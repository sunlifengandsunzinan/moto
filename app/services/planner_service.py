from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import hashlib
from html import escape
import json
import math
import re
from typing import Any, Mapping
from urllib.parse import quote

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
from .route_templates_config import load_route_templates


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
            {"label": "开始规划", "href": "/moto/planner", "kind": "primary"},
            {"label": "录入点位", "href": "/moto/spots/collect", "kind": "secondary"},
        ],
        "filters": {
            "action": "/moto/spots",
            "reset_href": "/moto/spots",
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
            "action": {"label": "去录入点位", "href": "/moto/spots/collect"},
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
                "slug": "jiangzhehu-2-day",
                "title": "江浙沪 2 天轻松短途",
                "summary": "适合周末出发，节奏轻，适合 150cc-400cc 车型。",
                "tags": ["2 天", "轻松", "短途"],
                "href": "/moto/routes/jiangzhehu-2-day",
            },
            {
                "slug": "wannan-3-day",
                "title": "皖南 3 天入门山路线",
                "summary": "弯道和风景兼顾，适合有短途经验的骑手。",
                "tags": ["3 天", "山路", "入门"],
                "href": "/moto/routes/wannan-3-day",
            },
            {
                "slug": "hainan-5-day",
                "title": "环海南 5 天海岸线",
                "summary": "海景路线优先，适合冬春季节出行。",
                "tags": ["5 天", "海边", "经典"],
                "href": "/moto/routes/hainan-5-day",
            },
            {
                "slug": "liaoning-benhuan-3-day",
                "title": "辽宁 3 天本溪到绿江边境风景线",
                "summary": "跑山、江景和边境县道串在一起，适合辽宁省内经典摩旅。",
                "tags": ["3 天", "辽宁", "山水边境"],
                "href": "/moto/routes/liaoning-benhuan-3-day",
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
                **item,
                "is_active": item["key"] == active_tab,
            }
            for item in items
        ]
    }


def get_moto_me_context() -> dict[str, Any]:
    route_templates = get_route_templates()

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
            {"label": "路线模板", "value": len(route_templates)},
            {"label": "时长分档", "value": 4},
            {"label": "可直接导航", "value": len(route_templates)},
            {"label": "近期推荐", "value": min(3, len(route_templates))},
        ],
        "sections": [
            {
                "title": "常用功能",
                "items": [
                    {
                        "label": "开始路线规划",
                        "description": "按天数、车型和偏好生成基础行程。",
                        "href": "/moto/planner",
                    },
                    {
                        "label": "查看路线库",
                        "description": "按骑行时间快速切换路线，并直接跳转导航。",
                        "href": "/moto/routes",
                    },
                    {
                        "label": "提交定制需求",
                        "description": "如果不想自己筛路线，可以直接提交定制行程。",
                        "href": "/moto/custom",
                    },
                    {
                        "label": "采集导航点",
                        "description": "为路线补充经纬度、途径点顺序和来源备注。",
                        "href": "/moto/routes/collect",
                    },
                ],
            },
            {
                "title": "最近可继续",
                "items": [
                    {
                        "label": route["title"],
                        "description": route["summary"],
                        "href": f"/moto/routes/{route['slug']}",
                    }
                    for route in route_templates[:3]
                ],
            },
        ],
        "quick_actions": [
            {"label": "路线库", "href": "/moto/routes", "kind": "primary"},
            {"label": "定制需求", "href": "/moto/custom", "kind": "secondary"},
            {"label": "采集导航点", "href": "/moto/routes/collect", "kind": "secondary"},
        ],
    }


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
            "example": "jiangzhehu-2-day",
        },
        {
            "name": "route_title",
            "label": "路线标题",
            "required": True,
            "description": "保留采集时看到的路线名，方便人工核对。",
            "example": "江浙沪 2 天轻松短途",
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

    gpx_lookup = _build_gpx_lookup()

    return {
        "page": {
            "title": "热门摩旅路线库",
            "description": "先按骑行天数收窄路线，再决定继续规划还是直接导出到高德地图。",
        },
        "featured_summary": {
            "title": "路线列表",
            "description": (
                f"当前筛出 {len(filtered_routes)} 条路线"
                if selected_days
                else f"当前共整理 {len(route_templates)} 条可直接继续规划的路线模板。"
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
            _route_index_card(route, gpx_lookup=gpx_lookup)
            for route in filtered_routes
        ],
        "empty_state": {
            "title": "暂时没有匹配路线",
            "description": "可以先试试路线规划工具，生成一份适合你的基础方案。",
            "action": {"label": "开始规划", "href": "/moto/planner"},
        },
    }


def _route_index_card(route: Mapping[str, Any], *, gpx_lookup: Mapping[str, Any] | None = None) -> dict[str, Any]:
    navigation_waypoints = _route_navigation_waypoints(route)
    waypoints = [point["name"] for point in navigation_waypoints]
    waypoint_count = len(waypoints)
    coordinate_waypoint_count = sum(1 for point in navigation_waypoints if point["has_coordinates"])
    supports_coordinate_navigation = coordinate_waypoint_count > 0
    navigation_mode = _route_navigation_mode(navigation_waypoints)
    status_variant = _route_navigation_status_variant(navigation_mode)
    amap_export_href = _route_amap_export_href(navigation_waypoints)
    gpx_payload = _route_gpx_payload(route, navigation_waypoints, gpx_lookup=gpx_lookup)
    tags = [f"{route['days']} 天", route["best_season"], difficulty_label(route["difficulty"])]
    if route.get("is_navigation_state_demo"):
        tags.insert(0, "状态演示")
    if gpx_payload["is_available"]:
        tags.insert(0, "GPX")
    return {
        "slug": route["slug"],
        "title": route["title"],
        "summary": route["summary"],
        "tags": tags,
        "best_season": route["best_season"],
        "difficulty_label": difficulty_label(route["difficulty"]),
        "days": route["days"],
        "distance_km": route.get("distance_km", 0),
        "href": f"/moto/routes/{route['slug']}",
        "replan_href": f"/moto/planner?route={route['slug']}",
        "collect_href": f"/moto/routes/collect?route={route['slug']}",
        "is_navigation_state_demo": bool(route.get("is_navigation_state_demo")),
        "waypoints": waypoints,
        "navigation_waypoints": navigation_waypoints,
        "waypoint_count": waypoint_count,
        "amap_export": {
            "href": amap_export_href,
            "label": "导出到高德地图",
            "is_available": bool(amap_export_href),
            "screenshot_href": f"/moto/routes/{route['slug']}/amap-route.svg",
            "waypoint_text": " -> ".join(waypoints),
            "waypoints": navigation_waypoints,
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
        "gpx": gpx_payload,
        "days_plan": [
            {
                "day": day["day"],
                "title": day["title"],
                "distance": day["distance"],
            }
            for day in route.get("days_plan", [])
        ],
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
        "download_href": f"/api/moto/gpx/download/{quote(filename)}",
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
    gpx_file = str(route.get("gpx_file") or "").strip()
    if gpx_file:
        gpx_waypoints = gpx_service.get_gpx_waypoints(gpx_file)
        if len(gpx_waypoints) >= 2:
            return gpx_waypoints

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
        name = raw_point.strip()
        if not name:
            return None
        return {"name": name, "lat": None, "lng": None, "has_coordinates": False}

    if not isinstance(raw_point, Mapping):
        return None

    name = str(raw_point.get("name") or raw_point.get("title") or "").strip()
    if not name:
        return None

    coordinates = raw_point.get("coordinates") if isinstance(raw_point.get("coordinates"), Mapping) else {}
    lat = _route_coordinate_value(raw_point.get("lat"), coordinates.get("lat"), coordinates.get("latitude"), raw_point.get("latitude"))
    lng = _route_coordinate_value(raw_point.get("lng"), coordinates.get("lng"), coordinates.get("lon"), coordinates.get("longitude"), raw_point.get("longitude"), raw_point.get("lon"))
    has_coordinates = lat is not None and lng is not None
    return {"name": name, "lat": lat, "lng": lng, "has_coordinates": has_coordinates}


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


def _route_amap_export_href(waypoints: list[Mapping[str, Any]]) -> str:
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
        params.append(f"maddr={quote('|'.join(_route_amap_point_value(point) for point in via_points), safe='|')}")
    params.extend(["src=mypage", "callnative=0", "innersrc=uriapi"])
    return f"https://m.amap.com/navigation/carmap/{'&'.join(params)}"


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


def build_route_detail_context(route: dict[str, Any]) -> dict[str, Any]:
    gpx_lookup = _build_gpx_lookup()
    route_card = _route_index_card(route, gpx_lookup=gpx_lookup)
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
                    "image_url": f"/static/{checkpoint['image']}",
                }
                for checkpoint in route.get("checkpoints", [])
            ],
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