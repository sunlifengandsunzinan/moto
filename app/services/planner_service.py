from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from functools import lru_cache
import hashlib
from html import escape
import json
import math
import re
from typing import Any, Mapping
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit
from urllib.request import urlopen

from flask import current_app, has_app_context

from .liaoning_spots import (
    ROUTE_TYPE_LABELS,
    SUPPORT_LABELS,
    build_preview_spot_image_gallery,
    build_previewable_moto_spot_record,
    get_approved_moto_spots,
    get_empty_moto_spot_record,
    get_liaoning_moto_spots,
    get_moto_spot_collection_schema,
)
from .candidate_spots import build_candidate_review_media, candidate_to_collection_record, get_candidate_spot_by_slug, get_candidate_spots
from .candidate_spots import get_reviewed_spots
from . import gpx_service
from .navigation_import_assistant import build_navigation_import_assistant_payload
from .route_engagement import get_route_engagement, get_route_engagement_map
from .route_templates_config import load_route_templates
from .user_me_state import (
    get_club_activity_signup_counts,
    get_route_collection_community_stats,
    get_route_checkpoint_checkin_counts,
    get_route_want_go_stats,
    get_route_want_go_stats_map,
    get_user_club_activity_signup_slugs,
    get_user_me_metrics,
    get_user_route_checkpoint_collection,
    get_user_want_go_records,
    get_user_want_go_route_plan_details,
    get_user_route_collections,
)


RouteDict = dict[str, Any]


COLLECTION_GROUP_LABELS = {
    "identity": "基础识别",
    "location": "位置与可达性",
    "travel": "骑行与出行判断",
    "content": "内容展示",
    "planning": "规划关系",
    "support": "补给与驿站支持",
    "quality": "质量与核验",
}

SPOT_MARKER_LABELS = {
    "checkin-point": "打卡点",
    "fuel-station": "加油站",
    "moto-station": "摩托驿站",
    "coffee-stop": "咖啡站",
    "support-stop": "补给点",
}

SPOT_TYPE_LABELS = {
    "scenic-spot": "风景打卡点",
    "moto-station": "摩托驿站",
    "support-stop": "补给点",
}

ROUTE_ONLY_ANCHOR_PREFIX = "__anchor__:"


def _mini_program_route_detail_action(slug: str) -> dict[str, Any]:
    return {"type": "route-detail", "slug": str(slug).strip()}


def _mini_program_tab_action(tab: str) -> dict[str, str]:
    return {"type": "tab", "tab": str(tab).strip()}


def _mini_program_webview_action(path: str) -> dict[str, str]:
    return {"type": "webview", "path": str(path).strip()}


def _mini_program_api_action(path: str) -> dict[str, str]:
    normalized = f"/{str(path or '').strip().lstrip('/')}"
    if normalized.startswith("/api/"):
        normalized = normalized.removeprefix("/api")
    return {"type": "api", "path": normalized}


def _mini_program_download_action(path: str) -> dict[str, str]:
    return {"type": "download", "path": str(path).strip()}


def _mini_program_spots_filter_action(query: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "type": "spots-filter",
        "query": {
            str(key): str(value).strip()
            for key, value in query.items()
            if str(value or "").strip()
        },
    }


def _mini_program_action_for_href(href: str) -> dict[str, Any]:
    value = str(href or "").strip()
    if not value:
        return {}
    if value.startswith("/api/"):
        return _mini_program_api_action(value)
    if value == "/moto/routes":
        return _mini_program_tab_action("routes")
    if value == "/moto/spots":
        return _mini_program_tab_action("spots")
    if value == "/moto/me":
        return _mini_program_tab_action("me")

    route_match = re.fullmatch(r"/moto/routes/([^/?#]+)", value)
    if route_match:
        return _mini_program_route_detail_action(route_match.group(1))

    return _mini_program_webview_action(value)


def _with_mini_program_action(item: Mapping[str, Any]) -> dict[str, Any]:
    decorated = dict(item)
    href = str(decorated.get("href") or "").strip()
    if href:
        decorated["mini_program_action"] = _mini_program_action_for_href(href)
    return decorated


def get_spot_collection_context(
    form_data: Mapping[str, Any] | None = None,
    candidate_slug: str | None = None,
    review_feedback: Mapping[str, str] | None = None,
    apply_video_analysis: bool = False,
) -> dict[str, Any]:
    selected_candidate = get_candidate_spot_by_slug(candidate_slug) if candidate_slug else None
    record = (
        build_spot_collection_record(form_data)
        if form_data
        else candidate_to_collection_record(selected_candidate, apply_video_analysis=apply_video_analysis)
        if selected_candidate
        else get_empty_moto_spot_record()
    )
    preview_record = build_previewable_moto_spot_record(record)
    schema = get_moto_spot_collection_schema()
    groups = _collection_groups(schema, record)
    required_fields = [field for field in schema if field["required"]]
    missing_required = [field["label"] for field in required_fields if _is_missing(record, field["name"])]
    candidate_queue = [_candidate_card(item, candidate_slug) for item in get_candidate_spots()]
    reviewed_spots = get_reviewed_spots()
    review_media = build_candidate_review_media(selected_candidate)
    video_apply_diff = _video_apply_diff(selected_candidate) if selected_candidate else {"has_changes": False, "items": []}

    return {
        "page": {
            "title": "录入摩旅点位",
            "description": "按固定字段收集打卡点、摩托驿站、补给点和中转节点。先做结构化录入，再决定是否入库。",
        },
        "collection_form": {
            "action": f"/moto/spots/collect?candidate={candidate_slug}" if candidate_slug else "/moto/spots/collect",
            "method": "post",
            "groups": groups,
            "submit_label": "生成结构化预览",
        },
        "candidate_review": {
            "selected": selected_candidate,
            "selected_media": review_media,
            "apply_video_analysis": apply_video_analysis,
            "video_apply_href": f"/moto/spots/collect?candidate={candidate_slug}&apply_video_analysis=1" if candidate_slug else "",
            "video_reset_href": f"/moto/spots/collect?candidate={candidate_slug}" if candidate_slug else "",
            "video_apply_diff": video_apply_diff,
            "queue": candidate_queue,
            "feedback": review_feedback,
            "management": {
                "clear_all_action": "/moto/spots/reviewed/clear",
                "delete_selected_action": "/moto/spots/reviewed/delete",
            },
            "reviewed_sections": [
                {
                    "key": "approved",
                    "title": "已批准数据",
                    "count": len(reviewed_spots["approved"]),
                    "entries": reviewed_spots["approved"],
                },
                {
                    "key": "rejected",
                    "title": "已拒绝数据",
                    "count": len(reviewed_spots["rejected"]),
                    "entries": reviewed_spots["rejected"],
                },
            ],
        },
        "preview": {
            "record": record,
            "json": json.dumps(record, ensure_ascii=False, indent=2),
            "missing_required": missing_required,
            "image_gallery": build_preview_spot_image_gallery(preview_record),
        },
        "tips": [
            "先保证必填字段完整，再补道路特征、风险提示和来源信息。",
            "列表字段统一用中文逗号或换行分隔，系统会自动拆分。",
            "sources 建议每行一条，格式：来源类型 | 来源名称 | 来源地址 | 作者 | 是否核验 | 备注。",
            "如果候选带有抖音视频分析结果，先参考关键帧、本地 OCR 和路线提示，再决定是否批准。",
        ],
    }


def _candidate_card(candidate: Mapping[str, Any], selected_slug: str | None) -> dict[str, Any]:
    return {
        "slug": candidate["slug"],
        "name": candidate["name"],
        "city": candidate["city"],
        "summary": candidate["summary"],
        "confidence_score": candidate["confidence_score"],
        "source_count": candidate["source_count"],
        "review_href": candidate["review_href"],
        "is_selected": candidate["slug"] == selected_slug,
    }


def build_spot_collection_record(form_data: Mapping[str, Any]) -> dict[str, Any]:
    template = get_empty_moto_spot_record()
    record = {
        key: value.copy() if isinstance(value, dict | list) else value
        for key, value in template.items()
    }

    scalar_fields = [
        "slug",
        "name",
        "spot_type",
        "city",
        "region",
        "route_type",
        "access_level",
        "ride_level",
        "recommended_stay",
        "summary",
        "image_key",
        "fuel_support",
        "repair_support",
        "lodging_support",
        "food_support",
        "confidence_score",
        "last_verified_at",
    ]
    list_fields = [
        "spot_markers",
        "best_seasons",
        "best_time_of_day",
        "road_features",
        "risk_notes",
        "photo_focus",
        "image_urls",
        "route_tags",
        "nearby_spot_slugs",
        "support_role",
        "moto_station_features",
    ]

    for name in scalar_fields:
        value = str(form_data.get(name, "")).strip()
        if value:
            record[name] = value

    for name in list_fields:
        record[name] = _split_collection_list(str(form_data.get(name, "")))

    record["parking_friendly"] = _parse_boolean(form_data.get("parking_friendly"))
    record["coordinates"] = {
        "lat": _parse_float(form_data.get("coordinates_lat")),
        "lng": _parse_float(form_data.get("coordinates_lng")),
    }
    record["sources"] = _parse_sources_form(form_data)
    return record


def _collection_groups(schema: list[dict[str, Any]], record: Mapping[str, Any]) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    by_group = {group: [] for group in COLLECTION_GROUP_LABELS}

    for field in schema:
        by_group[field["group"]].append(_collection_field(field, record))

    for group, label in COLLECTION_GROUP_LABELS.items():
        groups.append({"key": group, "label": label, "fields": by_group[group]})

    return groups


def _collection_field(field: Mapping[str, Any], record: Mapping[str, Any]) -> dict[str, Any]:
    name = str(field["name"])
    field_type = str(field["type"])
    component = "text"
    value: Any = record.get(name, "")

    if name == "summary":
        component = "textarea"
    elif field_type == "list[string]":
        component = "textarea"
        value = "\n".join(record.get(name, []))
    elif field_type == "list[object]":
        component = "sources"
        value = _source_rows(record.get(name, []))
    elif field_type == "boolean":
        component = "select"
        value = "yes" if value is True else "no" if value is False else ""
    elif field_type == "object" and name == "coordinates":
        component = "coordinates"
        value = {
            "lat": "" if record.get(name, {}).get("lat") is None else record[name]["lat"],
            "lng": "" if record.get(name, {}).get("lng") is None else record[name]["lng"],
        }

    return {
        "name": name,
        "label": field["label"],
        "required": field["required"],
        "group": field["group"],
        "component": component,
        "value": value,
        "example": field["example"],
        "type": field_type,
        "options": _collection_options(name, field_type),
    }


def _collection_options(name: str, field_type: str) -> list[dict[str, str]]:
    if field_type != "boolean":
        return []
    return [
        {"label": "未填写", "value": ""},
        {"label": "是", "value": "yes"},
        {"label": "否", "value": "no"},
    ]


def _is_missing(record: Mapping[str, Any], field_name: str) -> bool:
    value = record.get(field_name)
    if isinstance(value, list):
        return len(value) == 0
    if isinstance(value, dict):
        return all(item in (None, "") for item in value.values())
    return value in (None, "")


def _split_collection_list(raw: str) -> list[str]:
    normalized = raw.replace("，", ",").replace("\n", ",")
    return [item.strip() for item in normalized.split(",") if item.strip()]


def _parse_boolean(value: Any) -> bool | None:
    normalized = str(value or "").strip().lower()
    if normalized == "yes":
        return True
    if normalized == "no":
        return False
    return None


def _parse_float(value: Any) -> float | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _parse_sources(raw: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for line in raw.splitlines():
        parts = [part.strip() for part in line.split("|")]
        if not any(parts):
            continue
        if len(parts) >= 6:
            item = {
                "type": parts[0],
                "name": parts[1],
                "url": parts[2],
                "author": parts[3],
                "verified": parts[4].lower() in {"yes", "true", "1", "是"},
                "note": parts[5],
            }
        else:
            item = {
                "type": parts[0] if len(parts) > 0 else "",
                "name": parts[1] if len(parts) > 1 else "",
                "url": "",
                "author": "",
                "verified": (parts[2].lower() in {"yes", "true", "1", "是"}) if len(parts) > 2 else False,
                "note": parts[3] if len(parts) > 3 else "",
            }
        items.append(item)
    return items


def _parse_sources_form(form_data: Mapping[str, Any]) -> list[dict[str, Any]]:
    types = _form_list_values(form_data, "sources_type")
    names = _form_list_values(form_data, "sources_name")
    urls = _form_list_values(form_data, "sources_url")
    authors = _form_list_values(form_data, "sources_author")
    verified_values = _form_list_values(form_data, "sources_verified")
    notes = _form_list_values(form_data, "sources_note")

    if any(types + names + urls + authors + verified_values + notes):
        row_count = max(len(types), len(names), len(urls), len(authors), len(verified_values), len(notes))
        items: list[dict[str, Any]] = []
        for index in range(row_count):
            item = {
                "type": types[index] if index < len(types) else "",
                "name": names[index] if index < len(names) else "",
                "url": urls[index] if index < len(urls) else "",
                "author": authors[index] if index < len(authors) else "",
                "verified": (verified_values[index].lower() in {"yes", "true", "1", "是"}) if index < len(verified_values) else False,
                "note": notes[index] if index < len(notes) else "",
            }
            if any(str(value).strip() for key, value in item.items() if key != "verified") or item["verified"]:
                items.append(item)
        return items

    return _parse_sources(str(form_data.get("sources", "")))


def _form_list_values(form_data: Mapping[str, Any], field_name: str) -> list[str]:
    getlist = getattr(form_data, "getlist", None)
    if callable(getlist):
        return [str(value).strip() for value in getlist(field_name)]

    value = form_data.get(field_name, [])
    if isinstance(value, list):
        return [str(item).strip() for item in value]
    if value in (None, ""):
        return []
    return [str(value).strip()]


def _source_rows(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = [
        {
            "type": str(item.get("type", "")),
            "name": str(item.get("name", "")),
            "url": str(item.get("url", "")),
            "author": str(item.get("author", "")),
            "verified": "yes" if item.get("verified") else "no",
            "note": str(item.get("note", "")),
        }
        for item in sources
    ]
    while len(rows) < 3:
        rows.append(
            {
                "type": "",
                "name": "",
                "url": "",
                "author": "",
                "verified": "",
                "note": "",
            }
        )
    return rows


def planner_route_options() -> list[dict[str, str]]:
    options = [{"label": "智能匹配（推荐）", "value": ""}]
    options.extend(
        {"label": route["title"], "value": route["slug"]}
        for route in get_route_templates()
    )
    return options


def planner_region_options() -> list[dict[str, str]]:
    return [
        {"label": "全部地区", "value": ""},
        {"label": "东北 / 辽宁", "value": "north"},
        {"label": "华东", "value": "east"},
        {"label": "华南", "value": "south"},
    ]


def planner_spot_options() -> list[dict[str, str]]:
    approved_spot_slugs = {spot["slug"] for spot in get_approved_moto_spots()}
    return [
        {
            "label": f"{spot['name']} · {spot['city']}",
            "value": spot["slug"],
            "is_newly_approved": spot["slug"] in approved_spot_slugs,
        }
        for spot in get_liaoning_moto_spots()
    ]


def planner_must_visit_field() -> dict[str, Any]:
    options = planner_spot_options()
    highlighted_options = [option for option in options if option["is_newly_approved"]]
    regular_options = [option for option in options if not option["is_newly_approved"]]
    return {
        "name": "must_visit_spots",
        "label": "想经过的打卡点",
        "type": "checkbox_group",
        "value": [],
        "options": options,
        "highlighted_options": highlighted_options,
        "regular_options": regular_options,
    }


def get_spots_index_context(query: Mapping[str, Any]) -> dict[str, Any]:
    spots = get_liaoning_moto_spots()
    region = str(query.get("region", "")).strip()
    route_type = str(query.get("route_type", "")).strip()
    support = str(query.get("support", "")).strip()

    filtered_spots = [spot for spot in spots if _spot_matches_filters(spot, region, route_type, support)]
    active_filters = _spot_active_filters(spots, region, route_type, support)

    return {
        "page": {
            "title": "辽宁摩旅点位库",
            "description": "把打卡点、补给节点和骑行地标压缩成一张适合手机快速浏览的清单，先选点位，再进路线规划。",
        },
        "entry_actions": [
            _with_mini_program_action({"label": "开始规划", "href": "/moto/planner", "kind": "primary"}),
            _with_mini_program_action({"label": "录入点位", "href": "/moto/spots/collect", "kind": "secondary"}),
        ],
        "filters": {
            "action": "/moto/spots",
            "reset_href": "/moto/spots",
            "mini_program_reset_action": _mini_program_tab_action("spots"),
            "fields": [
                {
                    "name": "region",
                    "label": "区域",
                    "value": region,
                    "options": _spot_filter_options(spots, "region", "全部区域"),
                },
                {
                    "name": "route_type",
                    "label": "线路类型",
                    "value": route_type,
                    "options": _spot_route_type_options(spots),
                },
                {
                    "name": "support",
                    "label": "支撑能力",
                    "value": support,
                    "options": _spot_support_options(),
                },
            ],
            "active_filters": active_filters,
            "has_active_filters": len(active_filters) > 0,
            "quick_groups": _spot_quick_filter_groups(spots, region, route_type, support),
        },
        "stats": {
            "total": len(spots),
            "visible": len(filtered_spots),
            "regions": len({spot["region"] for spot in spots}),
            "filters": len(active_filters),
        },
        "spots": [_spot_card(spot) for spot in filtered_spots],
        "empty_state": {
            "title": "当前筛选下还没有命中的点位",
            "description": "先放宽筛选条件，或者去录入页补充新的摩旅点位。",
            "action": _with_mini_program_action({"label": "去录入点位", "href": "/moto/spots/collect"}),
        },
    }


def build_route_recommendations_for_spot(spot: Mapping[str, Any], limit: int = 3) -> list[dict[str, Any]]:
    recommendations: list[dict[str, Any]] = []
    for route in get_route_templates():
        score = spot_route_affinity_score(spot, route)
        if score <= 0:
            continue
        recommendations.append(
            {
                "slug": route["slug"],
                "title": route["title"],
                "summary": route["summary"],
                "score": score,
                "reasons": _spot_route_recommendation_reasons(spot, route),
                "route_href": f"/moto/routes/{route['slug']}",
                "planner_href": f"/moto/planner?route={route['slug']}&origin={spot['city']}",
                "mini_program_route_action": _mini_program_route_detail_action(str(route["slug"])),
                "mini_program_planner_action": _mini_program_webview_action(
                    f"/moto/planner?route={route['slug']}&origin={spot['city']}"
                ),
            }
        )

    recommendations.sort(key=lambda item: item["score"], reverse=True)
    return recommendations[:limit]


def _spot_matches_filters(spot: Mapping[str, Any], region: str, route_type: str, support: str) -> bool:
    if region and spot["region"] != region:
        return False
    if route_type and spot["route_type"] != route_type:
        return False
    if support and support not in spot["support_role"]:
        return False
    return True


def _spot_filter_options(spots: list[Mapping[str, Any]], field: str, default_label: str) -> list[dict[str, str]]:
    values = sorted({str(spot[field]) for spot in spots})
    return [{"label": default_label, "value": ""}] + [
        {"label": value, "value": value} for value in values
    ]


def _spot_route_type_options(spots: list[Mapping[str, Any]]) -> list[dict[str, str]]:
    options = [{"label": "全部类型", "value": ""}]
    seen: set[str] = set()
    for spot in spots:
        if spot["route_type"] in seen:
            continue
        seen.add(spot["route_type"])
        options.append({"label": spot["route_type_label"], "value": spot["route_type"]})
    return options


def _spot_support_options() -> list[dict[str, str]]:
    return [
        {"label": "全部支撑", "value": ""},
        {"label": "适合补油", "value": "fuel"},
        {"label": "适合过夜", "value": "lodging"},
        {"label": "附近可维修", "value": "repair"},
        {"label": "适合观景停留", "value": "viewpoint"},
    ]


def _spot_card(spot: Mapping[str, Any]) -> dict[str, Any]:
    video_brief = _spot_video_brief(spot)
    support_labels = spot["support_labels"]
    summary_tags = [item for item in [spot["route_type_label"], spot["ride_level_label"], *support_labels[:1]] if item]
    return {
        "slug": spot["slug"],
        "name": spot["name"],
        "city": spot["city"],
        "region": spot["region"],
        "summary": spot["summary"],
        "spot_markers": _spot_marker_labels(spot.get("spot_markers", [])),
        "route_type_label": spot["route_type_label"],
        "ride_level_label": spot["ride_level_label"],
        "season_labels": spot["season_labels"],
        "support_labels": support_labels,
        "best_time_of_day": spot["best_time_of_day"],
        "quick_meta": [
            spot["route_type_label"],
            spot["ride_level_label"],
            *spot["best_time_of_day"][:2],
        ],
        "summary_tags": summary_tags,
        "summary_tags_count": len(summary_tags),
        "video_summary": video_brief["summary"],
        "video_chips": video_brief["chips"],
        "href": f"/moto/spots/liaoning/{spot['slug']}",
        "mini_program_action": _mini_program_webview_action(f"/moto/spots/liaoning/{spot['slug']}"),
        "image_url": spot["image_gallery"][0]["image_url"],
    }


def _spot_marker_labels(markers: Any) -> list[str]:
    values = markers if isinstance(markers, list) else []
    return [SPOT_MARKER_LABELS.get(str(item), str(item)) for item in values if str(item).strip()]


def _spot_active_filters(spots: list[Mapping[str, Any]], region: str, route_type: str, support: str) -> list[dict[str, str]]:
    filters: list[dict[str, str]] = []
    if region:
        filters.append({"label": "区域", "value": region})
    if route_type:
        route_label = next(
            (option["label"] for option in _spot_route_type_options(spots) if option["value"] == route_type),
            route_type,
        )
        filters.append({"label": "线路", "value": route_label})
    if support:
        support_label = next(
            (option["label"] for option in _spot_support_options() if option["value"] == support),
            support,
        )
        filters.append({"label": "支撑", "value": support_label})
    return filters


def _spot_quick_filter_groups(
    spots: list[Mapping[str, Any]],
    region: str,
    route_type: str,
    support: str,
) -> list[dict[str, Any]]:
    return [
        {
            "title": "按区域看",
            "items": [
                _spot_quick_filter_item(
                    label=option["label"],
                    current=region,
                    target=option["value"],
                    query={"region": option["value"], "route_type": route_type, "support": support},
                )
                for option in _spot_filter_options(spots, "region", "全部区域")
            ],
        },
        {
            "title": "按需求看",
            "items": [
                _spot_quick_filter_item(
                    label=option["label"],
                    current=support,
                    target=option["value"],
                    query={"region": region, "route_type": route_type, "support": option["value"]},
                )
                for option in _spot_support_options()
            ],
        },
    ]


def _spot_quick_filter_item(label: str, current: str, target: str, query: Mapping[str, str]) -> dict[str, Any]:
    return {
        "label": label,
        "href": _build_spot_query_href(query),
        "mini_program_action": _mini_program_spots_filter_action(query),
        "is_active": current == target,
    }


def _build_spot_query_href(query: Mapping[str, str]) -> str:
    pairs = [f"{key}={value}" for key, value in query.items() if value]
    return "/moto/spots" if not pairs else f"/moto/spots?{'&'.join(pairs)}"


def _spot_video_brief(spot: Mapping[str, Any]) -> dict[str, Any]:
    video_analysis = spot.get("video_analysis") or spot.get("videoAnalysis") or {}
    fixed_spot_info = spot.get("fixed_spot_info") or spot.get("fixedSpotInfo") or {}
    keyframe_paths = spot.get("keyframe_paths") or spot.get("keyframePaths") or []

    if not isinstance(video_analysis, dict):
        video_analysis = {}
    if not isinstance(fixed_spot_info, dict):
        fixed_spot_info = {}
    if not isinstance(keyframe_paths, list):
        keyframe_paths = [keyframe_paths] if keyframe_paths else []

    chips: list[str] = []
    if spot.get("video_url") or spot.get("videoUrl"):
        chips.append("视频采集")
    if keyframe_paths:
        chips.append(f"关键帧 {len([item for item in keyframe_paths if str(item).strip()])} 张")
    if fixed_spot_info.get("poiType"):
        chips.append(_spot_type_label(fixed_spot_info.get("poiType")))
    if fixed_spot_info.get("routeType"):
        chips.append(_route_type_label(fixed_spot_info.get("routeType")))

    summary = (
        str(video_analysis.get("summary") or "").strip()
        or str(video_analysis.get("sceneSummary") or "").strip()
        or str(fixed_spot_info.get("summary") or "").strip()
    )
    return {"summary": summary, "chips": chips[:4]}


def _video_apply_diff(candidate: Mapping[str, Any]) -> dict[str, Any]:
    baseline = candidate_to_collection_record(candidate, apply_video_analysis=False)
    applied = candidate_to_collection_record(candidate, apply_video_analysis=True)
    fields = [
        ("city", "城市"),
        ("region", "区域"),
        ("spot_type", "点位类型"),
        ("route_type", "路线类型"),
        ("summary", "摘要"),
        ("support_role", "支撑标签"),
        ("spot_markers", "固定标记"),
        ("photo_focus", "拍摄重点"),
        ("route_tags", "路线标签"),
    ]
    items: list[dict[str, str]] = []
    for field_name, label in fields:
        before = _diff_display_value(field_name, baseline.get(field_name))
        after = _diff_display_value(field_name, applied.get(field_name))
        if before == after:
            continue
        change_kind = "added" if _is_empty_diff_value(baseline.get(field_name)) else "overwritten"
        items.append(
            {
                "label": label,
                "before": before,
                "after": after,
                "change_kind": change_kind,
                "change_label": "仅新增" if change_kind == "added" else "覆盖已有值",
            }
        )
    return {"has_changes": len(items) > 0, "items": items}


def _diff_display_value(field_name: str, value: Any) -> str:
    if isinstance(value, list):
        items = [_field_item_label(field_name, item) for item in value if str(item).strip()]
        return "、".join(items) if items else "未填写"
    if field_name == "spot_type":
        return _spot_type_label(value)
    if field_name == "route_type":
        return _route_type_label(value)
    text = str(value or "").strip()
    return text or "未填写"


def _field_item_label(field_name: str, value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if field_name == "support_role":
        return SUPPORT_LABELS.get(text, text)
    if field_name == "spot_markers":
        return SPOT_MARKER_LABELS.get(text, text)
    return text


def _spot_type_label(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "未填写"
    return SPOT_TYPE_LABELS.get(text, text)


def _route_type_label(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "未填写"
    return ROUTE_TYPE_LABELS.get(text, text)


def _is_empty_diff_value(value: Any) -> bool:
    if isinstance(value, list):
        return not any(str(item).strip() for item in value)
    if isinstance(value, dict):
        return not any(str(item).strip() for item in value.values())
    return not str(value or "").strip()


def get_home_context() -> dict[str, Any]:
    return {
        "nav": {
            "brand": "摩旅计划",
            "links": [
                {"label": "开始规划", "href": "/moto/planner"},
                {"label": "热门路线", "href": "/moto/routes"},
                {"label": "采集监控", "href": "/moto/collector/monitor"},
                {"label": "定制规划", "href": "/moto/custom"},
            ],
        },
        "hero": {
            "eyebrow": "摩托车旅行路线规划",
            "title": "把摩旅攻略，变成一份能直接出发的计划",
            "subtitle": "输入出发地、天数和骑行偏好，快速生成每日路线、沿途补给建议和行前清单。",
            "primary_action": {"label": "开始规划路线", "href": "/moto/planner"},
            "secondary_action": {"label": "查看热门路线", "href": "/moto/routes"},
            "highlights": [
                "按日拆分行程",
                "补给与维修点建议",
                "适合新手的风险提醒",
            ],
        },
        "benefits": [
            {
                "title": "按摩托车出行场景规划",
                "description": "不是通用旅游攻略，更关注每日骑行强度、补给点位和实际可执行性。",
            },
            {
                "title": "每天怎么骑，一眼看懂",
                "description": "自动拆分每日里程、休息点和过夜建议，减少临时改计划的麻烦。",
            },
            {
                "title": "新手也能放心出发",
                "description": "提供路线提醒、装备清单和常见风险提示，适合第一次摩旅的人。",
            },
        ],
        "featured_routes": [
            {
                "slug": "liaoning-benhuan-3-day",
                "title": "辽宁 3 天本溪到绿江边境风景线",
                "summary": "跑山、江景和边境县道串在一起，适合辽宁省内经典摩旅。",
                "tags": ["3 天", "辽宁", "山水边境"],
                "href": "/moto/routes/liaoning-benhuan-3-day",
            },
            {
                "slug": "liaoning-dalian-coast-2-day",
                "title": "辽宁南部 2 天大连海岸线轻旅",
                "summary": "滨海公路、城区补给和轻强度节奏更适合周末短途。",
                "tags": ["2 天", "辽宁", "海岸线"],
                "href": "/moto/routes/liaoning-dalian-coast-2-day",
            },
            {
                "slug": "liaoning-liaodong-2-day",
                "title": "辽宁东部 2 天丹东到宽甸江景线",
                "summary": "江景、县道和沿线补给点组合，适合两天内完成的辽东骑行。",
                "tags": ["2 天", "辽宁", "江景"],
                "href": "/moto/routes/liaoning-liaodong-2-day",
            },
            {
                "slug": "liaoning-red-beach-2-day",
                "title": "辽宁西线 2 天红海滩与兴城海滨",
                "summary": "平缓海滨线和湿地风景结合，适合放松型公路旅行。",
                "tags": ["2 天", "辽宁", "湿地海滨"],
                "href": "/moto/routes/liaoning-red-beach-2-day",
            },
        ],
        "cta": {
            "title": "路线不想自己做？可以直接定制",
            "description": "适合第一次长途、多人结伴、异地摩旅或需要更细路线安排的人。",
            "action": {"label": "提交定制需求", "href": "/moto/custom"},
        },
    }


def build_moto_tabbar(active_tab: str) -> dict[str, Any]:
    items = [
        {"key": "routes", "label": "路线", "href": "/moto/routes"},
        {"key": "spots", "label": "打卡点", "href": "/moto/spots"},
        {"key": "me", "label": "我的", "href": "/moto/me"},
    ]
    return {
        "items": [
            {
                **_with_mini_program_action(item),
                "is_active": item["key"] == active_tab,
            }
            for item in items
        ]
    }


def get_moto_me_context(user_id: str | None = None) -> dict[str, Any]:
    route_templates = get_route_templates()
    gpx_lookup = _build_gpx_lookup()
    route_lookup = {
        str(route.get("slug") or "").strip(): route
        for route in route_templates
        if str(route.get("slug") or "").strip()
    }
    user_metrics = get_user_me_metrics(user_id)
    checkin_count = int(user_metrics.get("checkin_count") or 0)
    want_go_records_source = get_user_want_go_records(user_id)
    want_go_count = len(want_go_records_source)
    route_collections = get_user_route_collections(user_id)

    bucket_labels = {
        "this_month": "这个月",
        "next_month": "下个月",
        "later": "再说",
    }

    want_go_records: list[dict[str, Any]] = []
    for plan_detail in want_go_records_source:
        slug = str(plan_detail.get("slug") or "").strip()
        if not slug:
            continue
        route = route_lookup.get(slug, {})
        plan_bucket = str(plan_detail.get("bucket") or "").strip()
        updated_at = str(plan_detail.get("selected_at") or plan_detail.get("updated_at") or "").strip()
        want_go_records.append(
            {
                "slug": slug,
                "route_title": str(route.get("title") or slug).strip() or slug,
                "plan_bucket": plan_bucket,
                "plan_label": bucket_labels.get(plan_bucket, "未选择"),
                "updated_at": updated_at,
                "status": str(plan_detail.get("status") or "").strip() or "active",
                "mini_program_action": _mini_program_route_detail_action(slug),
            }
        )
    want_go_records.sort(
        key=lambda item: (
            str(item.get("updated_at") or ""),
            str(item.get("slug") or ""),
        ),
        reverse=True,
    )

    checkin_records: list[dict[str, Any]] = []
    for slug, collection in route_collections.items():
        route = route_lookup.get(slug, {})
        checkpoint_total_hint = _route_detail_checkpoint_total_hint(route, gpx_lookup=gpx_lookup)
        normalized_collection = (
            get_user_route_checkpoint_collection(user_id, slug, checkpoint_total=checkpoint_total_hint)
            if checkpoint_total_hint > 0
            else collection
        )
        checked_count = int(normalized_collection.get("checked_count") or 0)
        checkpoint_total = int(normalized_collection.get("checkpoint_total") or 0)
        checkin_records.append(
            {
                "slug": slug,
                "route_title": str(normalized_collection.get("route_title") or route.get("title") or slug).strip() or slug,
                "checked_count": checked_count,
                "checkpoint_total": checkpoint_total,
                "progress_text": f"{checked_count}/{checkpoint_total}" if checkpoint_total > 0 else str(checked_count),
                "updated_at": str(normalized_collection.get("updated_at") or "").strip(),
                "mini_program_action": _mini_program_route_detail_action(slug),
            }
        )
    checkin_records.sort(
        key=lambda item: (
            str(item.get("updated_at") or ""),
            str(item.get("slug") or ""),
        ),
        reverse=True,
    )

    return {
        "page": {
            "title": "我的摩旅",
            "description": "把路线规划、直接导航和定制需求集中到一个页面里，更适合两 tab 的小程序结构。",
        },
        "profile": {
            "name": "摩旅计划",
            "tagline": "路线规划 · 直接导航 · 行程定制",
            "summary": "当前版本聚焦路线选择和出发决策，先让小程序更像一个轻量的摩旅路线工具。",
        },
        "metrics": [
            {"label": "我想去的", "value": want_go_count},
            {"label": "我的积分", "value": 0},
            {"label": "我打卡过的", "value": checkin_count},
        ],
        "sections": [
            {
                "title": "常用功能",
                "items": [
                    _with_mini_program_action(
                        {
                            "label": "开始路线规划",
                            "description": "按天数、车型和偏好生成基础行程。",
                            "href": "/moto/planner",
                        }
                    ),
                    _with_mini_program_action(
                        {
                            "label": "查看路线库",
                            "description": "按骑行时间快速切换路线，并直接跳转导航。",
                            "href": "/moto/routes",
                        }
                    ),
                    _with_mini_program_action(
                        {
                            "label": "提交定制需求",
                            "description": "如果不想自己筛路线，可以直接提交定制行程。",
                            "href": "/moto/custom",
                        }
                    ),
                    _with_mini_program_action(
                        {
                            "label": "采集导航点",
                            "description": "为路线补充经纬度、途径点顺序和来源备注。",
                            "href": "/moto/routes/collect",
                        }
                    ),
                ],
            },
            {
                "title": "最近可继续",
                "items": [
                    _with_mini_program_action(
                        {
                            "label": route["title"],
                            "description": route["summary"],
                            "href": f"/moto/routes/{route['slug']}",
                        }
                    )
                    for route in route_templates[:3]
                ],
            },
        ],
        "quick_actions": [
            _with_mini_program_action({"label": "路线库", "href": "/moto/routes", "kind": "primary"}),
            _with_mini_program_action({"label": "定制需求", "href": "/moto/custom", "kind": "secondary"}),
            _with_mini_program_action({"label": "采集导航点", "href": "/moto/routes/collect", "kind": "secondary"}),
        ],
        "user_records": {
            "want_go": want_go_records,
            "checkins": checkin_records,
        },
    }


def get_moto_collection_context(user_id: str | None = None) -> dict[str, Any]:
    route_templates = get_route_templates()
    gpx_lookup = _build_gpx_lookup()
    route_lookup = {
        str(route.get("slug") or "").strip(): route
        for route in route_templates
        if str(route.get("slug") or "").strip()
    }
    user_collections = get_user_route_collections(user_id)
    community_stats = get_route_collection_community_stats()
    route_community_stats = community_stats.get("route_stats") if isinstance(community_stats.get("route_stats"), dict) else {}
    signed_activity_slugs = get_user_club_activity_signup_slugs(user_id)

    routes: list[dict[str, Any]] = []
    badges: list[dict[str, Any]] = []
    completed_count = 0

    for slug, collection in user_collections.items():
        route = route_lookup.get(slug, {})
        checkpoint_total_hint = _route_detail_checkpoint_total_hint(route, gpx_lookup=gpx_lookup)
        normalized_collection = (
            get_user_route_checkpoint_collection(user_id, slug, checkpoint_total=checkpoint_total_hint)
            if checkpoint_total_hint > 0
            else collection
        )
        route_title = str(normalized_collection.get("route_title") or route.get("title") or slug).strip() or slug
        badge = normalized_collection.get("badge") if isinstance(normalized_collection.get("badge"), dict) else {}
        is_completed = bool(normalized_collection.get("is_completed"))
        if is_completed:
            completed_count += 1

        poster_href = f"/moto/routes/{slug}/amap-route.svg"
        route_item = {
            "slug": slug,
            "title": route_title,
            "distance_km": route.get("distance_km") or 0,
            "days": route.get("days") or 0,
            "checked_count": int(normalized_collection.get("checked_count") or 0),
            "checkpoint_total": int(normalized_collection.get("checkpoint_total") or 0),
            "completion_percent": int(normalized_collection.get("completion_percent") or 0),
            "is_completed": is_completed,
            "updated_at": str(normalized_collection.get("updated_at") or "").strip(),
            "poster_href": poster_href,
            "share_text": str((badge or {}).get("share_text") or f"我正在挑战 {route_title} 打卡路线").strip(),
            "mini_program_action": _mini_program_route_detail_action(slug),
            "club_avg_completion_percent": int((route_community_stats.get(slug) or {}).get("avg_completion_percent") or 0),
            "club_member_count": int((route_community_stats.get(slug) or {}).get("members") or 0),
        }
        routes.append(route_item)

        if badge:
            badges.append(
                {
                    "slug": slug,
                    "title": str(badge.get("title") or f"{route_title} 征服者").strip(),
                    "subtitle": str(badge.get("subtitle") or "路线打卡已集齐").strip(),
                    "awarded_at": str(badge.get("awarded_at") or "").strip(),
                    "share_text": str(badge.get("share_text") or route_item["share_text"]).strip(),
                    "poster_href": poster_href,
                    "mini_program_action": _mini_program_route_detail_action(slug),
                }
            )

    routes.sort(key=lambda item: (item["completion_percent"], item["updated_at"], item["title"]), reverse=True)
    badges.sort(key=lambda item: (item["awarded_at"], item["title"]), reverse=True)

    club_route_board = []
    for item in routes[:10]:
        community_item = route_community_stats.get(item["slug"]) if isinstance(route_community_stats, dict) else {}
        club_route_board.append(
            {
                "slug": item["slug"],
                "title": item["title"],
                "member_count": int((community_item or {}).get("members") or 0),
                "completed_member_count": int((community_item or {}).get("completed_members") or 0),
                "avg_completion_percent": int((community_item or {}).get("avg_completion_percent") or 0),
            }
        )

    style_counts: dict[str, int] = {}
    for route in route_templates:
        difficulty_text = difficulty_label(str(route.get("difficulty") or ""))
        style_key = difficulty_text or "综合路线"
        style_counts[style_key] = style_counts.get(style_key, 0) + 1

    style_tags = [
        {"label": key, "count": value}
        for key, value in sorted(style_counts.items(), key=lambda pair: pair[1], reverse=True)[:3]
    ]

    public_routes = [
        {
            "slug": route.get("slug") or "",
            "title": route.get("title") or "未命名路线",
            "poster_href": f"/moto/routes/{route.get('slug')}/amap-route.svg",
        }
        for route in route_templates[:3]
        if str(route.get("slug") or "").strip()
    ]
    public_route_slugs = [str(item.get("slug") or "").strip() for item in public_routes if str(item.get("slug") or "").strip()]
    signup_counts = get_club_activity_signup_counts(public_route_slugs)
    public_routes = [
        {
            **item,
            "signup_count": int(signup_counts.get(str(item.get("slug") or "").strip()) or 0),
            "is_signed_up": str(item.get("slug") or "").strip() in signed_activity_slugs,
        }
        for item in public_routes
    ]

    weekly_checkpoint_total = int(community_stats.get("weekly_checkpoint_total") or 0)
    weekly_completed_routes = int(community_stats.get("weekly_completed_routes") or 0)
    activity_level = "高"
    if weekly_checkpoint_total < 10:
        activity_level = "低"
    elif weekly_checkpoint_total < 30:
        activity_level = "中"

    return {
        "page": {
            "title": "我的收集册",
            "description": "手动打卡点亮每条路线，集齐即可获得征服者徽章。",
        },
        "summary": {
            "route_count": len(routes),
            "completed_route_count": completed_count,
            "badge_count": len(badges),
        },
        "club_public": {
            "title": "俱乐部公开内容",
            "route_styles": style_tags,
            "activity_level": activity_level,
            "activity_posters": public_routes,
        },
        "club_route_board": {
            "weekly_checkpoint_total": weekly_checkpoint_total,
            "weekly_completed_routes": weekly_completed_routes,
            "routes": club_route_board,
        },
        "badges": badges,
        "routes": routes,
    }


def _route_detail_checkpoint_total_hint(
    route: Mapping[str, Any],
    *,
    gpx_lookup: Mapping[str, Any] | None = None,
) -> int:
    if not isinstance(route, Mapping):
        return 0

    # Use the same checkpoint generation chain as route detail so totals stay consistent.
    route_card = _route_index_card(route, gpx_lookup=gpx_lookup, use_cached_preview_polyline=True)
    checkpoints = _build_route_detail_checkpoints(route, route_card)
    return len(checkpoints)


def get_planner_form_context(route_slug: str | None = None, origin: str | None = None) -> dict[str, Any]:
    context = {
        "page_intro": {
            "title": "规划你的摩旅路线",
            "description": "先填几个关键条件，我们会给你一份基础可执行方案。第一版更适合做出发前规划，不替代实时导航。",
        },
        "planner_form": {
            "action": "/moto/planner/result",
            "method": "post",
            "fields": [
                {
                    "name": "route_template",
                    "label": "优先参考路线模板",
                    "type": "select",
                    "value": "",
                    "options": planner_route_options(),
                },
                {
                    "name": "route_region",
                    "label": "想跑的地区",
                    "type": "select",
                    "value": "",
                    "options": planner_region_options(),
                },
                {
                    "name": "origin",
                    "label": "出发地",
                    "type": "text",
                    "placeholder": "例如：上海、杭州、成都",
                    "value": "",
                },
                {
                    "name": "trip_days",
                    "label": "出行天数",
                    "type": "select",
                    "value": "2",
                    "options": [
                        {"label": "1 天", "value": "1"},
                        {"label": "2 天", "value": "2"},
                        {"label": "3 天", "value": "3"},
                        {"label": "5 天", "value": "5"},
                        {"label": "7 天", "value": "7"},
                    ],
                },
                {
                    "name": "daily_distance",
                    "label": "日均可接受骑行距离",
                    "type": "select",
                    "value": "200",
                    "options": [
                        {"label": "150 km - 轻松休闲", "value": "150"},
                        {"label": "200 km - 常规舒适", "value": "200"},
                        {"label": "300 km - 进阶强度", "value": "300"},
                        {"label": "400 km+ - 长距离拉练", "value": "400"},
                    ],
                },
                {
                    "name": "experience_level",
                    "label": "骑行经验",
                    "type": "radio",
                    "value": "beginner",
                    "options": [
                        {"label": "新手", "value": "beginner"},
                        {"label": "有短途经验", "value": "intermediate"},
                        {"label": "有长途经验", "value": "advanced"},
                    ],
                },
                {
                    "name": "bike_type",
                    "label": "车型或排量",
                    "type": "select",
                    "value": "300-500cc",
                    "options": [
                        {"label": "125-150cc", "value": "125-150cc"},
                        {"label": "150-250cc", "value": "150-250cc"},
                        {"label": "300-500cc", "value": "300-500cc"},
                        {"label": "500cc+", "value": "500cc+"},
                        {"label": "ADV / Touring", "value": "adv-touring"},
                    ],
                },
                {
                    "name": "route_preference",
                    "label": "路线偏好",
                    "type": "checkbox_group",
                    "value": ["scenic", "relaxed"],
                    "options": [
                        {"label": "山路", "value": "mountain"},
                        {"label": "海边", "value": "coast"},
                        {"label": "风景", "value": "scenic"},
                        {"label": "轻松", "value": "relaxed"},
                        {"label": "少夜路", "value": "avoid_night"},
                        {"label": "小众路线", "value": "niche"},
                    ],
                },
                {
                    **planner_must_visit_field(),
                },
                {
                    "name": "budget_range",
                    "label": "预算范围",
                    "type": "select",
                    "value": "1000-2000",
                    "options": [
                        {"label": "500 以下", "value": "under-500"},
                        {"label": "500-1000", "value": "500-1000"},
                        {"label": "1000-2000", "value": "1000-2000"},
                        {"label": "2000-4000", "value": "2000-4000"},
                        {"label": "4000+", "value": "4000-plus"},
                    ],
                },
            ],
            "poi_settings": [
                {"name": "poi_types", "value": "fuel", "label": "加油点", "checked": True},
                {"name": "poi_types", "value": "repair", "label": "补胎 / 维修点", "checked": True},
                {"name": "poi_types", "value": "lodging", "label": "住宿点", "checked": True},
                {"name": "poi_types", "value": "viewpoint", "label": "观景点", "checked": True},
                {"name": "poi_types", "value": "emergency", "label": "应急点", "checked": False},
            ],
            "poi_settings_help": "勾选你希望结果页展示的 POI 点类型。第一版先按类型筛选，不做距离半径设置。",
            "submit_label": "生成路线方案",
            "footnote": "第一版结果为出发前规划建议，具体路况和天气请在出发前再次确认。",
        },
        "sample_trip": {
            "title": "默认体验案例",
            "summary": "杭州出发，2 天，偏风景和轻松节奏，适合有短途经验的骑手。",
            "chips": ["杭州", "2 天", "200 km/天", "300-500cc"],
        },
        "planner_tips": [
            "现在可以先选模板、地区，再细调预算和骑行偏好。",
            "如果你有明确想去的打卡点，可以直接勾选，匹配会优先靠近这些节点。",
            "当前版本优先给出基础可执行方案，不替代实时导航。",
            "如果是多人同行或复杂异地路线，建议直接提交定制需求。",
        ],
        "selected_route": None,
    }

    route = get_route_by_slug(route_slug) if route_slug else None
    if route is None:
        return context

    apply_route_defaults(context, route, origin)
    return context


def get_route_templates() -> list[RouteDict]:
    routes = deepcopy(load_route_templates())
    existing_slugs = {str(route.get("slug") or "") for route in routes}
    routes.extend(_build_gpx_route_records(existing_slugs))
    return routes


def get_liaoning_route_templates(*, include_hidden: bool = False) -> list[RouteDict]:
    liaoning_spot_slugs = {str(spot.get("slug") or "").strip() for spot in get_liaoning_moto_spots()}
    routes = get_route_templates()
    if not include_hidden:
        routes = [route for route in routes if _is_route_visible(route)]
    return [route for route in routes if _is_liaoning_route(route, liaoning_spot_slugs)]


def _is_route_visible(route: Mapping[str, Any]) -> bool:
    value = route.get("is_visible")
    if value is None:
        return True
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    raw = str(value).strip().lower()
    if raw in {"", "1", "true", "yes", "y"}:
        return True
    if raw in {"0", "false", "no", "n"}:
        return False
    return True


def _is_liaoning_route(route: Mapping[str, Any], liaoning_spot_slugs: set[str]) -> bool:
    scope_value = str(route.get("liaoning_scope") or "").strip().lower()
    if scope_value in {"include", "force", "forced", "true", "1", "yes"}:
        return True
    if scope_value in {"exclude", "false", "0", "no"}:
        return False

    route_spot_slugs = {
        str(value).strip()
        for value in (route.get("spot_slugs") or [])
        if str(value).strip()
    }
    if route_spot_slugs.intersection(liaoning_spot_slugs):
        return True

    text_fields = [
        str(route.get("slug") or ""),
        str(route.get("title") or ""),
        str(route.get("summary") or ""),
    ]

    tags = route.get("tags")
    if isinstance(tags, list):
        text_fields.extend(str(item) for item in tags)

    merged_text = " ".join(text_fields).lower()
    non_liaoning_keywords = [
        "北京", "天津", "河北", "山西", "内蒙古", "吉林", "黑龙江", "上海", "江苏", "浙江", "安徽", "福建", "江西",
        "山东", "河南", "湖北", "湖南", "广东", "广西", "海南", "重庆", "四川", "贵州", "云南", "西藏", "陕西",
        "甘肃", "青海", "宁夏", "新疆", "香港", "澳门", "台湾", "ji lin", "heilongjiang", "beijing", "tianjin",
    ]
    has_non_liaoning_keyword = any(keyword in merged_text for keyword in non_liaoning_keywords)

    waypoints = route.get("navigation", {}).get("waypoints") if isinstance(route.get("navigation"), Mapping) else []
    if isinstance(waypoints, list):
        coordinate_points = [
            item for item in waypoints
            if isinstance(item, Mapping) and item.get("lat") not in {None, ""} and item.get("lng") not in {None, ""}
        ]
        if coordinate_points:
            if all(_is_liaoning_coordinate(item.get("lat"), item.get("lng")) for item in coordinate_points):
                return True
            return False

        waypoint_text = " ".join(str(item.get("name") or "") for item in waypoints if isinstance(item, Mapping))
        non_liaoning_place_keywords = [
            "集安", "通化", "临江", "长白山", "延吉", "长春", "吉林市", "松原", "白城", "四平",
            "哈尔滨", "齐齐哈尔", "牡丹江", "佳木斯", "大庆", "伊春", "漠河", "加格达奇",
            "赤峰", "承德", "秦皇岛", "北京", "天津",
        ]
        if any(keyword in waypoint_text for keyword in non_liaoning_place_keywords):
            return False

        liaoning_city_keywords = ["沈阳", "大连", "丹东", "本溪", "盘锦", "葫芦岛", "锦州", "营口", "鞍山", "抚顺", "辽阳", "铁岭", "阜新", "朝阳", "宽甸", "桓仁"]
        city_hit_count = sum(1 for keyword in liaoning_city_keywords if keyword in waypoint_text)
        if city_hit_count >= 2 and not has_non_liaoning_keyword:
            return True

    if ("liaoning" in merged_text or "辽宁" in merged_text) and not has_non_liaoning_keyword:
        return True

    return False


def _is_liaoning_coordinate(raw_lat: Any, raw_lng: Any) -> bool:
    try:
        lat = float(raw_lat)
        lng = float(raw_lng)
    except (TypeError, ValueError):
        return False

    return 38.7 <= lat <= 43.6 and 118.8 <= lng <= 125.8


def get_route_by_slug(slug: str) -> dict[str, Any] | None:
    return next((route for route in get_route_templates() if route["slug"] == slug), None)


def _build_gpx_route_records(existing_slugs: set[str]) -> list[RouteDict]:
    gpx_routes: list[RouteDict] = []
    for record in gpx_service.get_processed_route_records(limit=500):
        if str(record.get("qualification_status") or "").strip() != "qualified":
            continue

        route_slug = str(record.get("route_slug") or "").strip()
        if not route_slug or route_slug in existing_slugs:
            continue

        filename = _gpx_basename(record.get("gpx_path") or "")
        if not filename:
            continue

        waypoints = _route_record_waypoints(record, filename)
        if len(waypoints) < 2:
            continue

        route_days = _dynamic_gpx_route_days(record, waypoints)
        distance_km = _dynamic_gpx_route_distance(record, waypoints)

        title = str(record.get("title") or filename.removesuffix(".gpx") or route_slug).strip()
        average_day_distance = max(1, round(distance_km / route_days))
        gpx_routes.append(
            {
                "slug": route_slug,
                "title": title,
                "region": "gpx-route",
                "spot_slugs": [],
                "days": route_days,
                "difficulty": "medium",
                "scenery_type": ["scenic", "relaxed"],
                "bike_types": ["150-250cc", "300-500cc", "adv-touring"],
                "experience_levels": ["beginner", "intermediate"],
                "best_season": "自动提取",
                "distance_km": int(round(distance_km)),
                "budget_range": "待补充",
                "summary": "来自自动入库的合格路线：已具备明确位置点或可打开点，可按高德路线继续校正路线与公里数；若缺少骑行天数则自动推断拆分。",
                "gpx_file": filename,
                "navigation": {
                    "provider": "amap",
                    "waypoints": waypoints,
                },
                "days_plan": _gpx_route_days_plan(waypoints, route_days, average_day_distance),
                "pois": {
                    "fuel": [],
                    "repair": [],
                    "lodging": [],
                    "viewpoint": [
                        {
                            "name": waypoints[-1]["name"],
                            "meta": "自动提取终点 · 已纳入路线页联动",
                        }
                    ],
                    "emergency": [],
                },
            }
        )
        existing_slugs.add(route_slug)

    return gpx_routes


def _dynamic_gpx_route_days(route_record: Mapping[str, Any], waypoints: list[dict[str, Any]]) -> int:
    route_days = int(route_record.get("route_days") or 0)
    if route_days > 0:
        return route_days
    estimated_distance = _dynamic_gpx_route_distance(route_record, waypoints)
    if estimated_distance >= 700:
        return 3
    if estimated_distance >= 320 or len(waypoints) >= 5:
        return 2
    return 1


def _dynamic_gpx_route_distance(route_record: Mapping[str, Any], waypoints: list[dict[str, Any]]) -> float:
    explicit_distance = float(route_record.get("distance_km") or 0)
    if explicit_distance > 0:
        return explicit_distance
    estimated = _estimate_waypoint_route_distance_km(waypoints)
    if estimated > 0:
        return estimated
    return float(max(80, (len(waypoints) - 1) * 80))


def _estimate_waypoint_route_distance_km(waypoints: list[Mapping[str, Any]]) -> float:
    coordinate_points = [point for point in waypoints if point.get("has_coordinates")]
    if len(coordinate_points) < 2:
        return 0.0

    total_distance_km = 0.0
    previous_point = coordinate_points[0]
    for point in coordinate_points[1:]:
        total_distance_km += _haversine_distance_km(
            float(previous_point.get("lat") or 0),
            float(previous_point.get("lng") or 0),
            float(point.get("lat") or 0),
            float(point.get("lng") or 0),
        )
        previous_point = point
    if total_distance_km <= 0:
        return 0.0
    return max(1.0, round(total_distance_km * 1.25, 1))


def _haversine_distance_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    radius_km = 6371.0
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lng = math.radians(lng2 - lng1)
    haversine = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lng / 2) ** 2
    )
    return radius_km * 2 * math.atan2(math.sqrt(haversine), math.sqrt(1 - haversine))


def _route_record_waypoints(route_record: Mapping[str, Any], filename: str) -> list[dict[str, Any]]:
    raw_waypoints = route_record.get("waypoints_json")
    if isinstance(raw_waypoints, str) and raw_waypoints.strip():
        try:
            parsed = json.loads(raw_waypoints)
        except json.JSONDecodeError:
            parsed = []
        if isinstance(parsed, list):
            normalized_points: list[dict[str, Any]] = []
            for item in parsed:
                if not isinstance(item, Mapping):
                    continue
                name = str(item.get("name") or "").strip()
                lat = item.get("lat")
                lng = item.get("lng")
                if not name or lat in {None, ""} or lng in {None, ""}:
                    continue
                try:
                    normalized_points.append(
                        {
                            "name": name,
                            "lat": float(lat),
                            "lng": float(lng),
                            "has_coordinates": True,
                        }
                    )
                except (TypeError, ValueError):
                    continue
            if normalized_points:
                return normalized_points

    return gpx_service.get_gpx_waypoints(filename)


def _gpx_route_days_plan(waypoints: list[dict[str, Any]], route_days: int, average_day_distance: int) -> list[dict[str, Any]]:
    chunk_size = max(1, len(waypoints) // route_days)
    days_plan: list[dict[str, Any]] = []

    for index in range(route_days):
        start = index * chunk_size
        end = None if index == route_days - 1 else (index + 1) * chunk_size
        chunk = waypoints[start:end]
        if not chunk:
            continue
        title = " -> ".join(point["name"] for point in chunk)
        days_plan.append(
            {
                "day": index + 1,
                "title": title,
                "ride_time": f"建议骑行 {3 + index}-{4 + index} 小时",
                "distance": average_day_distance,
                "highlights": ["明确途经点", "高德坐标导航", "自动入库路线"],
                "note": "该日计划按合格路线的途经点顺序拆分，用于和路线页及高德导航保持一致。",
            }
        )

    return days_plan


def get_route_waypoint_collection_schema() -> list[dict[str, Any]]:
    return [
        {
            "name": "route_slug",
            "label": "路线 slug",
            "required": True,
            "description": "和 route_templates.json 里的 slug 对齐，后续用于精确回写。",
            "example": "liaoning-benhuan-3-day",
        },
        {
            "name": "route_title",
            "label": "路线标题",
            "required": True,
            "description": "保留采集时看到的路线名，方便人工核对。",
            "example": "辽宁 3 天本溪到绿江边境风景线",
        },
        {
            "name": "source.channel",
            "label": "采集渠道",
            "required": True,
            "description": "例如手工整理、地图检索、轨迹导入、视频分析。",
            "example": "manual-map-research",
        },
        {
            "name": "source.reference_url",
            "label": "来源链接",
            "required": False,
            "description": "记录高德、游记、轨迹或短视频链接，便于回溯。",
            "example": "https://m.amap.com/...",
        },
        {
            "name": "source.operator",
            "label": "采集人",
            "required": False,
            "description": "标记本次补采由谁执行。",
            "example": "Lifeng",
        },
        {
            "name": "navigation.provider",
            "label": "导航提供方",
            "required": True,
            "description": "当前默认是 amap，后面可扩展到其他地图。",
            "example": "amap",
        },
        {
            "name": "navigation.waypoints[]",
            "label": "途径点数组",
            "required": True,
            "description": "按实际出发顺序写，至少 2 个点；有坐标就写 lng/lat，没有就先保留 name。",
            "example": '{"name": "莫干山", "lng": 119.8795, "lat": 30.6140, "source": "manual"}',
        },
        {
            "name": "collection_notes",
            "label": "采集备注",
            "required": False,
            "description": "说明点位是否待复核、是否需要拆成 day waypoints、是否有争议。",
            "example": "第 2 个服务点只有名称，等下次地图核对后补 lng/lat。",
        },
    ]


def get_route_waypoint_collection_context(route_slug: str | None = None) -> dict[str, Any]:
    route_templates = get_route_templates()
    selected_route = get_route_by_slug(route_slug) if route_slug else (route_templates[0] if route_templates else None)
    selected_card = _route_index_card(selected_route) if selected_route else None
    selected_seed = _build_route_waypoint_collection_seed(selected_route) if selected_route else {}

    return {
        "page": {
            "title": "路线坐标采集",
            "description": "先把路线的途径点和经纬度采成结构化数据，后续可以直接回写 route_templates.json 或接采集流水线。",
        },
        "route_options": [
            {
                "slug": route["slug"],
                "title": route["title"],
                "href": f"/moto/routes/collect?route={route['slug']}",
                "is_selected": selected_route is not None and route["slug"] == selected_route["slug"],
                "is_demo": bool(route.get("is_navigation_state_demo")),
            }
            for route in route_templates
        ],
        "selected_route": selected_card,
        "selected_route_seed": selected_seed,
        "selected_route_seed_json": json.dumps(selected_seed, ensure_ascii=False, indent=2),
        "schema": get_route_waypoint_collection_schema(),
        "api": {
            "schema_href": "/api/moto/routes/collect/schema",
            "selected_schema_href": (
                f"/api/moto/routes/collect/schema?route={selected_route['slug']}"
                if selected_route
                else "/api/moto/routes/collect/schema"
            ),
        },
        "storage": {
            "canonical_file": "app/services/route_templates.json",
            "seed_example_file": "data/raw/route_waypoint_collection.example.json",
            "validate_command": "python scripts/validate_route_templates.py",
        },
        "tips": [
            "先保顺序，再补坐标。起点、终点和中间途径点都要按真实导航顺序排列。",
            "如果暂时只有名称，不要编坐标；先保留 name，后续用部分坐标状态继续补采。",
            "采集完成后优先跑独立校验脚本，再决定是否回写 route_templates.json。",
        ],
    }


def get_route_waypoint_collection_api_payload(route_slug: str | None = None) -> dict[str, Any]:
    context = get_route_waypoint_collection_context(route_slug)
    return {
        "page": context["page"],
        "route_options": context["route_options"],
        "selected_route": context["selected_route"],
        "selected_route_seed": context["selected_route_seed"],
        "schema": context["schema"],
        "storage": context["storage"],
        "tips": context["tips"],
    }


def get_custom_plan_context() -> dict[str, Any]:
    return {
        "page_intro": {
            "title": "定制你的摩旅方案",
            "description": "适合第一次长途、多人同行、异地出发或不想自己反复做攻略的人。",
        },
        "service_points": [
            "每日路线安排",
            "关键点位建议",
            "风险提醒和行前清单",
        ],
        "custom_form": {
            "action": "/moto/custom",
            "method": "post",
            "fields": [
                {"name": "name", "label": "称呼", "type": "text", "value": ""},
                {"name": "contact", "label": "联系方式", "type": "text", "value": ""},
                {"name": "origin", "label": "出发地", "type": "text", "value": ""},
                {
                    "name": "trip_days",
                    "label": "计划天数",
                    "type": "select",
                    "value": "3",
                    "options": [
                        {"label": "2 天", "value": "2"},
                        {"label": "3 天", "value": "3"},
                        {"label": "5 天", "value": "5"},
                        {"label": "7 天", "value": "7"},
                    ],
                },
                {
                    "name": "bike_type",
                    "label": "车型",
                    "type": "select",
                    "value": "300-500cc",
                    "options": [
                        {"label": "150-250cc", "value": "150-250cc"},
                        {"label": "300-500cc", "value": "300-500cc"},
                        {"label": "500cc+", "value": "500cc+"},
                        {"label": "ADV / Touring", "value": "adv-touring"},
                    ],
                },
                {"name": "travel_dates", "label": "出发时间", "type": "text", "value": ""},
                {
                    "name": "budget_range",
                    "label": "预算范围",
                    "type": "select",
                    "value": "1000-2000",
                    "options": [
                        {"label": "500-1000", "value": "500-1000"},
                        {"label": "1000-2000", "value": "1000-2000"},
                        {"label": "2000-4000", "value": "2000-4000"},
                        {"label": "4000+", "value": "4000-plus"},
                    ],
                },
                {"name": "requirements", "label": "特殊要求", "type": "textarea", "value": ""},
            ],
            "submit_label": "提交定制需求",
            "footnote": "提交后我们会先判断你的行程条件，再联系你确认是否适合定制。",
        },
    }


def create_custom_plan_payload(form_data: Mapping[str, Any]) -> dict[str, str]:
    return {
        "name": str(form_data.get("name") or "未填写"),
        "contact": str(form_data.get("contact") or "未填写"),
        "origin": str(form_data.get("origin") or "未填写"),
        "trip_days": str(form_data.get("trip_days") or "未填写"),
        "bike_type": str(form_data.get("bike_type") or "未填写"),
        "travel_dates": str(form_data.get("travel_dates") or "未填写"),
        "budget_range": str(form_data.get("budget_range") or "未填写"),
        "requirements": str(form_data.get("requirements") or "未填写"),
    }


def build_plan_result(form_data: Mapping[str, Any]) -> dict[str, Any]:
    preferences = normalize_preferences(form_data)
    route = select_best_route(preferences, get_route_templates())
    daily_plan = build_daily_plan(route, preferences)
    total_distance = sum(day["distance_value"] for day in daily_plan)
    matched_spots = build_matched_spots(route, preferences)

    return {
        "plan_overview": {
            "title": build_route_title(preferences, route),
            "summary": build_route_summary(preferences, route),
            "stats": [
                {"label": "总里程", "value": f"约 {total_distance} km"},
                {"label": "推荐季节", "value": route["best_season"]},
                {"label": "整体强度", "value": difficulty_label(route["difficulty"])},
                {"label": "适合人群", "value": audience_label(preferences)},
            ],
        },
        "matched_spots": matched_spots,
        "daily_plan": [
            {
                "day": day["day"],
                "title": day["title"],
                "ride_time": day["ride_time"],
                "distance": f"约 {day['distance_value']} km",
                "highlights": day["highlights"],
                "note": day["note"],
            }
            for day in daily_plan
        ],
        "poi_groups": build_poi_groups(route, preferences),
        "warnings": build_warnings(route, preferences),
        "checklist_groups": build_checklist(preferences, route),
        "result_actions": [
            {"label": "保存这条路线", "href": "#"},
            {"label": "升级为定制规划", "href": "/moto/custom"},
            {"label": "重新调整条件", "href": "/moto/planner"},
        ],
        "related_routes": build_related_routes(route["slug"]),
    }


def build_routes_index_context(route_templates: list[dict[str, Any]], filters: Mapping[str, Any]) -> dict[str, Any]:
    selected_days = str(filters.get("days") or "").strip()
    route_slugs = [str(route.get("slug") or "") for route in route_templates]
    engagement_lookup = get_route_engagement_map(route_slugs)
    want_go_lookup = get_route_want_go_stats_map(route_slugs)
    day_options = [
        {"label": "全部", "value": ""},
        *[
            {"label": f"{days} 天", "value": str(days)}
            for days in sorted({int(route["days"]) for route in route_templates})
        ],
    ]
    filtered_routes = [
        route for route in route_templates
        if not selected_days or str(route["days"]) == selected_days
    ]
    filtered_routes.sort(
        key=lambda route: (
            -want_go_lookup.get(route["slug"], {}).get("total_count", 0),
            -engagement_lookup.get(route["slug"], {}).get("total_count", 0),
            -engagement_lookup.get(route["slug"], {}).get("navigation_count", 0),
            -engagement_lookup.get(route["slug"], {}).get("favorite_count", 0),
            route["title"],
        )
    )

    gpx_lookup = _build_gpx_lookup()

    return {
        "page": {
            "title": "热门摩旅路线库",
            "description": "先按骑行天数收窄路线，再决定继续规划还是直接导出到高德地图。",
        },
        "featured_summary": {
            "title": "路线列表",
            "description": (
                f"当前筛出 {len(filtered_routes)} 条路线，按热度排序"
                if selected_days
                else f"当前共整理 {len(route_templates)} 条可直接继续规划的路线模板，按热度排序。"
            ),
        },
        "filters": {
            "action": "/moto/routes",
            "selected_days": selected_days,
            "fields": [
                {
                    "name": "days",
                    "label": "天数",
                    "type": "select",
                    "value": selected_days,
                    "options": day_options,
                }
            ],
            "day_quick_filters": [
                {
                    "label": option["label"],
                    "value": option["value"],
                    "href": "/moto/routes" if not option["value"] else f"/moto/routes?days={option['value']}",
                    "is_active": option["value"] == selected_days,
                }
                for option in day_options
            ],
        },
        "routes": [
            _route_index_card(
                route,
                gpx_lookup=gpx_lookup,
                engagement_lookup=engagement_lookup,
                want_go_lookup=want_go_lookup,
            )
            for route in filtered_routes
        ],
        "empty_state": {
            "title": "暂时没有匹配路线",
            "description": "可以先试试路线规划工具，生成一份适合你的基础方案。",
            "action": {"label": "开始规划", "href": "/moto/planner"},
        },
    }


def _route_index_card(
    route: Mapping[str, Any],
    *,
    gpx_lookup: Mapping[str, Any] | None = None,
    engagement_lookup: Mapping[str, Mapping[str, int]] | None = None,
    want_go_lookup: Mapping[str, Mapping[str, int]] | None = None,
    use_cached_preview_polyline: bool = True,
) -> dict[str, Any]:
    slug = str(route["slug"])
    engagement = (
        dict(engagement_lookup.get(slug, {}))
        if isinstance(engagement_lookup, Mapping) and slug in engagement_lookup
        else get_route_engagement(slug)
    )
    want_go_stats = (
        dict(want_go_lookup.get(slug, {}))
        if isinstance(want_go_lookup, Mapping) and slug in want_go_lookup
        else get_route_want_go_stats(slug)
    )
    engagement["want_go_count"] = int(want_go_stats.get("total_count") or 0)
    navigation_waypoints = _route_navigation_waypoints(route)
    display_navigation_waypoints = [point for point in navigation_waypoints if not bool(point.get("route_only"))]
    if len(display_navigation_waypoints) < 2:
        display_navigation_waypoints = navigation_waypoints

    waypoints = [point["name"] for point in display_navigation_waypoints]
    waypoint_count = len(waypoints)
    coordinate_waypoint_count = sum(1 for point in display_navigation_waypoints if point["has_coordinates"])
    supports_coordinate_navigation = coordinate_waypoint_count > 0
    navigation_mode = _route_navigation_mode(navigation_waypoints)
    status_variant = _route_navigation_status_variant(navigation_mode)
    locked_amap_href = _route_navigation_locked_amap_href(route)
    configured_amap_app_href = _route_navigation_app_amap_href(route)
    if configured_amap_app_href:
        amap_export_href = configured_amap_app_href
    elif locked_amap_href:
        amap_export_href = _normalize_locked_amap_href(locked_amap_href, prefer_native=True)
    else:
        amap_export_href = _route_amap_export_href(navigation_waypoints, prefer_native=True)
    amap_browser_href = (
        _normalize_locked_amap_href(locked_amap_href, prefer_native=False)
        if locked_amap_href
        else _route_amap_export_href(navigation_waypoints, prefer_native=False)
    )
    tencent_export_href = _route_tencent_export_href(display_navigation_waypoints)
    tencent_app_href = _route_tencent_app_href(display_navigation_waypoints)
    cached_preview_points = _route_cached_preview_polyline_points(route) if use_cached_preview_polyline else []
    if len(cached_preview_points) >= 2:
        routed_polyline = {
            "points": cached_preview_points,
            "status": "cached-tencent-direction",
        }
    else:
        routed_polyline = _route_tencent_preview_polyline(navigation_waypoints)

    routed_polyline_points = routed_polyline.get("points", []) if isinstance(routed_polyline.get("points"), list) else []
    routed_polyline_status = str(routed_polyline.get("status") or "waypoint-straight-line").strip() or "waypoint-straight-line"

    # Locked routes still allow preview polyline rendering when Tencent returns a complete road path.
    # Only suppress preview when result indicates fallback/unreliable status.
    if locked_amap_href and (
        "segment-failed" in routed_polyline_status
        or "partial-fallback" in routed_polyline_status
        or routed_polyline_status in {
            "waypoint-straight-line",
            "request-failed",
            "missing-webservice-key",
            "insufficient-waypoints",
            "empty-polyline",
        }
        or routed_polyline_status.startswith("tencent-status-")
    ):
        routed_polyline_points = []
        routed_polyline_status = f"locked-amap-road-polyline-unavailable:{routed_polyline_status}"

    gpx_payload = _route_gpx_payload(route, navigation_waypoints, gpx_lookup=gpx_lookup)
    source_meta = _route_source_meta(route, gpx_payload=gpx_payload)
    tags = [f"{route['days']} 天", route["best_season"], difficulty_label(route["difficulty"])]
    if route.get("is_navigation_state_demo"):
        tags.insert(0, "状态演示")
    if gpx_payload["is_available"]:
        tags.insert(0, "GPX")
    return {
        "slug": slug,
        "title": route["title"],
        "summary": route["summary"],
        "cover_image_url": str(route.get("cover_image_url") or "").strip(),
        "tags": tags,
        "best_season": route["best_season"],
        "difficulty_label": difficulty_label(route["difficulty"]),
        "days": route["days"],
        "distance_km": route.get("distance_km", 0),
        "href": f"/moto/routes/{slug}",
        "mini_program_action": _mini_program_route_detail_action(slug),
        "replan_href": f"/moto/planner?route={slug}",
        "collect_href": f"/moto/routes/collect?route={slug}",
        "favorite_api_href": f"/api/moto/routes/{slug}/favorite",
        "navigation_api_href": f"/api/moto/routes/{slug}/navigation",
        "mini_program": {
            "replan": _mini_program_webview_action(f"/moto/planner?route={slug}"),
            "collect": _mini_program_webview_action(f"/moto/routes/collect?route={slug}"),
            "favorite": _mini_program_api_action(f"/moto/routes/{slug}/favorite"),
            "navigation": _mini_program_api_action(f"/moto/routes/{slug}/navigation"),
            "want_go": _mini_program_api_action(f"/moto/routes/{slug}/want-go"),
        },
        "engagement": engagement,
        "want_go": {
            "plan_bucket": "",
            "this_month_count": int(want_go_stats.get("this_month_count") or 0),
            "next_month_count": int(want_go_stats.get("next_month_count") or 0),
            "later_count": int(want_go_stats.get("later_count") or 0),
            "total_count": int(want_go_stats.get("total_count") or 0),
        },
        "is_navigation_state_demo": bool(route.get("is_navigation_state_demo")),
        "waypoints": waypoints,
        "navigation_waypoints": display_navigation_waypoints,
        "waypoint_count": waypoint_count,
        "amap_export": {
            "app_href": amap_export_href,
            "href": amap_export_href,
            "browser_href": amap_browser_href,
            "embed_href": f"/moto/routes/{slug}/amap-embed",
            "launch_href": f"/moto/routes/{slug}/amap-launch",
            "mini_program": {
                "navigate": _mini_program_webview_action(amap_export_href) if amap_export_href else {},
                "launch": _mini_program_webview_action(f"/moto/routes/{slug}/amap-launch") if amap_export_href else {},
                "browser": _mini_program_webview_action(amap_browser_href) if amap_browser_href else {},
                "interactive_map": _mini_program_webview_action(f"/moto/routes/{slug}/amap-embed"),
            },
            "label": "直接导航",
            "is_available": bool(amap_export_href),
            "screenshot_href": f"/moto/routes/{slug}/amap-route.svg",
            "waypoint_text": " -> ".join(waypoints),
            "waypoints": display_navigation_waypoints,
            "preview_polyline_points": routed_polyline_points,
            "preview_polyline_source": "tencent-direction" if routed_polyline_points else "unavailable",
            "preview_polyline_status": routed_polyline_status,
            "coordinate_waypoint_count": coordinate_waypoint_count,
            "supports_coordinate_navigation": supports_coordinate_navigation,
            "navigation_mode": navigation_mode,
            "status_variant": status_variant,
            "status_badge": _route_navigation_status_badge(status_variant),
            "status_text": _route_navigation_status_text(
                waypoint_count=waypoint_count,
                coordinate_waypoint_count=coordinate_waypoint_count,
                navigation_mode=navigation_mode,
            ),
        },
        "tencent_export": {
            "app_href": tencent_app_href,
            "href": tencent_export_href,
            "launch_href": f"/moto/routes/{slug}/tencent-launch",
            "mini_program": {
                "navigate": _mini_program_webview_action(f"/moto/routes/{slug}/tencent-launch") if tencent_export_href else {},
            },
            "label": "腾讯地图导航",
            "is_available": bool(tencent_export_href),
        },
        "gpx": gpx_payload,
        "source_meta": source_meta,
        "days_plan": [
            {
                "day": day["day"],
                "title": day["title"],
                "distance": day.get("distance", 0),
                "ride_time": day.get("ride_time", ""),
                "highlights": day.get("highlights", []),
                "note": day.get("note", ""),
            }
            for day in route.get("days_plan", [])
        ],
    }


def _route_source_meta(route: Mapping[str, Any], *, gpx_payload: Mapping[str, Any]) -> dict[str, str]:
    source_import = route.get("source_import") if isinstance(route.get("source_import"), Mapping) else {}

    label = str(gpx_payload.get("source_badge") or source_import.get("platform") or "路线模板").strip()
    author = str(gpx_payload.get("source_author") or _display_route_source_author(route.get("author") or source_import.get("author"))).strip()

    detail = ""
    if source_import:
        detail = str(source_import.get("source_keyword") or source_import.get("type") or source_import.get("platform") or "").strip()
    if not detail and gpx_payload.get("source_title"):
        detail = str(gpx_payload.get("source_title") or "").strip()

    return {
        "label": label,
        "author": author,
        "detail": detail,
    }


def _build_trip_advice(route: Mapping[str, Any], *, route_card: Mapping[str, Any]) -> dict[str, Any]:
    detail_for_whom = str(route.get("detail_for_whom") or "").strip()
    raw_notes = route.get("detail_notes") if isinstance(route.get("detail_notes"), list) else []
    notes = [str(item).strip() for item in raw_notes if str(item or "").strip()]

    comment = ""
    for candidate in notes:
        if candidate.startswith("内容摘要："):
            comment = candidate.removeprefix("内容摘要：").strip()
            break

    if not comment:
        for candidate in notes:
            if candidate.startswith("原始笔记："):
                continue
            comment = candidate
            break

    if not comment:
        comment = detail_for_whom or str(route.get("summary") or "").strip()

    suggestion_items = []
    if detail_for_whom:
        suggestion_items.append(detail_for_whom)
    for note in notes:
        if note.startswith("内容摘要：") or note.startswith("原始笔记："):
            continue
        if note == comment or note in suggestion_items:
            continue
        suggestion_items.append(note)

    source_meta = route_card.get("source_meta") if isinstance(route_card.get("source_meta"), Mapping) else {}
    source_line = ""
    label = str(source_meta.get("label") or "").strip()
    author = str(source_meta.get("author") or "").strip()
    if label and author:
        source_line = f"{label} · {author}"
    else:
        source_line = label or author

    return {
        "title": "行途建议",
        "comment": comment,
        "items": suggestion_items[:3],
        "source_line": source_line,
    }


def _build_gpx_lookup() -> dict[str, dict[str, Any]]:
    files_by_name = {
        str(file_info.get("name") or "").strip(): file_info
        for file_info in gpx_service.get_gpx_files()
        if str(file_info.get("name") or "").strip()
    }
    videos_by_filename: dict[str, dict[str, Any]] = {}
    for route_record in gpx_service.get_processed_route_records(limit=500):
        filename = _gpx_basename(route_record.get("gpx_path") or route_record.get("path") or route_record.get("name"))
        if filename and filename not in videos_by_filename:
            videos_by_filename[filename] = route_record
    for video in gpx_service.get_processed_videos(limit=500):
        filename = _gpx_basename(video.get("gpx_path") or video.get("path") or video.get("name"))
        if filename and filename not in videos_by_filename:
            videos_by_filename[filename] = video
    return {"files_by_name": files_by_name, "videos_by_filename": videos_by_filename}


def _route_gpx_payload(
    route: Mapping[str, Any],
    navigation_waypoints: list[Mapping[str, Any]],
    *,
    gpx_lookup: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    filename = str(route.get("gpx_file") or "").strip()
    if not filename:
        return {
            "is_available": False,
            "filename": "",
            "download_href": "",
            "download_label": "GPX 文件下载",
            "source_badge": "",
            "source_title": "",
            "source_author": "",
            "processed_at": "",
            "updated_at": "",
            "file_size": "",
            "track_point_count": 0,
            "extracted_spots_count": 0,
            "meta_text": "",
            "facts": [],
        }

    lookup = gpx_lookup or _build_gpx_lookup()
    file_info = lookup.get("files_by_name", {}).get(filename, {}) if isinstance(lookup, Mapping) else {}
    video_info = lookup.get("videos_by_filename", {}).get(filename, {}) if isinstance(lookup, Mapping) else {}
    source_title = str(video_info.get("title") or route.get("title") or filename.removesuffix(".gpx")).strip()
    source_author = _display_route_source_author(video_info.get("author"))
    processed_at = _format_gpx_timestamp(video_info.get("processed_at"))
    updated_at = _format_gpx_timestamp(file_info.get("mtime"))
    file_size = _format_gpx_file_size(file_info.get("size"))
    extracted_spots_count = int(video_info.get("spots_count") or 0)
    track_point_count = len(navigation_waypoints)
    source_badge = _route_gpx_source_badge(video_info, extracted_spots_count=extracted_spots_count)

    meta_parts = []
    if track_point_count:
        meta_parts.append(f"{track_point_count} 个轨迹点")
    if extracted_spots_count:
        meta_parts.append(f"{extracted_spots_count} 个提取点")
    if source_author:
        meta_parts.append(source_author)

    facts = [{"label": "文件名", "value": filename}]
    if source_badge:
        facts.append({"label": "来源类型", "value": source_badge})
    if file_size:
        facts.append({"label": "文件大小", "value": file_size})
    if updated_at:
        facts.append({"label": "文件更新时间", "value": updated_at})
    if source_author:
        facts.append({"label": "来源作者", "value": source_author})
    if processed_at:
        facts.append({"label": "提取时间", "value": processed_at})
    if extracted_spots_count:
        facts.append({"label": "提取点位", "value": str(extracted_spots_count)})

    return {
        "is_available": True,
        "filename": filename,
        "download_href": f"/api/moto/routes/{quote(str(route.get('slug') or '').strip())}/gpx",
        "mini_program": {
            "download": _mini_program_download_action(f"/api/moto/routes/{quote(str(route.get('slug') or '').strip())}/gpx"),
        },
        "download_label": "GPX 文件下载",
        "source_badge": source_badge,
        "source_title": source_title,
        "source_author": source_author,
        "processed_at": processed_at,
        "updated_at": updated_at,
        "file_size": file_size,
        "track_point_count": track_point_count,
        "extracted_spots_count": extracted_spots_count,
        "meta_text": " · ".join(meta_parts),
        "facts": facts,
    }


def _route_gpx_source_badge(video_info: Mapping[str, Any], *, extracted_spots_count: int) -> str:
    source_channel = str(video_info.get("source_channel") or "").strip().lower()
    qualification_status = str(video_info.get("qualification_status") or "").strip().lower()
    author = str(video_info.get("author") or "").strip()

    if source_channel in {"local-free-video-route-analysis", "douyin-gpx-generator"}:
        return "视频提取"
    if "openclaw" in source_channel:
        return "GPX 导入"
    if qualification_status == "qualified" and (extracted_spots_count > 0 or author):
        return "视频提取"
    if video_info:
        return "GPX 导入"
    return ""


def _display_route_source_author(value: Any) -> str:
    author = str(value or "").strip().lstrip("@")
    return f"@{author}" if author else ""


def _gpx_basename(path_value: Any) -> str:
    raw = str(path_value or "").strip()
    if not raw:
        return ""
    return re.split(r"[\\/]", raw)[-1].strip()


def _format_gpx_timestamp(value: Any) -> str:
    if value in {None, ""}:
        return ""
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value).strftime("%Y-%m-%d %H:%M")

    text = str(value).strip()
    if not text:
        return ""

    normalized = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return text[:16]


def _format_gpx_file_size(size: Any) -> str:
    try:
        value = float(size)
    except (TypeError, ValueError):
        return ""

    if value < 1024:
        return f"{int(value)} B"
    if value < 1024 * 1024:
        return f"{value / 1024:.1f} KB"
    return f"{value / (1024 * 1024):.1f} MB"


def _route_navigation_waypoints(route: Mapping[str, Any]) -> list[dict[str, Any]]:
    locked_amap_href = _route_navigation_locked_amap_href(route)
    if locked_amap_href:
        locked_waypoints = _parse_locked_amap_waypoints(locked_amap_href)
        if len(locked_waypoints) >= 2:
            return locked_waypoints

    navigation_config = route.get("navigation") if isinstance(route.get("navigation"), Mapping) else {}
    raw_navigation_waypoints = (
        navigation_config.get("waypoints", [])
        or route.get("navigation_waypoints", [])
        or route.get("waypoints", [])
    )

    if raw_navigation_waypoints:
        normalized_points = [
            point
            for point in (_normalize_route_navigation_point(raw_point) for raw_point in raw_navigation_waypoints)
            if point is not None
        ]
        if normalized_points:
            return normalized_points

    # GPX waypoints are fallback only. Admin-edited waypoints should be authoritative.
    gpx_file = str(route.get("gpx_file") or "").strip()
    if gpx_file:
        gpx_waypoints = gpx_service.get_gpx_waypoints(gpx_file)
        if len(gpx_waypoints) >= 2:
            return gpx_waypoints

    ordered_names: list[str] = []
    points_by_name: dict[str, dict[str, Any]] = {}

    for raw_point in raw_navigation_waypoints:
        _merge_route_navigation_point(points_by_name, ordered_names, raw_point)

    for day in route.get("days_plan", []):
        raw_day_waypoints = day.get("waypoints", [])
        if raw_day_waypoints:
            for raw_point in raw_day_waypoints:
                _merge_route_navigation_point(points_by_name, ordered_names, raw_point)
            continue

        title = str(day.get("title") or "")
        for raw_name in title.split("->"):
            _merge_route_navigation_point(points_by_name, ordered_names, raw_name.strip())

    return [points_by_name[name] for name in ordered_names]


def _parse_locked_amap_waypoints(href: str) -> list[dict[str, Any]]:
    raw = str(href or "").strip()
    if not raw:
        return []

    try:
        parsed = urlsplit(raw)
    except Exception:
        return []

    query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
    if not query_pairs:
        return []

    query_map: dict[str, str] = {}
    for key, value in query_pairs:
        if key:
            query_map[key] = value

    # amap /dir format: from[name], from[lnglat], via[i][name], via[i][lnglat], to[name], to[lnglat]
    start = _amap_query_point(query_map.get("from[name]"), query_map.get("from[lnglat]"))
    destination = _amap_query_point(query_map.get("to[name]"), query_map.get("to[lnglat]"))

    via_by_index: dict[int, dict[str, str]] = {}
    for key, value in query_pairs:
        match = re.match(r"^via\[(\d+)\]\[(name|lnglat)\]$", key)
        if not match:
            continue
        index = int(match.group(1))
        field = match.group(2)
        bucket = via_by_index.setdefault(index, {})
        bucket[field] = value

    via_points = [
        _amap_query_point(via_by_index[index].get("name"), via_by_index[index].get("lnglat"))
        for index in sorted(via_by_index)
    ]
    via_points = [point for point in via_points if point is not None]

    # amap m.amap.com/carmap format: saddr / maddr / daddr where each point is "lng,lat,name"
    if start is None and "saddr" in query_map:
        start = _amap_carmap_point(query_map.get("saddr"))
    if destination is None and "daddr" in query_map:
        destination = _amap_carmap_point(query_map.get("daddr"))
    if not via_points and "maddr" in query_map:
        raw_maddr = str(query_map.get("maddr") or "")
        via_points = [
            point
            for point in (_amap_carmap_point(segment) for segment in raw_maddr.split("|"))
            if point is not None
        ]

    points: list[dict[str, Any]] = []
    if start is not None:
        points.append(start)
    points.extend(via_points)
    if destination is not None:
        points.append(destination)
    return points


def _amap_query_point(name: Any, lnglat: Any) -> dict[str, Any] | None:
    normalized_name, route_only = _route_waypoint_name_and_flags(name)
    coords = _parse_amap_lnglat(lnglat)
    if coords is None and not normalized_name:
        return None

    if coords is None:
        return {
            "name": normalized_name or "途径点",
            "lat": None,
            "lng": None,
            "has_coordinates": False,
            "route_only": route_only,
        }

    lng, lat = coords
    return {
        "name": normalized_name or f"{lng:.6f},{lat:.6f}",
        "lat": lat,
        "lng": lng,
        "has_coordinates": True,
        "route_only": route_only,
    }


def _amap_carmap_point(raw_value: Any) -> dict[str, Any] | None:
    text = str(raw_value or "").strip()
    if not text:
        return None
    parts = [part.strip() for part in text.split(",")]
    if len(parts) < 2:
        return None

    coords = _parse_amap_lnglat(",".join(parts[:2]))
    name = parts[2] if len(parts) >= 3 else ""
    return _amap_query_point(name, f"{parts[0]},{parts[1]}") if coords is not None else None


def _parse_amap_lnglat(raw_value: Any) -> tuple[float, float] | None:
    text = str(raw_value or "").strip()
    if not text:
        return None

    parts = [part.strip() for part in text.split(",") if part.strip()]
    if len(parts) != 2:
        return None

    try:
        lng = float(parts[0])
        lat = float(parts[1])
    except ValueError:
        return None

    if not _is_valid_coordinate(lat, lng):
        return None
    return (lng, lat)


def _route_cached_preview_polyline_points(route: Mapping[str, Any]) -> list[dict[str, float]]:
    navigation_config = route.get("navigation") if isinstance(route.get("navigation"), Mapping) else {}
    raw_points = navigation_config.get("preview_polyline_points") if isinstance(navigation_config, Mapping) else []
    if not isinstance(raw_points, list):
        return []

    points: list[dict[str, float]] = []
    for item in raw_points:
        if not isinstance(item, Mapping):
            continue
        try:
            lat = float(item.get("lat"))
            lng = float(item.get("lng"))
        except (TypeError, ValueError):
            continue
        if not _is_valid_coordinate(lat, lng):
            continue
        points.append({"lat": lat, "lng": lng})
    return points


def _route_gpx_preview_polyline_points(route: Mapping[str, Any]) -> list[dict[str, float]]:
    filename = str(route.get("gpx_file") or "").strip()
    if not filename:
        return []

    raw_points = gpx_service.get_gpx_track_polyline(filename, max_points=2200)
    if not isinstance(raw_points, list):
        return []

    points: list[dict[str, float]] = []
    for item in raw_points:
        if not isinstance(item, Mapping):
            continue
        try:
            lat = float(item.get("lat"))
            lng = float(item.get("lng"))
        except (TypeError, ValueError):
            continue
        if not _is_valid_coordinate(lat, lng):
            continue
        points.append({"lat": lat, "lng": lng})
    return points


def _route_tencent_preview_polyline(waypoints: list[Mapping[str, Any]]) -> dict[str, Any]:
    coordinate_points = [
        {
            "lat": float(point.get("lat")),
            "lng": float(point.get("lng")),
        }
        for point in waypoints
        if point.get("has_coordinates") and point.get("lat") is not None and point.get("lng") is not None
    ]
    if len(coordinate_points) < 2:
        return {"points": [], "status": "insufficient-waypoints"}

    tencent_key = _tencent_route_service_key()
    if not tencent_key:
        return {"points": [], "status": "missing-webservice-key"}

    digest_input = json.dumps(coordinate_points, ensure_ascii=False, separators=(",", ":"))
    cache_key = hashlib.sha1(digest_input.encode("utf-8")).hexdigest()
    try:
        return _fetch_tencent_route_polyline_cached_success(cache_key, digest_input, tencent_key)
    except Exception:
        # Unstable responses (rate limit / partial fallback) should not be sticky-cached.
        return _fetch_tencent_route_polyline_uncached(digest_input, tencent_key)


@lru_cache(maxsize=256)
def _fetch_tencent_route_polyline_cached_success(cache_key: str, serialized_points: str, tencent_key: str) -> dict[str, Any]:
    del cache_key
    result = _fetch_tencent_route_polyline_uncached(serialized_points, tencent_key)
    status = str(result.get("status") or "").strip()
    has_points = isinstance(result.get("points"), list) and len(result.get("points") or []) >= 2
    is_stable_success = status == "tencent-direction-segmented" and has_points
    if not is_stable_success:
        raise RuntimeError(f"unstable-polyline:{status or 'unknown'}")
    return result


def _fetch_tencent_route_polyline_uncached(serialized_points: str, tencent_key: str) -> dict[str, Any]:
    try:
        coordinate_points = json.loads(serialized_points)
    except json.JSONDecodeError:
        return {"points": [], "status": "invalid-points-json"}
    if not isinstance(coordinate_points, list) or len(coordinate_points) < 2:
        return {"points": [], "status": "insufficient-waypoints"}

    merged_points: list[dict[str, float]] = []
    for index in range(len(coordinate_points) - 1):
        start = coordinate_points[index]
        end = coordinate_points[index + 1]
        segment_result = _fetch_tencent_segment_polyline(start, end, tencent_key)
        segment_points = segment_result.get("points") if isinstance(segment_result.get("points"), list) else []
        segment_status = str(segment_result.get("status") or "request-failed").strip() or "request-failed"
        if len(segment_points) < 2:
            # Never synthesize straight-line fallback segments: they visibly drift away from actual roads.
            return {
                "points": [],
                "status": f"tencent-direction-segment-failed-{index + 1}:{segment_status}",
            }

        if merged_points and merged_points[-1] == segment_points[0]:
            merged_points.extend(segment_points[1:])
        else:
            merged_points.extend(segment_points)

    if len(merged_points) >= 2:
        return {"points": _downsample_polyline(merged_points, max_points=2200), "status": "tencent-direction-segmented"}
    return {"points": [], "status": "empty-polyline"}


def _fetch_tencent_segment_polyline(start: Mapping[str, Any], end: Mapping[str, Any], tencent_key: str) -> dict[str, Any]:
    params = {
        "from": f"{start['lat']},{start['lng']}",
        "to": f"{end['lat']},{end['lng']}",
        "output": "json",
        "key": tencent_key,
    }

    payload = _fetch_tencent_route_payload(params)
    if not isinstance(payload, Mapping):
        return {"points": [], "status": "request-failed"}

    raw_status = payload.get("status")
    try:
        response_status = int(raw_status)
    except (TypeError, ValueError):
        response_status = -1
    if response_status != 0:
        response_message = str(payload.get("message") or "").strip().lower()
        if "webserviceapi" in response_message and "未开启" in str(payload.get("message") or ""):
            return {"points": [], "status": "tencent-webservice-disabled"}
        return {"points": [], "status": f"tencent-status-{response_status}"}

    result = payload.get("result") if isinstance(payload.get("result"), Mapping) else {}
    routes = result.get("routes") if isinstance(result.get("routes"), list) else []
    if not routes:
        return {"points": [], "status": "empty-route"}

    first_route = routes[0] if isinstance(routes[0], Mapping) else {}
    raw_polyline = first_route.get("polyline")
    decoded_points = _decode_tencent_polyline(raw_polyline)
    if len(decoded_points) >= 2:
        return {"points": decoded_points, "status": "tencent-direction"}

    steps = first_route.get("steps") if isinstance(first_route.get("steps"), list) else []
    merged_points: list[dict[str, float]] = []
    for step in steps:
        if not isinstance(step, Mapping):
            continue
        step_points = _decode_tencent_polyline(step.get("polyline"))
        if not step_points:
            continue
        if merged_points and merged_points[-1] == step_points[0]:
            merged_points.extend(step_points[1:])
        else:
            merged_points.extend(step_points)

    if len(merged_points) >= 2:
        return {"points": merged_points, "status": "tencent-direction"}
    return {"points": [], "status": "empty-polyline"}


def _fetch_tencent_route_payload(params: Mapping[str, str]) -> Mapping[str, Any] | None:
    payload: dict[str, Any] | None = None
    for scheme in ("https", "http"):
        request_url = f"{scheme}://apis.map.qq.com/ws/direction/v1/driving/?{urlencode(dict(params))}"
        try:
            with urlopen(request_url, timeout=3) as response:
                payload = json.loads(response.read().decode("utf-8"))
            break
        except Exception:
            continue
    return payload


def _decode_tencent_polyline(raw_polyline: Any) -> list[dict[str, float]]:
    if isinstance(raw_polyline, str):
        text = raw_polyline.strip()
        if not text:
            return []
        points: list[dict[str, float]] = []
        for segment in text.split(";"):
            segment = segment.strip()
            if not segment:
                continue
            pair = [part.strip() for part in segment.split(",") if part.strip()]
            if len(pair) != 2:
                continue
            try:
                lat = float(pair[0])
                lng = float(pair[1])
            except ValueError:
                continue
            if _is_valid_coordinate(lat, lng):
                points.append({"lat": lat, "lng": lng})
        return points

    if not isinstance(raw_polyline, list):
        return []
    numeric_values = [value for value in raw_polyline if isinstance(value, int | float)]
    if len(numeric_values) < 4:
        return []

    plain_points = _polyline_values_to_points([float(value) for value in numeric_values])
    decoded_values = [float(value) for value in numeric_values]
    if abs(decoded_values[0]) > 180 or abs(decoded_values[1]) > 180:
        decoded_values[0] = decoded_values[0] / 1000000.0
        decoded_values[1] = decoded_values[1] / 1000000.0
    for index in range(2, len(decoded_values)):
        decoded_values[index] = decoded_values[index - 2] + (decoded_values[index] / 1000000.0)
    compressed_points = _polyline_values_to_points(decoded_values)

    # Tencent driving polyline is usually compressed. Prefer the smoother candidate,
    # but keep a safe fallback for unusual payloads.
    compressed_score = _polyline_candidate_score(compressed_points)
    plain_score = _polyline_candidate_score(plain_points)
    if compressed_score >= plain_score:
        return compressed_points
    return plain_points


def _polyline_values_to_points(values: list[float]) -> list[dict[str, float]]:
    points: list[dict[str, float]] = []
    for index in range(0, len(values) - 1, 2):
        lat = values[index]
        lng = values[index + 1]
        if _is_valid_coordinate(lat, lng):
            points.append({"lat": lat, "lng": lng})
    return points


def _polyline_candidate_score(points: list[dict[str, float]]) -> float:
    if len(points) < 2:
        return float("-inf")

    long_jumps = 0
    max_jump = 0.0
    for index in range(1, len(points)):
        previous = points[index - 1]
        current = points[index]
        jump_km = _haversine_distance_km(previous["lat"], previous["lng"], current["lat"], current["lng"])
        max_jump = max(max_jump, jump_km)
        if jump_km > 8:
            long_jumps += 1

    return len(points) - (long_jumps * 80) - (max_jump * 3)


def _is_valid_coordinate(lat: float, lng: float) -> bool:
    return -90 <= lat <= 90 and -180 <= lng <= 180


def _downsample_polyline(points: list[dict[str, float]], *, max_points: int) -> list[dict[str, float]]:
    if len(points) <= max_points:
        return points
    step = max(1, math.ceil(len(points) / max_points))
    sampled = [points[index] for index in range(0, len(points), step)]
    if sampled[-1] != points[-1]:
        sampled.append(points[-1])
    return sampled[:max_points]


def _tencent_route_service_key() -> str:
    if has_app_context():
        return str(current_app.config.get("TENCENT_MAP_WEB_SERVICE_KEY") or "").strip()
    return ""


def _merge_route_navigation_point(
    points_by_name: dict[str, dict[str, Any]],
    ordered_names: list[str],
    raw_point: Any,
) -> None:
    point = _normalize_route_navigation_point(raw_point)
    if point is None:
        return

    name = point["name"]
    existing = points_by_name.get(name)
    if existing is None:
        points_by_name[name] = point
        ordered_names.append(name)
        return

    if not existing["has_coordinates"] and point["has_coordinates"]:
        existing["lat"] = point["lat"]
        existing["lng"] = point["lng"]
        existing["has_coordinates"] = True


def _normalize_route_navigation_point(raw_point: Any) -> dict[str, Any] | None:
    if isinstance(raw_point, str):
        name, route_only = _route_waypoint_name_and_flags(raw_point)
        if not name:
            return None
        return {"name": name, "lat": None, "lng": None, "has_coordinates": False, "route_only": route_only}

    if not isinstance(raw_point, Mapping):
        return None

    name, name_marked_route_only = _route_waypoint_name_and_flags(raw_point.get("name") or raw_point.get("title") or "")
    if not name:
        return None

    coordinates = raw_point.get("coordinates") if isinstance(raw_point.get("coordinates"), Mapping) else {}
    lat = _route_coordinate_value(raw_point.get("lat"), coordinates.get("lat"), coordinates.get("latitude"), raw_point.get("latitude"))
    lng = _route_coordinate_value(raw_point.get("lng"), coordinates.get("lng"), coordinates.get("lon"), coordinates.get("longitude"), raw_point.get("longitude"), raw_point.get("lon"))
    has_coordinates = lat is not None and lng is not None
    route_only = bool(raw_point.get("route_only")) or name_marked_route_only
    return {"name": name, "lat": lat, "lng": lng, "has_coordinates": has_coordinates, "route_only": route_only}


def _route_waypoint_name_and_flags(raw_name: Any) -> tuple[str, bool]:
    name = str(raw_name or "").strip()
    if not name:
        return "", False
    if name.startswith(ROUTE_ONLY_ANCHOR_PREFIX):
        stripped = name[len(ROUTE_ONLY_ANCHOR_PREFIX):].strip()
        return stripped or "途径点", True
    return name, False


def _route_coordinate_value(*values: Any) -> float | None:
    for value in values:
        if value in {None, ""}:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _route_navigation_mode(waypoints: list[Mapping[str, Any]]) -> str:
    if not waypoints:
        return "none"

    coordinate_waypoint_count = sum(1 for point in waypoints if point.get("has_coordinates"))
    if coordinate_waypoint_count == 0:
        return "names"
    if coordinate_waypoint_count == len(waypoints):
        return "coordinates"
    return "mixed"


def _route_navigation_status_text(*, waypoint_count: int, coordinate_waypoint_count: int, navigation_mode: str) -> str:
    if waypoint_count == 0:
        return ""
    if navigation_mode == "coordinates":
        return f"{coordinate_waypoint_count}/{waypoint_count} 个点已带坐标，可直接高德逐点导航"
    if navigation_mode == "mixed":
        return f"{coordinate_waypoint_count}/{waypoint_count} 个点已带坐标，将混合坐标和地点名称导航"
    return f"0/{waypoint_count} 个点带坐标，将按地点名称导航"


def _route_navigation_status_variant(navigation_mode: str) -> str:
    if navigation_mode == "coordinates":
        return "complete"
    if navigation_mode == "mixed":
        return "partial"
    return "names"


def _route_navigation_status_badge(status_variant: str) -> str:
    if status_variant == "complete":
        return "坐标完整"
    if status_variant == "partial":
        return "部分坐标"
    return "名称导航"


def _build_route_waypoint_collection_seed(route: Mapping[str, Any] | None) -> dict[str, Any]:
    if route is None:
        return {}

    route_card = _route_index_card(route)
    return {
        "route_slug": route["slug"],
        "route_title": route["title"],
        "collection_status": route_card["amap_export"]["status_variant"],
        "collection_notes": "",
        "source": {
            "channel": "manual-map-research",
            "reference_url": "",
            "operator": "",
        },
        "navigation": {
            "provider": "amap",
            "waypoints": [
                {
                    "name": point["name"],
                    "lng": point["lng"],
                    "lat": point["lat"],
                    "has_coordinates": point["has_coordinates"],
                }
                for point in route_card["navigation_waypoints"]
            ],
        },
        "missing_coordinate_waypoints": [
            point["name"]
            for point in route_card["navigation_waypoints"]
            if not point["has_coordinates"]
        ],
    }


def _route_amap_export_href(waypoints: list[Mapping[str, Any]], *, prefer_native: bool) -> str:
    if len(waypoints) < 2:
        return ""

    start = waypoints[0]
    destination = waypoints[-1]
    via_points = waypoints[1:-1]
    params = [
        "jm=1",
        "sort=tfc",
        f"saddr={quote(_route_amap_point_value(start))}",
        f"daddr={quote(_route_amap_point_value(destination))}",
    ]
    if via_points:
        # Encode all separators so maddr survives nested webview/browser handoff.
        params.append(f"maddr={quote('|'.join(_route_amap_point_value(point) for point in via_points))}")
    params.extend(["src=mypage", f"callnative={1 if prefer_native else 0}", "innersrc=uriapi"])
    return f"https://m.amap.com/navigation/carmap/{'&'.join(params)}"


def _route_tencent_export_href(waypoints: list[Mapping[str, Any]]) -> str:
    params = _route_tencent_export_params(waypoints)
    if not params:
        return ""
    return f"https://apis.map.qq.com/uri/v1/routeplan?{urlencode(params)}"


def _route_tencent_app_href(waypoints: list[Mapping[str, Any]]) -> str:
    params = _route_tencent_export_params(waypoints)
    if not params:
        return ""
    return f"qqmap://map/routeplan?{urlencode(params)}"


def _route_tencent_export_params(waypoints: list[Mapping[str, Any]]) -> list[tuple[str, str]]:
    coordinate_points = [
        point
        for point in waypoints
        if (
            not bool(point.get("route_only"))
            and point.get("has_coordinates")
            and point.get("lat") is not None
            and point.get("lng") is not None
        )
    ]
    if len(coordinate_points) < 2:
        coordinate_points = [
            point
            for point in waypoints
            if point.get("has_coordinates") and point.get("lat") is not None and point.get("lng") is not None
        ]
    if len(coordinate_points) < 2:
        return []

    start = coordinate_points[0]
    destination = coordinate_points[-1]
    via_points = _select_tencent_via_points(coordinate_points[1:-1], max_points=6)
    params: list[tuple[str, str]] = [
        ("type", "drive"),
        ("from", str(start.get("name") or "起点")),
        ("fromcoord", f"{float(start['lat'])},{float(start['lng'])}"),
        ("to", str(destination.get("name") or "终点")),
        ("tocoord", f"{float(destination['lat'])},{float(destination['lng'])}"),
        ("policy", "0"),
        ("referer", _tencent_uri_referer()),
    ]

    if via_points:
        via_names = ";".join(str(point.get("name") or "途径点") for point in via_points)
        via_coords = ";".join(f"{float(point['lat'])},{float(point['lng'])}" for point in via_points)
        # Tencent route URI is most stable with via names + viacoord coordinates.
        # Keep compatibility aliases for legacy containers.
        params.append(("via", via_names))
        params.append(("viacoord", via_coords))
        params.append(("waypoints", via_coords))
        params.append(("waypointcoords", via_coords))

    return params


def _select_tencent_via_points(points: list[Mapping[str, Any]], *, max_points: int) -> list[Mapping[str, Any]]:
    if max_points <= 0 or len(points) <= max_points:
        return list(points)

    if max_points == 1:
        return [points[len(points) // 2]]

    last_index = len(points) - 1
    step = last_index / (max_points - 1)
    selected_indexes: list[int] = []
    for index in range(max_points):
        source_index = int(round(index * step))
        source_index = max(0, min(last_index, source_index))
        if selected_indexes and source_index <= selected_indexes[-1]:
            source_index = min(last_index, selected_indexes[-1] + 1)
        selected_indexes.append(source_index)

    deduped_indexes: list[int] = []
    for source_index in selected_indexes:
        if not deduped_indexes or source_index != deduped_indexes[-1]:
            deduped_indexes.append(source_index)

    return [points[source_index] for source_index in deduped_indexes[:max_points]]


def _tencent_uri_referer() -> str:
    if has_app_context():
        value = str(current_app.config.get("TENCENT_MAP_URI_REFERER") or "").strip()
        if value:
            return value
    return "xingtu"


def _route_navigation_locked_amap_href(route: Mapping[str, Any]) -> str:
    navigation = route.get("navigation") if isinstance(route.get("navigation"), Mapping) else {}
    return str(navigation.get("amap_locked_href") or "").strip()


def _route_navigation_app_amap_href(route: Mapping[str, Any]) -> str:
    navigation = route.get("navigation") if isinstance(route.get("navigation"), Mapping) else {}
    return str(
        navigation.get("amap_app_href")
        or route.get("amap_app_href")
        or ""
    ).strip()


def _normalize_locked_amap_href(href: str, *, prefer_native: bool) -> str:
    raw = str(href or "").strip()
    if not raw:
        return ""

    try:
        parsed = urlsplit(raw)
    except Exception:
        return raw

    if not parsed.scheme or not parsed.netloc:
        return raw

    query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
    filtered_pairs = [(key, value) for key, value in query_pairs if key != "callnative"]
    filtered_pairs.append(("callnative", "1" if prefer_native else "0"))
    normalized_query = urlencode(filtered_pairs, doseq=True)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, normalized_query, parsed.fragment))


def _route_amap_point_value(point: Mapping[str, Any]) -> str:
    if point.get("has_coordinates") and point.get("lng") is not None and point.get("lat") is not None:
        return f"{point['lng']},{point['lat']},{point['name']}"
    return str(point.get("name") or "")


def render_route_amap_screenshot_svg(route: Mapping[str, Any]) -> str:
                route_card = _route_index_card(route)
                preview_waypoints = route_card["navigation_waypoints"][:6]
                path_d = _route_waypoint_preview_path(len(preview_waypoints))
                pins: list[str] = []
                labels: list[str] = []

                for index, point in enumerate(preview_waypoints):
                                x = 120 + index * (920 / max(len(preview_waypoints) - 1, 1))
                                y = 510 - (60 if index % 2 else 0)
                                pin_fill = "#d85f3d" if index in {0, len(preview_waypoints) - 1} else "#2f7fb2"
                                pins.append(
                                                f"<g transform='translate({x:.1f} {y:.1f})'>"
                                                f"<path d='M0 -34 C18 -34 32 -20 32 -2 C32 17 18 31 0 54 C-18 31 -32 17 -32 -2 C-32 -20 -18 -34 0 -34 Z' fill='{pin_fill}' stroke='#f8fbff' stroke-width='4' />"
                                                f"<circle cx='0' cy='-2' r='15' fill='#f8fbff' />"
                                                f"<text x='0' y='5' text-anchor='middle' fill='{pin_fill}' font-size='18' font-weight='700' font-family='Helvetica Neue, Arial, sans-serif'>{index + 1}</text>"
                                                f"</g>"
                                )
                                labels.append(
                                                f"<rect x='{x - 62:.1f}' y='{y + 58:.1f}' width='124' height='36' rx='18' fill='rgba(16,24,32,0.44)' />"
                                                f"<text x='{x:.1f}' y='{y + 82:.1f}' text-anchor='middle' fill='#f8fbff' font-size='20' font-family='Helvetica Neue, Arial, sans-serif'>{escape(point['name'])}</text>"
                                )

                return f"""<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 1200 720' role='img' aria-label='{escape(route_card['title'])} 高德路线截图'>
    <defs>
        <linearGradient id='routeBg' x1='0%' x2='100%' y1='0%' y2='100%'>
            <stop offset='0%' stop-color='#d9e7d7' />
            <stop offset='100%' stop-color='#eef3ea' />
        </linearGradient>
    </defs>
    <rect width='1200' height='720' rx='36' fill='url(#routeBg)' />
    <rect x='46' y='46' width='1108' height='628' rx='28' fill='rgba(248,251,255,0.84)' />
    <path d='M70 300 C220 210 350 220 490 305 S800 405 1130 240' fill='none' stroke='rgba(137,182,154,0.35)' stroke-width='110' stroke-linecap='round' />
    <path d='M104 382 C282 332 480 350 664 420 S972 520 1100 470' fill='none' stroke='rgba(170,212,193,0.32)' stroke-width='92' stroke-linecap='round' />
    <path d='M80 182 C240 260 440 240 620 148 S920 98 1118 168' fill='none' stroke='rgba(185,192,221,0.26)' stroke-width='74' stroke-linecap='round' />
    <path d='M80 542 L1120 542' fill='none' stroke='#d7dde3' stroke-width='20' stroke-linecap='round' />
    <path d='M120 132 L1040 132' fill='none' stroke='#d7dde3' stroke-width='12' stroke-dasharray='18 20' stroke-linecap='round' />
    <path d='M180 120 L310 610' fill='none' stroke='rgba(187,193,199,0.38)' stroke-width='10' stroke-linecap='round' />
    <path d='M520 94 L430 626' fill='none' stroke='rgba(187,193,199,0.35)' stroke-width='8' stroke-linecap='round' />
    <path d='M848 106 L986 604' fill='none' stroke='rgba(187,193,199,0.34)' stroke-width='8' stroke-linecap='round' />
    <text x='90' y='96' fill='#4a6375' font-size='28' font-family='Helvetica Neue, Arial, sans-serif' letter-spacing='3'>高德路线截图</text>
    <text x='90' y='168' fill='#183246' font-size='58' font-weight='700' font-family='Helvetica Neue, Arial, sans-serif'>{escape(route_card['title'])}</text>
    <foreignObject x='90' y='204' width='880' height='120'>
        <div xmlns='http://www.w3.org/1999/xhtml' style='color:#395466;font-size:28px;line-height:1.5;font-family:Helvetica Neue, Arial, sans-serif;'>
            {escape(route_card['amap_export']['status_text'] or '按当前途径点生成的高德路线截图')}
        </div>
    </foreignObject>
    <path d='{path_d}' fill='none' stroke='rgba(24,50,70,0.12)' stroke-width='28' stroke-linecap='round' stroke-linejoin='round' />
    <path d='{path_d}' fill='none' stroke='#ffffff' stroke-width='18' stroke-linecap='round' stroke-linejoin='round' />
    <path d='{path_d}' fill='none' stroke='#2f7fb2' stroke-width='9' stroke-linecap='round' stroke-linejoin='round' />
    {''.join(pins)}
    {''.join(labels)}
    <rect x='90' y='610' width='180' height='56' rx='28' fill='#e8edf1' />
    <text x='180' y='646' text-anchor='middle' fill='#1f4258' font-size='24' font-family='Helvetica Neue, Arial, sans-serif'>{escape(route_card['amap_export']['status_badge'])}</text>
    <text x='1110' y='648' text-anchor='end' fill='#557084' font-size='24' font-family='Helvetica Neue, Arial, sans-serif'>{escape(route_card['amap_export']['waypoint_text'])}</text>
</svg>"""


def _route_waypoint_preview_path(waypoint_count: int) -> str:
        if waypoint_count <= 1:
                return "M120 510 L1040 510"

        points: list[tuple[float, float]] = []
        span = 920 / max(waypoint_count - 1, 1)
        for index in range(waypoint_count):
                x = 120 + index * span
                y = 510 - (60 if index % 2 else 0)
                points.append((x, y))

        commands = [f"M{points[0][0]:.1f} {points[0][1]:.1f}"]
        for index in range(1, len(points)):
                prev_x, prev_y = points[index - 1]
                cur_x, cur_y = points[index]
                control_x = (prev_x + cur_x) / 2
                commands.append(f"Q{control_x:.1f} {prev_y:.1f} {cur_x:.1f} {cur_y:.1f}")
        return " ".join(commands)


def _build_route_detail_checkpoints(route: Mapping[str, Any], route_card: Mapping[str, Any]) -> list[dict[str, Any]]:
    configured_checkpoints = route.get("checkpoints") if isinstance(route.get("checkpoints"), list) else []
    normalized_configured: list[dict[str, Any]] = []
    for index, checkpoint in enumerate(configured_checkpoints):
        if not isinstance(checkpoint, Mapping):
            continue
        name = str(checkpoint.get("name") or "").strip() or f"打卡点{index + 1}"
        summary = str(checkpoint.get("summary") or "").strip() or "后台维护"
        timing = str(checkpoint.get("timing") or checkpoint.get("duration_text") or "").strip() or "后台维护"
        distance_text = str(checkpoint.get("distance_text") or checkpoint.get("distance") or "").strip()
        hit_count_text = str(checkpoint.get("hit_count_text") or "").strip()
        coordinates = checkpoint.get("coordinates") if isinstance(checkpoint.get("coordinates"), Mapping) else {}
        lat = _route_coordinate_value(checkpoint.get("lat"), checkpoint.get("latitude"), coordinates.get("lat"), coordinates.get("latitude"))
        lng = _route_coordinate_value(checkpoint.get("lng"), checkpoint.get("lon"), checkpoint.get("longitude"), coordinates.get("lng"), coordinates.get("lon"), coordinates.get("longitude"))
        item = {
            "name": name,
            "summary": summary,
            "timing": timing,
            "duration_text": timing,
            "distance_text": distance_text,
            "hit_count_text": hit_count_text,
            "image": str(checkpoint.get("image") or "route-checkpoint-placeholder.jpg").strip() or "route-checkpoint-placeholder.jpg",
        }
        if lat is not None:
            item["lat"] = lat
        if lng is not None:
            item["lng"] = lng
        normalized_configured.append(item)

    if normalized_configured:
        return normalized_configured

    navigation_waypoints = route_card.get("navigation_waypoints") if isinstance(route_card.get("navigation_waypoints"), list) else []
    generated_from_waypoints: list[dict[str, Any]] = []
    for index, waypoint in enumerate(navigation_waypoints):
        if not isinstance(waypoint, Mapping):
            continue
        name = str(waypoint.get("name") or "").strip() or f"打卡点{index + 1}"
        generated_from_waypoints.append(
            {
                "name": name,
                "summary": "后台维护",
                "timing": "后台维护",
                "duration_text": "后台维护",
                "distance_text": "",
                "hit_count_text": "",
                "image": "route-checkpoint-placeholder.jpg",
            }
        )

    return generated_from_waypoints


def build_route_detail_context(route: dict[str, Any]) -> dict[str, Any]:
    gpx_lookup = _build_gpx_lookup()
    route_card = _route_index_card(route, gpx_lookup=gpx_lookup, use_cached_preview_polyline=True)
    linked_spots = _build_route_linked_spots(route)
    import_assistant = build_navigation_import_assistant_payload(route_card)
    checkpoints = _build_route_detail_checkpoints(route, route_card)
    checkpoint_checkin_counts = get_route_checkpoint_checkin_counts(route.get("slug"), len(checkpoints))
    return {
        "page": {"title": route["title"], "eyebrow": "路线详情"},
        "route": {
            **route_card,
            "best_season": route["best_season"],
            "difficulty": difficulty_label(route["difficulty"]),
        },
        "detail_sections": {
            "highlights": route.get(
                "detail_highlights",
                [
                    "适合单人快速上线验证的模板化路线页",
                    "适合继续接数据库和真实点位数据",
                    "结构已经对齐规划结果页",
                ],
            ),
            "for_whom": route.get(
                "detail_for_whom",
                "适合想先做路线库和模板规划，再逐步扩展为定制服务的产品形态。",
            ),
            "notes": route.get(
                "detail_notes",
                [
                    "第一版详情页先用假数据承接结构。",
                    "下一步可以继续补每日行程和关键点位。",
                ],
            ),
            "trip_advice": _build_trip_advice(route, route_card=route_card),
            "daily_plan": [
                {
                    "day": day["day"],
                    "title": day["title"],
                    "ride_time": day["ride_time"],
                    "distance": f"约 {day['distance']} km",
                    "highlights": day["highlights"],
                    "note": day["note"],
                }
                for day in route["days_plan"]
            ],
            "checkpoints": [
                {
                    "name": checkpoint["name"],
                    "summary": checkpoint["summary"],
                    "timing": checkpoint["timing"],
                    "duration_text": str(checkpoint.get("duration_text") or checkpoint.get("timing") or "").strip(),
                    "distance_text": str(checkpoint.get("distance_text") or "").strip(),
                    "image_url": f"/static/{str(checkpoint.get('image') or 'route-checkpoint-placeholder.jpg').strip()}",
                    "lat": checkpoint.get("lat"),
                    "lng": checkpoint.get("lng"),
                    "hit_count": int(checkpoint_checkin_counts.get(index + 1) or 0),
                    "hit_count_text": (
                        str(checkpoint.get("hit_count_text") or "").strip()
                        or f"{int(checkpoint_checkin_counts.get(index + 1) or 0)}人打过卡"
                    ),
                }
                for index, checkpoint in enumerate(checkpoints)
            ],
            "linked_spots": linked_spots,
            "navigation_import_assistant": import_assistant,
            "poi_groups": build_poi_groups(
                route,
                {
                    "need_fuel_support": True,
                    "need_repair_support": True,
                    "need_lodging_support": True,
                },
            ),
        },
        "actions": [
            {"label": "按我的时间和车型重生成", "href": f"/moto/planner?route={route['slug']}"},
            {"label": "提交定制需求", "href": "/moto/custom"},
        ],
        "related_routes": [
            _route_index_card(candidate, gpx_lookup=gpx_lookup)
            for candidate in get_route_templates()
            if candidate["slug"] != route["slug"]
        ][:2],
    }


def _build_route_linked_spots(route: Mapping[str, Any]) -> list[dict[str, Any]]:
    spot_catalog = {
        str(spot.get("slug") or "").strip(): spot
        for spot in get_liaoning_moto_spots()
        if str(spot.get("slug") or "").strip()
    }

    linked_spots: list[dict[str, Any]] = []
    for raw_slug in route.get("spot_slugs", []) or []:
        slug = str(raw_slug or "").strip()
        if not slug:
            continue

        spot = spot_catalog.get(slug)
        if not spot:
            continue

        coordinates = spot.get("coordinates") if isinstance(spot.get("coordinates"), dict) else {}
        lat = coordinates.get("lat")
        lng = coordinates.get("lng")
        has_coordinates = isinstance(lat, (int, float)) and isinstance(lng, (int, float))
        source_items = spot.get("sources") if isinstance(spot.get("sources"), list) else []
        image_gallery = spot.get("image_gallery") if isinstance(spot.get("image_gallery"), list) else []

        linked_spots.append(
            {
                "slug": slug,
                "name": str(spot.get("name") or ""),
                "summary": str(spot.get("summary") or ""),
                "image_url": str((image_gallery[0] or {}).get("image_url") or "") if image_gallery else "",
                "support_tags": [str(tag) for tag in (spot.get("support_labels") or []) if str(tag).strip()],
                "coordinates": {
                    "lat": lat if has_coordinates else None,
                    "lng": lng if has_coordinates else None,
                    "has_coordinates": has_coordinates,
                    "text": f"{lat:.6f}, {lng:.6f}" if has_coordinates else "未维护坐标",
                },
                "sources": [
                    {
                        "type": str(item.get("type") or ""),
                        "name": str(item.get("name") or ""),
                        "verified": bool(item.get("verified")),
                        "note": str(item.get("note") or ""),
                    }
                    for item in source_items[:3]
                    if isinstance(item, dict)
                ],
            }
        )

    return linked_spots


def normalize_preferences(form_data: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "route_template": str(form_data.get("route_template") or "").strip(),
        "route_region": str(form_data.get("route_region") or "").strip(),
        "origin": str(form_data.get("origin") or "杭州").strip(),
        "trip_days": int(form_data.get("trip_days") or 2),
        "daily_distance": int(form_data.get("daily_distance") or 200),
        "experience_level": str(form_data.get("experience_level") or "beginner"),
        "bike_type": str(form_data.get("bike_type") or "300-500cc"),
        "budget_range": str(form_data.get("budget_range") or "1000-2000"),
        "must_visit_spots": get_multi_value(form_data, "must_visit_spots"),
        "route_preference": get_multi_value(form_data, "route_preference") or ["scenic", "relaxed"],
        "poi_types": get_multi_value(form_data, "poi_types") or ["fuel", "repair", "lodging", "viewpoint"],
    }


def get_multi_value(form_data: Mapping[str, Any], field_name: str) -> list[str]:
    getlist = getattr(form_data, "getlist", None)
    if callable(getlist):
        return [str(item) for item in getlist(field_name)]

    value = form_data.get(field_name)
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def select_best_route(preferences: Mapping[str, Any], routes: list[RouteDict]) -> RouteDict:
    route_slug = str(preferences.get("route_template") or "").strip()
    if route_slug:
        selected_route = next((route for route in routes if route["slug"] == route_slug), None)
        if selected_route is not None:
            return selected_route

    route_region = str(preferences.get("route_region") or "").strip()
    if route_region:
        regional_routes = [route for route in routes if route.get("region") == route_region]
        if regional_routes:
            routes = regional_routes

    scored_routes = [(score_route(route, preferences), route) for route in routes]
    scored_routes.sort(key=lambda item: item[0], reverse=True)
    return scored_routes[0][1]


def score_route(route: RouteDict, preferences: Mapping[str, Any]) -> int:
    score = 0
    day_gap = abs(route["days"] - preferences["trip_days"])
    score += max(0, 6 - day_gap * 2)

    if preferences["experience_level"] in route["experience_levels"]:
        score += 4
    if preferences["bike_type"] in route["bike_types"]:
        score += 3
    score += budget_score(route["budget_range"], str(preferences["budget_range"]))

    matched_preferences = set(preferences["route_preference"]) & set(route["scenery_type"])
    score += len(matched_preferences) * 3

    matched_spots = set(preferences.get("must_visit_spots", [])) & set(route.get("spot_slugs", []))
    score += len(matched_spots) * 4
    score += selected_spot_affinity_score(route, preferences)

    if preferences["daily_distance"] <= 200 and route["difficulty"] == "easy":
        score += 2
    if preferences["daily_distance"] >= 300 and route["difficulty"] == "medium":
        score += 2

    if preferences.get("route_region") and route.get("region") == preferences["route_region"]:
        score += 3

    return score


def selected_spot_affinity_score(route: RouteDict, preferences: Mapping[str, Any]) -> int:
    selected_spots = set(preferences.get("must_visit_spots", []))
    if not selected_spots:
        return 0

    catalog = {spot["slug"]: spot for spot in get_liaoning_moto_spots()}
    route_spots = set(route.get("spot_slugs", []))
    return sum(
        spot_route_affinity_score(catalog[slug], route)
        for slug in selected_spots
        if slug in catalog and slug not in route_spots
    )


def spot_route_affinity_score(spot: Mapping[str, Any], route: Mapping[str, Any]) -> int:
    score = 0

    if _spot_route_family(spot) == route.get("region"):
        score += 4

    matched_styles = _spot_route_styles(spot) & set(route.get("scenery_type", []))
    score += len(matched_styles) * 2

    ride_level = str(spot.get("ride_level") or "")
    if ride_level == "beginner" and route.get("difficulty") == "easy":
        score += 2
    elif ride_level in {"intermediate", "advanced"} and route.get("difficulty") == "medium":
        score += 2

    poi_types = set(route.get("pois", {}).keys())
    score += min(2, len(set(spot.get("support_role", [])) & poi_types))

    return score


def _spot_route_recommendation_reasons(spot: Mapping[str, Any], route: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []

    if _spot_route_family(spot) == route.get("region"):
        reasons.append("同属辽宁线，挂入后不需要改动区域逻辑")

    matched_styles = _spot_route_styles(spot) & set(route.get("scenery_type", []))
    if matched_styles:
        reasons.append(f"路线风格契合：{' / '.join(_route_style_label(item) for item in sorted(matched_styles))}")

    ride_level = str(spot.get("ride_level") or "")
    if ride_level == "beginner" and route.get("difficulty") == "easy":
        reasons.append("新手友好点位，适合挂到低强度模板")
    elif ride_level in {"intermediate", "advanced"} and route.get("difficulty") == "medium":
        reasons.append("骑行强度匹配，适合挂到进阶模板")

    support_overlap = set(spot.get("support_role", [])) & set(route.get("pois", {}).keys())
    if support_overlap:
        reasons.append(f"补给能力能承接模板需求：{' / '.join(SUPPORT_LABELS.get(item, item) for item in sorted(support_overlap))}")

    return reasons or ["点位属性与现有模板存在基础匹配，可作为候选补充点位"]


def _route_style_label(style: str) -> str:
    return {
        "coast": "海边",
        "mountain": "山路",
        "niche": "小众",
        "relaxed": "轻松",
        "scenic": "风景",
    }.get(style, style)


def _spot_route_family(spot: Mapping[str, Any]) -> str:
    region = str(spot.get("region") or "")
    return "north" if region.startswith("辽") else ""


def _spot_route_styles(spot: Mapping[str, Any]) -> set[str]:
    route_type = str(spot.get("route_type") or "")
    style_map = {
        "border-landmark": {"niche", "scenic"},
        "city-riverside": {"relaxed", "scenic"},
        "coast": {"coast", "relaxed", "scenic"},
        "coast-checkin": {"coast", "scenic"},
        "coast-city": {"coast", "relaxed", "scenic"},
        "coast-history": {"coast", "niche", "scenic"},
        "coast-scenic": {"coast", "scenic"},
        "county-road": {"niche", "scenic"},
        "mountain": {"mountain", "scenic"},
        "mountain-county-road": {"mountain", "niche", "scenic"},
        "mountain-landmark": {"mountain", "niche", "scenic"},
        "mountain-near-city": {"mountain", "relaxed", "scenic"},
        "mountain-scenic": {"mountain", "scenic"},
        "mountain-view": {"mountain", "scenic"},
        "plain-road": {"relaxed", "scenic"},
        "riverside-village": {"niche", "relaxed", "scenic"},
        "scenic-water": {"niche", "scenic"},
        "seasonal-landscape": {"niche", "scenic"},
        "supply-stop": {"relaxed"},
    }
    return style_map.get(route_type, {"scenic"})


def build_route_title(preferences: Mapping[str, Any], route: RouteDict) -> str:
    style_labels = {
        "mountain": "山路线",
        "coast": "海岸线",
        "scenic": "风景线",
        "relaxed": "轻松线",
        "niche": "小众路线",
    }
    style = next((style_labels[item] for item in preferences["route_preference"] if item in style_labels), "摩旅线")
    return f"{preferences['origin']}出发 {preferences['trip_days']} 天{style}"


def build_route_summary(preferences: Mapping[str, Any], route: RouteDict) -> str:
    preference_text = preference_label(preferences["route_preference"])
    spot_hint = ""
    matched_spots = matched_spot_names(route, preferences)
    if matched_spots:
        spot_hint = f" 已优先纳入你想去的打卡点：{'、'.join(matched_spots[:3])}。"
    return (
        f"基于你的出发地、天数和骑行偏好，当前优先匹配到“{route['title']}”这条模板路线。"
        f"整体更偏向{preference_text}，适合{audience_label(preferences)}。{spot_hint}"
    )


def build_daily_plan(route: RouteDict, preferences: Mapping[str, Any]) -> list[RouteDict]:
    daily_plan = []
    origin = preferences["origin"]

    for index, day in enumerate(route["days_plan"]):
        title = day["title"]
        if index == 0 and "->" in title:
            title = f"{origin}{title[title.find(' ->') :]}"
        if index == len(route["days_plan"]) - 1 and title.endswith("-> 杭州"):
            title = title[:-len("杭州")] + origin

        note = day["note"]
        if preferences["experience_level"] == "beginner":
            note += " 新手建议每 90 分钟安排一次短休息。"
        if "avoid_night" in preferences["route_preference"]:
            note += " 建议在日落前完成当天行程。"

        daily_plan.append(
            {
                "day": day["day"],
                "title": title,
                "ride_time": day["ride_time"],
                "distance_value": day["distance"],
                "highlights": day["highlights"],
                "note": note,
            }
        )

    return daily_plan


def build_poi_groups(route: RouteDict, preferences: Mapping[str, Any]) -> list[RouteDict]:
    poi_groups: list[RouteDict] = []
    pois = route.get("pois", {})

    poi_labels = {
        "fuel": "加油",
        "repair": "维修",
        "lodging": "住宿",
        "viewpoint": "观景",
        "emergency": "应急",
    }

    for poi_type in preferences.get("poi_types", []):
        if pois.get(poi_type):
            poi_groups.append({"label": poi_labels.get(str(poi_type), str(poi_type)), "items": pois[poi_type]})

    return poi_groups


def matched_spot_names(route: RouteDict, preferences: Mapping[str, Any]) -> list[str]:
    selected_spots = set(preferences.get("must_visit_spots", []))
    if not selected_spots:
        return []

    catalog = {spot["slug"]: spot["name"] for spot in get_liaoning_moto_spots()}
    return [catalog[slug] for slug in route.get("spot_slugs", []) if slug in selected_spots and slug in catalog]


def build_matched_spots(route: RouteDict, preferences: Mapping[str, Any]) -> list[RouteDict]:
    selected_spots = set(preferences.get("must_visit_spots", []))
    if not selected_spots:
        return []

    catalog = {spot["slug"]: spot for spot in get_liaoning_moto_spots()}
    return [
        {
            "href": f"/moto/spots/liaoning/{slug}",
            "name": catalog[slug]["name"],
            "city": catalog[slug]["city"],
            "summary": catalog[slug]["summary"],
            "recommended_stay": catalog[slug]["recommended_stay"],
            "photo_focus": catalog[slug]["photo_focus"],
        }
        for slug in route.get("spot_slugs", [])
        if slug in selected_spots and slug in catalog
    ]


def build_warnings(route: RouteDict, preferences: Mapping[str, Any]) -> list[str]:
    warnings = ["出发前请再次确认天气、施工和临时交通管制信息。"]

    if "mountain" in route["scenery_type"]:
        warnings.append("山区路段天气变化快，建议携带雨具和保暖层。")
    if "coast" in route["scenery_type"]:
        warnings.append("沿海道路风力和暴晒更明显，注意补水和防晒。")
    if preferences["experience_level"] == "beginner":
        warnings.append("新手尽量避免夜间骑行，控制单日节奏。")
    if preferences["daily_distance"] >= 300:
        warnings.append("连续长距离骑行更容易疲劳，建议增加中途休息。")

    return warnings


def build_checklist(preferences: Mapping[str, Any], route: RouteDict) -> list[RouteDict]:
    checklist = [
        {"title": "证件", "items": ["身份证", "驾驶证", "行驶证", "保险信息"]},
        {"title": "骑行装备", "items": ["头盔", "手套", "护具", "骑行服", "雨具"]},
        {"title": "工具补给", "items": ["充气泵", "补胎工具", "基础维修工具", "移动电源"]},
        {"title": "个人用品", "items": ["常用药", "饮水", "能量补给", "防晒用品"]},
    ]

    if "mountain" in route["scenery_type"]:
        checklist[3]["items"].append("保暖层")
    if "coast" in route["scenery_type"]:
        checklist[3]["items"].append("防晒袖套")
    if preferences["experience_level"] == "beginner":
        checklist[2]["items"].extend(["备用扎带", "胎压检查工具"])

    return checklist


def build_related_routes(route_slug: str) -> list[RouteDict]:
    return [
        {"title": route["title"], "href": f"/moto/routes/{route['slug']}"}
        for route in get_route_templates()
        if route["slug"] != route_slug
    ][:2]


def difficulty_label(level: str) -> str:
    return {
        "easy": "中低",
        "medium": "中等",
        "hard": "较高",
    }.get(level, "中等")


def apply_route_defaults(context: dict[str, Any], route: RouteDict, origin: str | None = None) -> None:
    average_distance = max(route["distance_km"] // route["days"], 1)
    default_distance = nearest_distance_bucket(average_distance)
    default_origin = (origin or infer_route_origin(route)).strip()

    for field in context["planner_form"]["fields"]:
        if field["name"] == "route_template":
            field["value"] = route["slug"]
        elif field["name"] == "route_region":
            field["value"] = route["region"]
        elif field["name"] == "origin":
            field["value"] = default_origin
        elif field["name"] == "trip_days":
            field["value"] = str(route["days"])
        elif field["name"] == "daily_distance":
            field["value"] = default_distance
        elif field["name"] == "experience_level":
            field["value"] = route["experience_levels"][0]
        elif field["name"] == "bike_type":
            field["value"] = route["bike_types"][0]
        elif field["name"] == "route_preference":
            field["value"] = route["scenery_type"]
        elif field["name"] == "must_visit_spots":
            field["value"] = route.get("spot_slugs", [])
        elif field["name"] == "budget_range":
            field["value"] = route["budget_range"]

    context["sample_trip"] = {
        "title": route["title"],
        "summary": route["summary"],
        "chips": [
            f"{route['days']} 天",
            f"{default_distance} km/天",
            route["best_season"],
            route["difficulty"],
        ],
    }
    context["selected_route"] = {
        "title": route["title"],
        "summary": route["summary"],
        "href": f"/moto/routes/{route['slug']}",
    }
    context["page_intro"]["description"] = (
        f"你正在基于“{route['title']}”这条模板路线做个性化重生成。"
        f"当前已预填推荐出发地：{default_origin}。可以继续调整预算和骑行偏好。"
    )


def nearest_distance_bucket(distance: int) -> str:
    buckets = [150, 200, 300, 400]
    return str(min(buckets, key=lambda item: abs(item - distance)))


def infer_route_origin(route: RouteDict) -> str:
    first_day = route.get("days_plan", [{}])[0]
    title = str(first_day.get("title") or "").strip()
    if "->" in title:
        return title.split("->", 1)[0].strip()
    return "杭州"


def budget_score(route_budget: str, preferred_budget: str) -> int:
    route_index = budget_index(route_budget)
    preferred_index = budget_index(preferred_budget)
    if route_index is None or preferred_index is None:
        return 0

    gap = abs(route_index - preferred_index)
    if gap == 0:
        return 3
    if gap == 1:
        return 1
    return 0


def budget_index(budget_range: str) -> int | None:
    budget_order = ["under-500", "500-1000", "1000-2000", "2000-4000", "4000-plus"]
    try:
        return budget_order.index(budget_range)
    except ValueError:
        return None


def audience_label(preferences: Mapping[str, Any]) -> str:
    return {
        "beginner": "首次或前几次摩旅用户",
        "intermediate": "有短途经验的骑手",
        "advanced": "有长途经验的骑手",
    }.get(str(preferences["experience_level"]), "摩旅用户")


def preference_label(preferences: list[str]) -> str:
    labels = {
        "mountain": "山路和弯道体验",
        "coast": "海边风景和轻松节奏",
        "scenic": "风景优先",
        "relaxed": "轻松节奏",
        "avoid_night": "少夜路安排",
        "niche": "相对小众的停靠点",
    }
    resolved = [labels[item] for item in preferences if item in labels]
    return "、".join(resolved[:2]) if resolved else "综合体验"