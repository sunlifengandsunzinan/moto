from __future__ import annotations

import json
from typing import Any, Mapping

from .liaoning_spots import (
    SUPPORT_LABELS,
    build_preview_spot_image_gallery,
    build_previewable_moto_spot_record,
    get_approved_moto_spots,
    get_empty_moto_spot_record,
    get_liaoning_moto_spots,
    get_moto_spot_collection_schema,
)
from .candidate_spots import candidate_to_collection_record, get_candidate_spot_by_slug, get_candidate_spots


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


def get_spot_collection_context(
    form_data: Mapping[str, Any] | None = None,
    candidate_slug: str | None = None,
    review_feedback: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    selected_candidate = get_candidate_spot_by_slug(candidate_slug) if candidate_slug else None
    record = (
        build_spot_collection_record(form_data)
        if form_data
        else candidate_to_collection_record(selected_candidate)
        if selected_candidate
        else get_empty_moto_spot_record()
    )
    preview_record = build_previewable_moto_spot_record(record)
    schema = get_moto_spot_collection_schema()
    groups = _collection_groups(schema, record)
    required_fields = [field for field in schema if field["required"]]
    missing_required = [field["label"] for field in required_fields if _is_missing(record, field["name"])]
    candidate_queue = [_candidate_card(item, candidate_slug) for item in get_candidate_spots()]

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
            "queue": candidate_queue,
            "feedback": review_feedback,
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
        "best_seasons",
        "best_time_of_day",
        "road_features",
        "risk_notes",
        "photo_focus",
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

    return {
        "page": {
            "title": "辽宁摩旅点位库",
            "description": "把打卡点、补给节点和适合串联的骑行地标放在同一张结构化清单里，方便先看点位再规划路线。",
        },
        "filters": {
            "action": "/moto/spots",
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
        },
        "stats": {
            "total": len(spots),
            "visible": len(filtered_spots),
            "regions": len({spot["region"] for spot in spots}),
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
    return {
        "name": spot["name"],
        "city": spot["city"],
        "region": spot["region"],
        "summary": spot["summary"],
        "route_type_label": spot["route_type_label"],
        "ride_level_label": spot["ride_level_label"],
        "season_labels": spot["season_labels"],
        "support_labels": spot["support_labels"],
        "best_time_of_day": spot["best_time_of_day"],
        "href": f"/moto/spots/liaoning/{spot['slug']}",
        "image_url": spot["image_gallery"][0]["image_url"],
    }


def get_home_context() -> dict[str, Any]:
    return {
        "nav": {
            "brand": "摩旅计划",
            "links": [
                {"label": "开始规划", "href": "/moto/planner"},
                {"label": "热门路线", "href": "/moto/routes"},
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
    return [
        {
            "slug": "jiangzhehu-2-day",
            "title": "江浙沪 2 天轻松短途",
            "region": "east",
            "spot_slugs": [],
            "days": 2,
            "difficulty": "easy",
            "scenery_type": ["scenic", "relaxed"],
            "bike_types": ["150-250cc", "300-500cc", "adv-touring"],
            "experience_levels": ["beginner", "intermediate"],
            "best_season": "春季 / 秋季",
            "distance_km": 320,
            "budget_range": "1000-2000",
            "summary": "适合周末出发，节奏轻，补给便利，适合城市周边摩旅。",
            "days_plan": [
                {
                    "day": 1,
                    "title": "杭州 -> 莫干山 -> 安吉",
                    "ride_time": "建议骑行 4-5 小时，含 2 次休息",
                    "distance": 170,
                    "highlights": ["山景道路", "补给便利", "适合新手"],
                    "note": "建议中午前进入山路，避免傍晚赶路。",
                },
                {
                    "day": 2,
                    "title": "安吉 -> 临安 -> 杭州",
                    "ride_time": "建议骑行 4 小时",
                    "distance": 150,
                    "highlights": ["返程轻松", "风景平衡", "路况稳定"],
                    "note": "返程前建议补油并检查胎压。",
                },
            ],
            "pois": {
                "fuel": [
                    {"name": "安吉城区加油站", "meta": "Day 1 · 下午补给"},
                    {"name": "临安北服务点", "meta": "Day 2 · 返程补给"},
                ],
                "repair": [
                    {"name": "安吉机车维修点", "meta": "Day 1 · 基础检查"},
                ],
                "lodging": [
                    {"name": "安吉骑手友好民宿", "meta": "Day 1 · 方便停车"},
                ],
                "viewpoint": [
                    {"name": "莫干山观景路段", "meta": "Day 1 · 建议停留"},
                ],
                "emergency": [
                    {"name": "安吉县医院急诊", "meta": "Day 1 · 紧急情况优先前往"},
                ],
            },
        },
        {
            "slug": "wannan-3-day",
            "title": "皖南 3 天入门山路线",
            "region": "east",
            "spot_slugs": [],
            "days": 3,
            "difficulty": "medium",
            "scenery_type": ["mountain", "scenic"],
            "bike_types": ["300-500cc", "500cc+", "adv-touring"],
            "experience_levels": ["intermediate", "advanced"],
            "best_season": "春季 / 秋季",
            "distance_km": 560,
            "budget_range": "1000-2000",
            "summary": "弯道和风景兼顾，适合有短途经验的骑手。",
            "days_plan": [
                {
                    "day": 1,
                    "title": "杭州 -> 宁国",
                    "ride_time": "建议骑行 5-6 小时，含 2 次休息",
                    "distance": 190,
                    "highlights": ["进山路段", "风景线", "补给充足"],
                    "note": "建议傍晚前进入住宿点。",
                },
                {
                    "day": 2,
                    "title": "宁国 -> 泾县 -> 黄山脚下",
                    "ride_time": "建议骑行 6 小时",
                    "distance": 210,
                    "highlights": ["弯道体验", "山景密集", "拍照点多"],
                    "note": "连续山路不建议疲劳骑行。",
                },
                {
                    "day": 3,
                    "title": "黄山脚下 -> 临安 -> 杭州",
                    "ride_time": "建议骑行 4-5 小时",
                    "distance": 160,
                    "highlights": ["返程轻松", "节奏回落", "补给稳定"],
                    "note": "返程前检查刹车和胎压。",
                },
            ],
            "pois": {
                "fuel": [
                    {"name": "宁国补给站", "meta": "Day 1 · 山路前补油"},
                    {"name": "泾县服务区", "meta": "Day 2 · 中段补给"},
                ],
                "repair": [
                    {"name": "宁国轮胎维修点", "meta": "Day 1 · 补胎和基础维护"},
                ],
                "lodging": [
                    {"name": "宁国城区民宿", "meta": "Day 1 · 方便停车"},
                    {"name": "黄山脚下客栈", "meta": "Day 2 · 适合早出发"},
                ],
                "viewpoint": [
                    {"name": "皖南山景观景台", "meta": "Day 2 · 建议停留 20 分钟"},
                ],
                "emergency": [
                    {"name": "宁国市人民医院", "meta": "Day 1 · 山路前应急保障"},
                ],
            },
        },
        {
            "slug": "hainan-5-day",
            "title": "环海南 5 天海岸线",
            "region": "south",
            "spot_slugs": [],
            "days": 5,
            "difficulty": "medium",
            "scenery_type": ["coast", "scenic", "relaxed"],
            "bike_types": ["150-250cc", "300-500cc", "adv-touring"],
            "experience_levels": ["beginner", "intermediate", "advanced"],
            "best_season": "冬季 / 春季",
            "distance_km": 780,
            "budget_range": "2000-4000",
            "summary": "海景路线优先，适合冬春季节出行。",
            "days_plan": [
                {
                    "day": 1,
                    "title": "海口 -> 文昌",
                    "ride_time": "建议骑行 4 小时",
                    "distance": 150,
                    "highlights": ["海边公路", "节奏轻松", "适合热身"],
                    "note": "注意海风和补水。",
                },
                {
                    "day": 2,
                    "title": "文昌 -> 琼海",
                    "ride_time": "建议骑行 4-5 小时",
                    "distance": 170,
                    "highlights": ["海景", "小众停靠点", "补给方便"],
                    "note": "中午高温时段建议休息。",
                },
                {
                    "day": 3,
                    "title": "琼海 -> 陵水",
                    "ride_time": "建议骑行 4-5 小时",
                    "distance": 160,
                    "highlights": ["海岸风景", "适合拍照", "路况平稳"],
                    "note": "沿海天气变化快。",
                },
                {
                    "day": 4,
                    "title": "陵水 -> 三亚",
                    "ride_time": "建议骑行 3-4 小时",
                    "distance": 120,
                    "highlights": ["轻松短日程", "海景优先", "适合休整"],
                    "note": "建议下午早些到达休整。",
                },
                {
                    "day": 5,
                    "title": "三亚 -> 东方 / 海口方向",
                    "ride_time": "建议骑行 5 小时",
                    "distance": 180,
                    "highlights": ["经典海岸线", "返程收尾", "风景完整"],
                    "note": "根据返程方式调整节奏。",
                },
            ],
            "pois": {
                "fuel": [
                    {"name": "文昌沿线加油点", "meta": "Day 1 · 海岸线补给"},
                    {"name": "陵水城区加油站", "meta": "Day 3 · 下午补给"},
                ],
                "repair": [
                    {"name": "三亚机车维修点", "meta": "Day 4 · 基础检修"},
                ],
                "lodging": [
                    {"name": "琼海海边民宿", "meta": "Day 2 · 停车方便"},
                    {"name": "三亚停车友好酒店", "meta": "Day 4 · 方便第二天返程"},
                ],
                "viewpoint": [
                    {"name": "东海岸观景点", "meta": "Day 2 · 建议日落前停留"},
                    {"name": "三亚海岸线", "meta": "Day 4 · 海边打卡"},
                ],
                "emergency": [
                    {"name": "陵水应急服务站", "meta": "Day 3 · 海岸线应急补给"},
                    {"name": "三亚中心医院", "meta": "Day 4 · 城市段紧急支援"},
                ],
            },
        },
        {
            "slug": "liaoning-benhuan-3-day",
            "title": "辽宁 3 天本溪到绿江边境风景线",
            "region": "north",
            "spot_slugs": [
                "benhuan-highway",
                "huanren-county",
                "qingshangou",
                "lujiang-village",
                "dandong-yalu-river",
            ],
            "days": 3,
            "difficulty": "medium",
            "scenery_type": ["mountain", "scenic", "niche"],
            "bike_types": ["150-250cc", "300-500cc", "500cc+", "adv-touring"],
            "experience_levels": ["intermediate", "advanced"],
            "best_season": "夏季 / 秋季",
            "distance_km": 680,
            "budget_range": "1000-2000",
            "summary": "从沈阳出发，串起本桓公路、桓仁、青山沟、绿江村和丹东，适合 2-3 天的辽宁省内经典摩旅。",
            "days_plan": [
                {
                    "day": 1,
                    "title": "沈阳 -> 本溪 -> 本桓公路 -> 桓仁",
                    "ride_time": "建议骑行 5-6 小时，含 2 次山路休息",
                    "distance": 260,
                    "highlights": ["本桓公路弯道", "本溪山景", "桓仁过夜补给"],
                    "note": "建议上午从沈阳出发，中午前进入本溪山区，避免傍晚连续压弯。",
                },
                {
                    "day": 2,
                    "title": "桓仁 -> 青山沟 -> 宽甸",
                    "ride_time": "建议骑行 4-5 小时，适合边走边拍",
                    "distance": 180,
                    "highlights": ["青山沟景区", "山水风景", "宽甸县城收尾"],
                    "note": "青山沟适合拉长停留时间，下午进入宽甸补给和住宿更稳。",
                },
                {
                    "day": 3,
                    "title": "宽甸 -> 绿江村 -> 丹东",
                    "ride_time": "建议骑行 5 小时，含 2 次观景停靠",
                    "distance": 240,
                    "highlights": ["绿江村江景", "边境氛围", "丹东鸭绿江收官"],
                    "note": "绿江村早晚光线更适合出片，若当天返程较远，建议提早离开。",
                },
            ],
            "pois": {
                "fuel": [
                    {"name": "本溪城区加油站", "meta": "Day 1 · 进山前补油"},
                    {"name": "桓仁县城加油点", "meta": "Day 1 · 晚间补给"},
                    {"name": "宽甸城区加油站", "meta": "Day 2 · 次日去绿江前补给"},
                ],
                "repair": [
                    {"name": "本溪机车维修点", "meta": "Day 1 · 进山前基础检查"},
                    {"name": "丹东城区维修点", "meta": "Day 3 · 收官后检查"},
                ],
                "lodging": [
                    {"name": "桓仁骑手友好酒店", "meta": "Day 1 · 停车方便"},
                    {"name": "宽甸城区民宿", "meta": "Day 2 · 次日出发绿江更顺路"},
                ],
                "viewpoint": [
                    {"name": "本桓公路观景路段", "meta": "Day 1 · 建议停留 15 分钟"},
                    {"name": "青山沟风景区", "meta": "Day 2 · 建议停留 1-2 小时"},
                    {"name": "绿江村观景点", "meta": "Day 3 · 建议日落前停留"},
                ],
                "emergency": [
                    {"name": "桓仁满族自治县中心医院", "meta": "Day 1 · 山路后段应急点"},
                    {"name": "宽甸中心医院", "meta": "Day 2 · 边境县道应急点"},
                ],
            },
            "detail_highlights": [
                "本桓公路是辽宁机车圈辨识度很高的跑山路段，适合纯骑行内容拍摄。",
                "青山沟和绿江村把山路摩旅接上了山水与边境风景，画面层次更完整。",
                "全线补给点相对清晰，适合周末 2-3 天完成，不需要一次性拉太长距离。",
            ],
            "detail_for_whom": "适合辽宁及东北周边车友做周末中短途摩旅，也适合想兼顾跑山、打卡和拍内容的骑手。",
            "detail_notes": [
                "本桓公路和宽甸山区天气变化快，建议携带雨具和保暖层。",
                "绿江村早晚温差更明显，计划拍日出或日落时要预留充足保暖装备。",
                "边境与山区路段建议白天通过，新手尽量避免夜间骑行。",
            ],
            "checkpoints": [
                {
                    "name": "本桓公路",
                    "summary": "辽宁经典跑山段，弯道连贯，林景和山体起伏都很适合骑行视频。",
                    "timing": "Day 1 · 中午前后进入最佳",
                    "image": "route-liaoning-benhuan.svg",
                },
                {
                    "name": "桓仁",
                    "summary": "更适合作为第一天补给和住宿节点，能把节奏从跑山自然过渡到休整。",
                    "timing": "Day 1 · 晚间落脚",
                    "image": "route-liaoning-huanren.svg",
                },
                {
                    "name": "青山沟",
                    "summary": "山水景区感更强，适合做人与车同框、景别切换和中途休闲拍摄。",
                    "timing": "Day 2 · 白天停留 1-2 小时",
                    "image": "route-liaoning-qingshangou.svg",
                },
                {
                    "name": "绿江村",
                    "summary": "这条线最容易出片的点位之一，江景、村落和光线氛围都很强。",
                    "timing": "Day 3 · 早晚光线最佳",
                    "image": "route-liaoning-lujiang.svg",
                },
                {
                    "name": "丹东鸭绿江",
                    "summary": "适合用城市沿江镜头给整条路线做收尾，也方便作为返程或住宿点。",
                    "timing": "Day 3 · 下午收官",
                    "image": "route-liaoning-dandong.svg",
                },
            ],
        },
        {
            "slug": "liaoning-dalian-coast-2-day",
            "title": "辽宁 2 天大连滨海轻骑线",
            "region": "north",
            "spot_slugs": [
                "dalian-binhai-road",
                "bangchuidao-roads",
                "jinshitan",
                "lvshun-coast-road",
            ],
            "days": 2,
            "difficulty": "easy",
            "scenery_type": ["coast", "scenic", "relaxed"],
            "bike_types": ["125-150cc", "150-250cc", "300-500cc", "adv-touring"],
            "experience_levels": ["beginner", "intermediate"],
            "best_season": "春季 / 夏季 / 秋季",
            "distance_km": 280,
            "budget_range": "1000-2000",
            "summary": "以大连滨海路为主轴，串联棒棰岛、金石滩和旅顺，适合周末轻松海边摩旅。",
            "days_plan": [
                {
                    "day": 1,
                    "title": "大连 -> 滨海路 -> 棒棰岛 -> 金石滩",
                    "ride_time": "建议骑行 4-5 小时，含多次拍照停靠",
                    "distance": 140,
                    "highlights": ["海边弯道", "城市海景", "轻骑节奏"],
                    "note": "建议避开热门时段，滨海路更适合上午和傍晚拍摄。",
                },
                {
                    "day": 2,
                    "title": "金石滩 -> 旅顺沿海 -> 大连",
                    "ride_time": "建议骑行 4 小时",
                    "distance": 140,
                    "highlights": ["沿海公路", "海边停靠", "返程轻松"],
                    "note": "沿海道路风力更明显，建议注意补水和防晒。",
                },
            ],
            "pois": {
                "fuel": [
                    {"name": "大连沿海城区加油站", "meta": "Day 1 · 出发前补给"},
                    {"name": "旅顺城区加油点", "meta": "Day 2 · 返程前补油"},
                ],
                "repair": [
                    {"name": "大连机车维修点", "meta": "Day 1 · 出发前基础检查"},
                ],
                "lodging": [
                    {"name": "金石滩海边酒店", "meta": "Day 1 · 停车方便"},
                ],
                "viewpoint": [
                    {"name": "滨海路观景位", "meta": "Day 1 · 建议多次停留"},
                    {"name": "旅顺海边停靠点", "meta": "Day 2 · 海边休整"},
                ],
                "emergency": [
                    {"name": "大连市中心医院", "meta": "沿线最近城市医疗支援"},
                ],
            },
        },
        {
            "slug": "liaoning-liaodong-2-day",
            "title": "辽宁 2 天辽东边境风景线",
            "region": "north",
            "spot_slugs": [
                "qingshangou",
                "kuandian-county-roads",
                "lujiang-village",
                "dandong-yalu-river",
            ],
            "days": 2,
            "difficulty": "medium",
            "scenery_type": ["mountain", "scenic", "niche"],
            "bike_types": ["150-250cc", "300-500cc", "500cc+", "adv-touring"],
            "experience_levels": ["intermediate", "advanced"],
            "best_season": "夏季 / 秋季",
            "distance_km": 430,
            "budget_range": "1000-2000",
            "summary": "更聚焦辽东边境和江景，两天内覆盖青山沟、宽甸、绿江村和丹东。",
            "days_plan": [
                {
                    "day": 1,
                    "title": "沈阳 -> 青山沟 -> 宽甸",
                    "ride_time": "建议骑行 5-6 小时，含景区停留",
                    "distance": 220,
                    "highlights": ["山水景区", "县道路段", "宽甸落脚"],
                    "note": "这条线更适合已经有短途经验的骑手。",
                },
                {
                    "day": 2,
                    "title": "宽甸 -> 绿江村 -> 丹东",
                    "ride_time": "建议骑行 5 小时",
                    "distance": 210,
                    "highlights": ["江景村落", "边境氛围", "沿江收官"],
                    "note": "如果想拍日出或日落，需要提前预留机动时间。",
                },
            ],
            "pois": {
                "fuel": [
                    {"name": "宽甸城区加油站", "meta": "Day 1 · 住宿前补给"},
                    {"name": "丹东沿线加油点", "meta": "Day 2 · 返程前补油"},
                ],
                "repair": [
                    {"name": "丹东机车维修点", "meta": "Day 2 · 收官后检查"},
                ],
                "lodging": [
                    {"name": "宽甸城区骑手友好民宿", "meta": "Day 1 · 方便停车"},
                ],
                "viewpoint": [
                    {"name": "青山沟观景点", "meta": "Day 1 · 白天停留"},
                    {"name": "绿江村观景位", "meta": "Day 2 · 适合早晚拍摄"},
                ],
                "emergency": [
                    {"name": "宽甸中心医院", "meta": "Day 1 · 山区应急支援"},
                ],
            },
        },
        {
            "slug": "liaoning-red-beach-2-day",
            "title": "辽宁 2 天红海滩海滨轻松线",
            "region": "north",
            "spot_slugs": [
                "red-beach",
                "panjin-wetland-roads",
                "huludao-xingcheng-coast",
                "juehua-island-departure",
            ],
            "days": 2,
            "difficulty": "easy",
            "scenery_type": ["coast", "scenic", "relaxed"],
            "bike_types": ["125-150cc", "150-250cc", "300-500cc", "adv-touring"],
            "experience_levels": ["beginner", "intermediate"],
            "best_season": "秋季",
            "distance_km": 360,
            "budget_range": "1000-2000",
            "summary": "适合想跑辽宁西南海边和秋季湿地景观的轻松两天线。",
            "days_plan": [
                {
                    "day": 1,
                    "title": "沈阳 -> 盘锦湿地周边 -> 红海滩",
                    "ride_time": "建议骑行 4-5 小时",
                    "distance": 180,
                    "highlights": ["湿地公路", "秋季景观", "低强度节奏"],
                    "note": "红海滩更看季节窗口，秋季出发体验最好。",
                },
                {
                    "day": 2,
                    "title": "盘锦 -> 兴城 -> 葫芦岛海滨",
                    "ride_time": "建议骑行 4-5 小时",
                    "distance": 180,
                    "highlights": ["海边巡航", "城市轻骑", "返程友好"],
                    "note": "整条线适合新手做海边和城市轻摩旅。",
                },
            ],
            "pois": {
                "fuel": [
                    {"name": "盘锦沿线加油站", "meta": "Day 1 · 湿地段补给"},
                    {"name": "兴城区加油点", "meta": "Day 2 · 海边返程前补油"},
                ],
                "repair": [
                    {"name": "葫芦岛城区维修点", "meta": "Day 2 · 收官检查"},
                ],
                "lodging": [
                    {"name": "盘锦城区酒店", "meta": "Day 1 · 次日转海边更顺路"},
                ],
                "viewpoint": [
                    {"name": "红海滩景观区", "meta": "Day 1 · 秋季重点打卡"},
                    {"name": "兴城海滨沿线", "meta": "Day 2 · 海边轻骑停靠"},
                ],
                "emergency": [
                    {"name": "盘锦中心医院", "meta": "Day 1 · 城区医疗支援"},
                ],
            },
        },
    ]


def get_route_by_slug(slug: str) -> dict[str, Any] | None:
    return next((route for route in get_route_templates() if route["slug"] == slug), None)


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
    return {
        "page": {
            "title": "热门摩旅路线库",
            "description": "按地区、天数和难度，找到更适合你的路线模板。",
        },
        "filters": {
            "action": "/moto/routes",
            "fields": [
                {
                    "name": "days",
                    "label": "天数",
                    "type": "select",
                    "value": str(filters.get("days") or ""),
                    "options": [
                        {"label": "全部天数", "value": ""},
                        {"label": "2 天", "value": "2"},
                        {"label": "3 天", "value": "3"},
                        {"label": "5 天", "value": "5"},
                    ],
                }
            ],
        },
        "routes": [
            {
                "slug": route["slug"],
                "title": route["title"],
                "summary": route["summary"],
                "tags": [f"{route['days']} 天", route["best_season"], route["difficulty"]],
                "best_season": route["best_season"],
                "href": f"/moto/routes/{route['slug']}",
                "replan_href": f"/moto/planner?route={route['slug']}",
            }
            for route in route_templates
        ],
        "empty_state": {
            "title": "暂时没有匹配路线",
            "description": "可以先试试路线规划工具，生成一份适合你的基础方案。",
            "action": {"label": "开始规划", "href": "/moto/planner"},
        },
    }


def build_route_detail_context(route: dict[str, Any]) -> dict[str, Any]:
    return {
        "route": {
            "title": route["title"],
            "summary": route["summary"],
            "tags": [f"{route['days']} 天", route["difficulty"], route["best_season"]],
            "best_season": route["best_season"],
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
            {
                "title": candidate["title"],
                "href": f"/moto/routes/{candidate['slug']}",
            }
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