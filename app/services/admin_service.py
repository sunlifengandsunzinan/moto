from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
import json
from typing import Any, Mapping

from .liaoning_spots import (
    get_approved_moto_spot_by_slug,
    get_approved_moto_spots,
    get_empty_moto_spot_record,
    save_approved_moto_spot,
    delete_approved_moto_spot,
)
from .route_templates_config import (
    get_route_template_by_slug,
    load_route_templates,
    save_route_templates,
    save_route_template,
    delete_route_template,
)
from .planner_service import get_liaoning_route_templates


ROUTE_FORM_GROUPS = [
    {
        "title": "基础信息",
        "description": "这些字段会直接影响路线列表和详情页的核心展示。",
        "fields": [
            ("slug", "唯一标识", "text", "例如 liaoning-dalian-coast-2-day"),
            ("title", "路线标题", "text", "前台页面展示标题"),
            ("region", "区域", "text", "例如 liaoning / east"),
            ("days", "骑行天数", "number", "数字"),
            ("distance_km", "总里程 km", "number", "数字"),
            ("difficulty", "难度", "text", "easy / medium / hard"),
            ("best_season", "最佳季节", "text", "例如 春秋"),
            ("budget_range", "预算范围", "text", "例如 1000-2000"),
            ("summary", "摘要", "textarea", "路线列表与详情摘要"),
            ("is_visible", "是否在路线页显示", "text", "true / false，默认 true"),
            ("detail_for_whom", "适合谁", "textarea", "详情页说明，可为空"),
        ],
    },
    {
        "title": "标签与关联",
        "description": "这些字段决定路线筛选、推荐以及和点位库的关联。",
        "fields": [
            ("scenery_type", "景观类型", "textarea", "每行或逗号一个值"),
            ("bike_types", "适合车型", "textarea", "每行或逗号一个值"),
            ("experience_levels", "适合经验等级", "textarea", "每行或逗号一个值"),
            ("spot_slugs", "关联点位 slug", "textarea", "每行或逗号一个值"),
            ("detail_highlights", "详情亮点", "textarea", "每行一个亮点"),
            ("detail_notes", "详情备注", "textarea", "每行一条备注"),
        ],
    },
    {
        "title": "路线结构",
        "description": "高德导航、路线地图和详情日程都依赖这里的数据。",
        "fields": [
            ("navigation_waypoints", "导航途径点 JSON", "textarea", "必须至少 2 个点，包含 name 和经纬度"),
            ("days_plan", "每日行程 JSON", "textarea", "详情页日程"),
            ("pois", "POI 分类 JSON", "textarea", "fuel / repair / lodging / viewpoint / emergency"),
            ("checkpoints", "打卡点时间线 JSON", "textarea", "可为空"),
        ],
    },
]


SPOT_FORM_GROUPS = [
    {
        "title": "基础信息",
        "description": "这些字段会直接影响点位列表和详情页标题区。",
        "fields": [
            ("slug", "唯一标识", "text", "例如 dalian-binhai-road"),
            ("name", "点位名称", "text", "详情页标题"),
            ("spot_type", "点位类型", "text", "例如 scenic-spot"),
            ("spot_markers", "固定标记", "textarea", "每行或逗号一个值"),
            ("city", "城市", "text", "例如 大连"),
            ("region", "区域", "text", "例如 辽南"),
            ("route_type", "路线类型", "text", "例如 coast"),
            ("summary", "摘要", "textarea", "列表与详情摘要"),
        ],
    },
    {
        "title": "坐标与图片",
        "description": "这些字段决定地图关联、图卡和详情页图片区。",
        "fields": [
            ("coordinates_lat", "纬度", "number", "例如 38.914"),
            ("coordinates_lng", "经度", "number", "例如 121.614"),
            ("image_urls", "图片地址", "textarea", "每行一张图，前 3 张优先用于封面/路线/拍摄"),
            ("image_key", "图片资源键", "text", "用于 SVG 占位图"),
            ("video_url", "视频地址", "text", "详情页视频来源"),
            ("keyframe_paths", "关键帧路径", "textarea", "每行一个 keyframe 路径"),
        ],
    },
    {
        "title": "骑行展示字段",
        "description": "这些字段会直接出现在详情页的标签、建议和说明中。",
        "fields": [
            ("best_seasons", "最佳季节", "textarea", "每行或逗号一个值"),
            ("best_time_of_day", "最佳时段", "textarea", "每行或逗号一个值"),
            ("ride_level", "骑行等级", "text", "例如 beginner"),
            ("recommended_stay", "建议停留", "text", "例如 2-3 小时"),
            ("road_features", "道路特征", "textarea", "每行一条"),
            ("risk_notes", "风险提示", "textarea", "每行一条"),
            ("photo_focus", "拍摄重点", "textarea", "每行一条"),
            ("route_tags", "路线标签", "textarea", "每行或逗号一个值"),
            ("nearby_spot_slugs", "附近点位 slug", "textarea", "每行或逗号一个值"),
        ],
    },
    {
        "title": "补给与质量",
        "description": "这些字段会影响筛选、推荐与来源说明。",
        "fields": [
            ("access_level", "可达性", "text", "例如 easy / unknown"),
            ("parking_friendly", "停车友好", "text", "true / false / blank"),
            ("fuel_support", "加油支持", "text", "例如 nearby"),
            ("repair_support", "维修支持", "text", "例如 limited"),
            ("lodging_support", "住宿支持", "text", "例如 available"),
            ("food_support", "餐饮支持", "text", "例如 available"),
            ("support_role", "简化支持标签", "textarea", "每行或逗号一个值"),
            ("moto_station_features", "驿站特征", "textarea", "每行或逗号一个值"),
            ("confidence_score", "可信度", "text", "例如 A / B / C"),
            ("last_verified_at", "最后核验时间", "text", "例如 2026-08-02"),
            ("sources", "来源 JSON", "textarea", "列表 JSON，每项包含 type/name/url/author/verified/note"),
            ("video_analysis", "视频分析 JSON", "textarea", "详情页视频诊断区域使用"),
        ],
    },
]


def get_admin_dashboard_context(feedback: Mapping[str, str] | None = None) -> dict[str, Any]:
    routes = load_route_templates()
    visible_frontend_routes = get_liaoning_route_templates()
    spots = get_approved_moto_spots()
    route_regions = sorted({str(route.get("region") or "") for route in routes if str(route.get("region") or "").strip()})
    spot_regions = sorted({str(spot.get("region") or "") for spot in spots if str(spot.get("region") or "").strip()})

    return {
        "page": {
            "title": "路线与点位后台管理",
            "description": "直接维护当前前台页面所使用的路线模板、打卡点、图片、坐标和结构化说明。",
        },
        "feedback": {
            "message": str((feedback or {}).get("message") or "").strip(),
            "kind": str((feedback or {}).get("kind") or "info").strip() or "info",
        },
        "stats": [
            {"label": "路线总库", "value": len(routes)},
            {"label": "前台显示路线", "value": len(visible_frontend_routes)},
            {"label": "点位总数", "value": len(spots)},
            {"label": "路线区域", "value": len(route_regions)},
            {"label": "点位区域", "value": len(spot_regions)},
        ],
        "route_section": {
            "title": "路线模板",
            "description": "编辑路线列表、详情页、高德地图、日程和 POI 数据。",
            "create_href": "/moto/admin/routes/new",
            "items": [
                {
                    "title": route.get("title") or str(route.get("slug") or "未命名路线"),
                    "slug": str(route.get("slug") or ""),
                    "summary": str(route.get("summary") or ""),
                    "meta": [
                        f"{int(route.get('days') or 0)} 天",
                        f"{route.get('distance_km') or 0} km",
                        str(route.get("region") or "未分类"),
                    ],
                    "is_visible": _parse_route_visibility(route.get("is_visible")),
                    "preview_href": f"/moto/routes/{route.get('slug')}",
                    "edit_href": f"/moto/admin/routes/{route.get('slug')}/edit",
                    "delete_href": f"/moto/admin/routes/{route.get('slug')}/delete",
                }
                for route in routes
            ],
        },
        "spot_section": {
            "title": "辽宁打卡点",
            "description": "编辑点位标题、摘要、图片、坐标、支撑标签与来源说明。",
            "create_href": "/moto/admin/spots/new",
            "items": [
                {
                    "title": spot.get("name") or str(spot.get("slug") or "未命名点位"),
                    "slug": str(spot.get("slug") or ""),
                    "summary": str(spot.get("summary") or ""),
                    "meta": [
                        str(spot.get("city") or "未设城市"),
                        str(spot.get("region") or "未设区域"),
                        str(spot.get("route_type_label") or spot.get("route_type") or "未分类"),
                    ],
                    "preview_href": f"/moto/spots/liaoning/{spot.get('slug')}",
                    "edit_href": f"/moto/admin/spots/{spot.get('slug')}/edit",
                    "image_url": ((spot.get("image_gallery") or [{}])[0]).get("image_url", ""),
                }
                for spot in spots
            ],
        },
    }


def get_admin_route_form_context(
    slug: str | None = None,
    *,
    form_data: Mapping[str, Any] | None = None,
    errors: list[str] | None = None,
    feedback: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    route = get_route_template_by_slug(slug) if slug else None
    values = _route_form_values(route, form_data)
    current_slug = values["slug"]
    is_edit = route is not None
    return {
        "page": {
            "eyebrow": "后台管理 / 路线",
            "title": "编辑路线" if is_edit else "新增路线",
            "description": "维护路线列表、路线详情和地图使用的数据。",
        },
        "form": {
            "action": "/moto/admin/routes/save",
            "method": "post",
            "enctype": "",
            "submit_label": "保存路线",
            "hidden_fields": [{"name": "original_slug", "value": slug or ""}],
            "groups": _build_form_groups(ROUTE_FORM_GROUPS, values),
        },
        "errors": errors or [],
        "feedback": {
            "message": str((feedback or {}).get("message") or "").strip(),
            "kind": str((feedback or {}).get("kind") or "info").strip() or "info",
        },
        "preview_href": f"/moto/routes/{current_slug}" if current_slug else "",
        "delete_action": f"/moto/admin/routes/{current_slug}/delete" if is_edit and current_slug else "",
        "back_href": "/moto/admin",
        "tips": [
            "导航途径点 JSON 需要至少 2 个带 name 的节点，支持 lat/lng 或 coordinates.lat/lng。",
            "每日行程 JSON 会直接进入路线详情页的“示例日程”区。",
            "POI JSON 会进入路线详情和路线列表的补给信息。",
        ],
    }


def get_admin_spot_form_context(
    slug: str | None = None,
    *,
    form_data: Mapping[str, Any] | None = None,
    errors: list[str] | None = None,
    feedback: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    spot = get_approved_moto_spot_by_slug(slug) if slug else None
    values = _spot_form_values(spot, form_data)
    current_slug = values["slug"]
    is_edit = spot is not None
    preview_urls = _split_multiline_value(values.get("image_urls", ""))
    return {
        "page": {
            "eyebrow": "后台管理 / 打卡点",
            "title": "编辑打卡点" if is_edit else "新增打卡点",
            "description": "维护点位列表、详情页、图片、坐标和视频诊断字段。",
        },
        "form": {
            "action": "/moto/admin/spots/save",
            "method": "post",
            "enctype": "multipart/form-data",
            "submit_label": "保存点位",
            "hidden_fields": [{"name": "original_slug", "value": slug or ""}],
            "groups": _build_form_groups(SPOT_FORM_GROUPS, values),
            "image_uploads": [
                {
                    "name": "image_upload_cover",
                    "label": "上传封面图",
                    "help": "保存后会覆盖第 1 张图片，用于列表封面。",
                    "current_url": preview_urls[0] if len(preview_urls) > 0 else "",
                },
                {
                    "name": "image_upload_route",
                    "label": "上传路线图",
                    "help": "保存后会覆盖第 2 张图片，用于道路视角。",
                    "current_url": preview_urls[1] if len(preview_urls) > 1 else "",
                },
                {
                    "name": "image_upload_photo",
                    "label": "上传拍摄图",
                    "help": "保存后会覆盖第 3 张图片，用于拍摄视角。",
                    "current_url": preview_urls[2] if len(preview_urls) > 2 else "",
                },
            ],
        },
        "errors": errors or [],
        "feedback": {
            "message": str((feedback or {}).get("message") or "").strip(),
            "kind": str((feedback or {}).get("kind") or "info").strip() or "info",
        },
        "preview_href": f"/moto/spots/liaoning/{current_slug}" if current_slug else "",
        "delete_action": f"/moto/admin/spots/{current_slug}/delete" if is_edit and current_slug else "",
        "back_href": "/moto/admin",
        "tips": [
            "图片地址前 3 张会优先用于封面图、道路视角和拍摄视角。",
            "来源 JSON 支持 verified 布尔值，详情页会显示“已核验/待核验”。",
            "视频分析 JSON 会直接影响详情页“视频采集诊断”区域的展示。",
        ],
    }


def save_route_from_form(form_data: Mapping[str, Any]) -> dict[str, Any]:
    original_slug = str(form_data.get("original_slug") or "").strip() or None
    base_route = get_route_template_by_slug(original_slug) if original_slug else None
    route = deepcopy(base_route) if base_route else {
        "slug": "",
        "title": "",
        "region": "liaoning",
        "spot_slugs": [],
        "days": 2,
        "difficulty": "easy",
        "scenery_type": [],
        "bike_types": [],
        "experience_levels": [],
        "best_season": "",
        "distance_km": 0,
        "budget_range": "",
        "summary": "",
        "navigation": {"provider": "amap", "waypoints": []},
        "days_plan": [],
        "pois": {"fuel": [], "repair": [], "lodging": [], "viewpoint": [], "emergency": []},
    }

    route.update({
        "slug": _required_text(form_data, "slug", "路线 slug"),
        "title": _required_text(form_data, "title", "路线标题"),
        "region": _required_text(form_data, "region", "路线区域"),
        "days": _required_int(form_data, "days", "骑行天数"),
        "distance_km": _required_number(form_data, "distance_km", "总里程"),
        "difficulty": _required_text(form_data, "difficulty", "路线难度"),
        "best_season": _required_text(form_data, "best_season", "最佳季节"),
        "budget_range": _required_text(form_data, "budget_range", "预算范围"),
        "summary": _required_text(form_data, "summary", "路线摘要"),
        "is_visible": _parse_bool_value(form_data.get("is_visible"), "是否在路线页显示", default=True),
        "scenery_type": _split_multiline_value(form_data.get("scenery_type")),
        "bike_types": _split_multiline_value(form_data.get("bike_types")),
        "experience_levels": _split_multiline_value(form_data.get("experience_levels")),
        "spot_slugs": _split_multiline_value(form_data.get("spot_slugs")),
        "days_plan": _parse_json_text(form_data.get("days_plan"), "每日行程 JSON", default=[]),
        "navigation": {
            "provider": "amap",
            "waypoints": _parse_json_text(form_data.get("navigation_waypoints"), "导航途径点 JSON", default=[]),
        },
        "pois": _parse_json_text(form_data.get("pois"), "POI JSON", default={}),
        "detail_highlights": _split_multiline_value(form_data.get("detail_highlights")),
        "detail_notes": _split_multiline_value(form_data.get("detail_notes")),
        "checkpoints": _parse_json_text(form_data.get("checkpoints"), "打卡点时间线 JSON", default=[]),
    })

    detail_for_whom = str(form_data.get("detail_for_whom") or "").strip()
    if detail_for_whom:
        route["detail_for_whom"] = detail_for_whom
    else:
        route.pop("detail_for_whom", None)

    return save_route_template(route, original_slug=original_slug)


def save_spot_from_form(form_data: Mapping[str, Any], uploaded_image_urls: Mapping[int, str] | None = None) -> dict[str, Any]:
    original_slug = str(form_data.get("original_slug") or "").strip() or None
    base_spot = get_approved_moto_spot_by_slug(original_slug) if original_slug else None
    spot = deepcopy(base_spot) if base_spot else get_empty_moto_spot_record()

    image_urls = _split_multiline_value(form_data.get("image_urls"))
    image_urls = _merge_uploaded_image_urls(image_urls, uploaded_image_urls or {})

    spot.update({
        "slug": _required_text(form_data, "slug", "点位 slug"),
        "name": _required_text(form_data, "name", "点位名称"),
        "spot_type": _required_text(form_data, "spot_type", "点位类型"),
        "spot_markers": _split_multiline_value(form_data.get("spot_markers")),
        "city": _required_text(form_data, "city", "城市"),
        "region": _required_text(form_data, "region", "区域"),
        "route_type": _required_text(form_data, "route_type", "路线类型"),
        "summary": _required_text(form_data, "summary", "点位摘要"),
        "best_seasons": _split_multiline_value(form_data.get("best_seasons")),
        "best_time_of_day": _split_multiline_value(form_data.get("best_time_of_day")),
        "ride_level": _required_text(form_data, "ride_level", "骑行等级"),
        "recommended_stay": _required_text(form_data, "recommended_stay", "建议停留"),
        "road_features": _split_multiline_value(form_data.get("road_features")),
        "risk_notes": _split_multiline_value(form_data.get("risk_notes")),
        "photo_focus": _split_multiline_value(form_data.get("photo_focus")),
        "image_urls": image_urls,
        "image_key": str(form_data.get("image_key") or "").strip(),
        "route_tags": _split_multiline_value(form_data.get("route_tags")),
        "nearby_spot_slugs": _split_multiline_value(form_data.get("nearby_spot_slugs")),
        "access_level": str(form_data.get("access_level") or "").strip() or "unknown",
        "fuel_support": str(form_data.get("fuel_support") or "").strip() or "unknown",
        "repair_support": str(form_data.get("repair_support") or "").strip() or "unknown",
        "lodging_support": str(form_data.get("lodging_support") or "").strip() or "unknown",
        "food_support": str(form_data.get("food_support") or "").strip() or "unknown",
        "support_role": _split_multiline_value(form_data.get("support_role")),
        "moto_station_features": _split_multiline_value(form_data.get("moto_station_features")),
        "confidence_score": str(form_data.get("confidence_score") or "").strip() or "C",
        "last_verified_at": str(form_data.get("last_verified_at") or "").strip(),
        "sources": _parse_json_text(form_data.get("sources"), "来源 JSON", default=[]),
        "video_analysis": _parse_json_text(form_data.get("video_analysis"), "视频分析 JSON", default={}),
    })

    spot["parking_friendly"] = _parse_nullable_bool(form_data.get("parking_friendly"))
    spot["coordinates"] = {
        "lat": _parse_optional_number(form_data.get("coordinates_lat")),
        "lng": _parse_optional_number(form_data.get("coordinates_lng")),
    }

    video_url = str(form_data.get("video_url") or "").strip()
    if video_url:
        spot["video_url"] = video_url
    else:
        spot.pop("video_url", None)

    keyframe_paths = _split_multiline_value(form_data.get("keyframe_paths"))
    if keyframe_paths:
        spot["keyframe_paths"] = keyframe_paths
    else:
        spot.pop("keyframe_paths", None)

    return save_approved_moto_spot(spot, original_slug=original_slug)


def delete_route_admin_record(slug: str) -> bool:
    return delete_route_template(slug)


def update_route_visibility(visible_route_slugs: list[str]) -> dict[str, int]:
    visible_set = {str(slug or "").strip() for slug in visible_route_slugs if str(slug or "").strip()}
    routes = [deepcopy(route) for route in load_route_templates()]

    updated_count = 0
    for route in routes:
        slug = str(route.get("slug") or "").strip()
        should_be_visible = slug in visible_set
        previous_value = _parse_route_visibility(route.get("is_visible"))
        route["is_visible"] = should_be_visible
        if previous_value != should_be_visible:
            updated_count += 1

    save_route_templates(routes)
    return {"updated": updated_count, "total": len(routes), "visible": len(visible_set)}


def delete_spot_admin_record(slug: str) -> bool:
    return delete_approved_moto_spot(slug)


def _route_form_values(route: Mapping[str, Any] | None, form_data: Mapping[str, Any] | None) -> dict[str, Any]:
    source = deepcopy(dict(route)) if route else {}
    values = {
        "slug": _field_value(form_data, "slug", source.get("slug", "")),
        "title": _field_value(form_data, "title", source.get("title", "")),
        "region": _field_value(form_data, "region", source.get("region", "liaoning")),
        "days": _field_value(form_data, "days", source.get("days", 2)),
        "distance_km": _field_value(form_data, "distance_km", source.get("distance_km", 0)),
        "difficulty": _field_value(form_data, "difficulty", source.get("difficulty", "easy")),
        "best_season": _field_value(form_data, "best_season", source.get("best_season", "")),
        "budget_range": _field_value(form_data, "budget_range", source.get("budget_range", "")),
        "summary": _field_value(form_data, "summary", source.get("summary", "")),
        "is_visible": _field_value(form_data, "is_visible", str(_parse_route_visibility(source.get("is_visible"))).lower()),
        "detail_for_whom": _field_value(form_data, "detail_for_whom", source.get("detail_for_whom", "")),
        "scenery_type": _field_value(form_data, "scenery_type", _stringify_list(source.get("scenery_type", []))),
        "bike_types": _field_value(form_data, "bike_types", _stringify_list(source.get("bike_types", []))),
        "experience_levels": _field_value(form_data, "experience_levels", _stringify_list(source.get("experience_levels", []))),
        "spot_slugs": _field_value(form_data, "spot_slugs", _stringify_list(source.get("spot_slugs", []))),
        "detail_highlights": _field_value(form_data, "detail_highlights", _stringify_list(source.get("detail_highlights", []))),
        "detail_notes": _field_value(form_data, "detail_notes", _stringify_list(source.get("detail_notes", []))),
        "navigation_waypoints": _field_value(form_data, "navigation_waypoints", _json_text((source.get("navigation") or {}).get("waypoints", []))),
        "days_plan": _field_value(form_data, "days_plan", _json_text(source.get("days_plan", []))),
        "pois": _field_value(form_data, "pois", _json_text(source.get("pois", {}))),
        "checkpoints": _field_value(form_data, "checkpoints", _json_text(source.get("checkpoints", []))),
    }
    return values


def _spot_form_values(spot: Mapping[str, Any] | None, form_data: Mapping[str, Any] | None) -> dict[str, Any]:
    source = deepcopy(dict(spot)) if spot else get_empty_moto_spot_record()
    coordinates = source.get("coordinates") if isinstance(source.get("coordinates"), dict) else {}
    values = {
        "slug": _field_value(form_data, "slug", source.get("slug", "")),
        "name": _field_value(form_data, "name", source.get("name", "")),
        "spot_type": _field_value(form_data, "spot_type", source.get("spot_type", "scenic-spot")),
        "spot_markers": _field_value(form_data, "spot_markers", _stringify_list(source.get("spot_markers", []))),
        "city": _field_value(form_data, "city", source.get("city", "")),
        "region": _field_value(form_data, "region", source.get("region", "")),
        "route_type": _field_value(form_data, "route_type", source.get("route_type", "")),
        "summary": _field_value(form_data, "summary", source.get("summary", "")),
        "coordinates_lat": _field_value(form_data, "coordinates_lat", coordinates.get("lat", "")),
        "coordinates_lng": _field_value(form_data, "coordinates_lng", coordinates.get("lng", "")),
        "image_urls": _field_value(form_data, "image_urls", _stringify_list(source.get("image_urls", []))),
        "image_key": _field_value(form_data, "image_key", source.get("image_key", "")),
        "video_url": _field_value(form_data, "video_url", source.get("video_url", source.get("videoUrl", ""))),
        "keyframe_paths": _field_value(form_data, "keyframe_paths", _stringify_list(source.get("keyframe_paths", source.get("keyframePaths", [])))),
        "best_seasons": _field_value(form_data, "best_seasons", _stringify_list(source.get("best_seasons", []))),
        "best_time_of_day": _field_value(form_data, "best_time_of_day", _stringify_list(source.get("best_time_of_day", []))),
        "ride_level": _field_value(form_data, "ride_level", source.get("ride_level", "beginner")),
        "recommended_stay": _field_value(form_data, "recommended_stay", source.get("recommended_stay", "")),
        "road_features": _field_value(form_data, "road_features", _stringify_list(source.get("road_features", []))),
        "risk_notes": _field_value(form_data, "risk_notes", _stringify_list(source.get("risk_notes", []))),
        "photo_focus": _field_value(form_data, "photo_focus", _stringify_list(source.get("photo_focus", []))),
        "route_tags": _field_value(form_data, "route_tags", _stringify_list(source.get("route_tags", []))),
        "nearby_spot_slugs": _field_value(form_data, "nearby_spot_slugs", _stringify_list(source.get("nearby_spot_slugs", []))),
        "access_level": _field_value(form_data, "access_level", source.get("access_level", "unknown")),
        "parking_friendly": _field_value(form_data, "parking_friendly", "" if source.get("parking_friendly") is None else str(source.get("parking_friendly")).lower()),
        "fuel_support": _field_value(form_data, "fuel_support", source.get("fuel_support", "unknown")),
        "repair_support": _field_value(form_data, "repair_support", source.get("repair_support", "unknown")),
        "lodging_support": _field_value(form_data, "lodging_support", source.get("lodging_support", "unknown")),
        "food_support": _field_value(form_data, "food_support", source.get("food_support", "unknown")),
        "support_role": _field_value(form_data, "support_role", _stringify_list(source.get("support_role", []))),
        "moto_station_features": _field_value(form_data, "moto_station_features", _stringify_list(source.get("moto_station_features", []))),
        "confidence_score": _field_value(form_data, "confidence_score", source.get("confidence_score", "C")),
        "last_verified_at": _field_value(form_data, "last_verified_at", source.get("last_verified_at", "")),
        "sources": _field_value(form_data, "sources", _json_text(source.get("sources", []))),
        "video_analysis": _field_value(form_data, "video_analysis", _json_text(source.get("video_analysis", source.get("videoAnalysis", {})))),
    }
    return values


def _build_form_groups(group_specs: list[dict[str, Any]], values: Mapping[str, Any]) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    for group in group_specs:
        groups.append(
            {
                "title": group["title"],
                "description": group["description"],
                "fields": [
                    {
                        "name": name,
                        "label": label,
                        "component": component,
                        "help": help_text,
                        "value": values.get(name, ""),
                    }
                    for name, label, component, help_text in group["fields"]
                ],
            }
        )
    return groups


def _field_value(form_data: Mapping[str, Any] | None, name: str, fallback: Any) -> Any:
    if form_data is not None and name in form_data:
        return form_data.get(name, "")
    return fallback


def _required_text(form_data: Mapping[str, Any], name: str, label: str) -> str:
    value = str(form_data.get(name) or "").strip()
    if not value:
        raise ValueError(f"{label}不能为空")
    return value


def _required_int(form_data: Mapping[str, Any], name: str, label: str) -> int:
    value = str(form_data.get(name) or "").strip()
    if not value:
        raise ValueError(f"{label}不能为空")
    try:
        return int(value)
    except ValueError as error:
        raise ValueError(f"{label}必须是整数") from error


def _required_number(form_data: Mapping[str, Any], name: str, label: str) -> int | float:
    value = str(form_data.get(name) or "").strip()
    if not value:
        raise ValueError(f"{label}不能为空")
    try:
        parsed = float(value)
    except ValueError as error:
        raise ValueError(f"{label}必须是数字") from error
    return int(parsed) if parsed.is_integer() else parsed


def _parse_optional_number(value: Any) -> int | float | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    parsed = float(raw)
    return int(parsed) if parsed.is_integer() else parsed


def _parse_nullable_bool(value: Any) -> bool | None:
    raw = str(value or "").strip().lower()
    if not raw:
        return None
    if raw in {"1", "true", "yes", "y"}:
        return True
    if raw in {"0", "false", "no", "n"}:
        return False
    raise ValueError("停车友好必须是 true / false / 空")


def _parse_bool_value(value: Any, label: str, *, default: bool) -> bool:
    raw = str(value or "").strip().lower()
    if not raw:
        return default
    if raw in {"1", "true", "yes", "y"}:
        return True
    if raw in {"0", "false", "no", "n"}:
        return False
    raise ValueError(f"{label}必须是 true / false")


def _parse_route_visibility(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return True
    if isinstance(value, (int, float)):
        return bool(value)
    raw = str(value).strip().lower()
    if raw in {"", "1", "true", "yes", "y"}:
        return True
    if raw in {"0", "false", "no", "n"}:
        return False
    return True


def _split_multiline_value(value: Any) -> list[str]:
    text = str(value or "").replace("\r", "\n")
    parts: list[str] = []
    for line in text.split("\n"):
        segments = [segment.strip() for segment in line.split(",")]
        parts.extend(segment for segment in segments if segment)
    return parts


def _stringify_list(items: Any) -> str:
    if not isinstance(items, list):
        return ""
    return "\n".join(str(item).strip() for item in items if str(item).strip())


def _parse_json_text(value: Any, label: str, *, default: Any) -> Any:
    text = str(value or "").strip()
    if not text:
        return deepcopy(default)
    try:
        return json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError(f"{label} 不是有效 JSON") from error


def _json_text(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, indent=2)


def _merge_uploaded_image_urls(current_urls: list[str], uploaded_image_urls: Mapping[int, str]) -> list[str]:
    merged = list(current_urls)
    for index, url in sorted(uploaded_image_urls.items()):
        if not url:
            continue
        while len(merged) <= index:
            merged.append("")
        merged[index] = url
    return [item for item in merged if str(item).strip()]