from __future__ import annotations

import json
from html import escape
from pathlib import Path
from urllib.parse import quote
from typing import Any


SpotDict = dict[str, Any]
PROJECT_ROOT = Path(__file__).resolve().parents[2]
APPROVED_SPOTS_PATH = PROJECT_ROOT / "data" / "reviewed" / "approved_spots.json"


MOTO_SPOT_COLLECTION_SCHEMA: list[dict[str, Any]] = [
    {"name": "slug", "label": "唯一标识", "type": "string", "required": True, "group": "identity", "example": "dalian-binhai-road"},
    {"name": "name", "label": "点位名称", "type": "string", "required": True, "group": "identity", "example": "大连滨海路"},
    {"name": "spot_type", "label": "点位类型", "type": "string", "required": True, "group": "identity", "example": "scenic-spot"},
    {"name": "spot_markers", "label": "固定类型标记", "type": "list[string]", "required": False, "group": "identity", "example": ["checkin-point", "fuel-station", "moto-station", "coffee-stop"]},
    {"name": "city", "label": "城市", "type": "string", "required": True, "group": "identity", "example": "大连"},
    {"name": "region", "label": "区域", "type": "string", "required": True, "group": "identity", "example": "辽南"},
    {"name": "route_type", "label": "路线类型", "type": "string", "required": True, "group": "identity", "example": "coast"},
    {"name": "coordinates", "label": "坐标", "type": "object", "required": False, "group": "location", "example": {"lat": 38.914, "lng": 121.614}},
    {"name": "access_level", "label": "可达性", "type": "string", "required": False, "group": "location", "example": "easy"},
    {"name": "parking_friendly", "label": "停车是否友好", "type": "boolean", "required": False, "group": "location", "example": True},
    {"name": "best_seasons", "label": "最佳季节", "type": "list[string]", "required": True, "group": "travel", "example": ["spring", "summer", "autumn"]},
    {"name": "best_time_of_day", "label": "最佳时段", "type": "list[string]", "required": False, "group": "travel", "example": ["白天", "傍晚"]},
    {"name": "ride_level", "label": "适合骑行等级", "type": "string", "required": True, "group": "travel", "example": "beginner"},
    {"name": "recommended_stay", "label": "建议停留时长", "type": "string", "required": True, "group": "travel", "example": "2-3 小时"},
    {"name": "road_features", "label": "道路特征", "type": "list[string]", "required": False, "group": "travel", "example": ["临海道路", "停车拍照方便"]},
    {"name": "risk_notes", "label": "风险提示", "type": "list[string]", "required": False, "group": "travel", "example": ["注意横风", "避免夜间压弯"]},
    {"name": "summary", "label": "摘要", "type": "string", "required": True, "group": "content", "example": "适合城市轻骑和海边路线内容。"},
    {"name": "photo_focus", "label": "拍摄重点", "type": "list[string]", "required": True, "group": "content", "example": ["海边弯道", "临海骑行"]},
    {"name": "image_urls", "label": "采集图片地址", "type": "list[string]", "required": False, "group": "content", "example": ["https://example.com/spot-cover.jpg", "https://example.com/spot-detail.jpg"]},
    {"name": "image_key", "label": "图片资源键", "type": "string", "required": False, "group": "content", "example": "liaoning-binhai-cover"},
    {"name": "route_tags", "label": "路线标签", "type": "list[string]", "required": False, "group": "planning", "example": ["辽南", "coast", "photo-friendly"]},
    {"name": "nearby_spot_slugs", "label": "附近点位", "type": "list[string]", "required": False, "group": "planning", "example": ["bangchuidao-roads", "jinshitan"]},
    {"name": "fuel_support", "label": "加油支持", "type": "string", "required": False, "group": "support", "example": "nearby"},
    {"name": "repair_support", "label": "维修支持", "type": "string", "required": False, "group": "support", "example": "limited"},
    {"name": "lodging_support", "label": "住宿支持", "type": "string", "required": False, "group": "support", "example": "available"},
    {"name": "food_support", "label": "餐饮支持", "type": "string", "required": False, "group": "support", "example": "available"},
    {"name": "support_role", "label": "简化支持标签", "type": "list[string]", "required": True, "group": "support", "example": ["viewpoint", "fuel"]},
    {"name": "moto_station_features", "label": "摩托驿站特征", "type": "list[string]", "required": False, "group": "support", "example": ["可停车", "骑友集合", "可洗车"]},
    {"name": "confidence_score", "label": "可信度", "type": "string", "required": False, "group": "quality", "example": "A"},
    {"name": "sources", "label": "信息来源", "type": "list[object]", "required": False, "group": "quality", "example": [{"type": "manual", "name": "骑友口述", "url": "https://example.com/source", "author": "辽东骑士老张", "verified": True}]},
    {"name": "last_verified_at", "label": "最后核验时间", "type": "string", "required": False, "group": "quality", "example": "2026-05-27"},
]


MOTO_SPOT_COLLECTION_TEMPLATE: SpotDict = {
    "slug": "",
    "name": "",
    "spot_type": "scenic-spot",
    "spot_markers": [],
    "city": "",
    "region": "",
    "route_type": "",
    "coordinates": {"lat": None, "lng": None},
    "access_level": "unknown",
    "parking_friendly": None,
    "best_seasons": [],
    "best_time_of_day": [],
    "ride_level": "beginner",
    "recommended_stay": "",
    "road_features": [],
    "risk_notes": [],
    "summary": "",
    "photo_focus": [],
    "image_urls": [],
    "image_key": "",
    "route_tags": [],
    "nearby_spot_slugs": [],
    "fuel_support": "unknown",
    "repair_support": "unknown",
    "lodging_support": "unknown",
    "food_support": "unknown",
    "support_role": [],
    "moto_station_features": [],
    "confidence_score": "C",
    "sources": [],
    "last_verified_at": "",
}


ROUTE_TYPE_LABELS = {
    "mountain": "山路",
    "supply-stop": "补给中转",
    "mountain-view": "山景地标",
    "scenic-water": "山水景区",
    "county-road": "县道探索",
    "riverside-village": "江景村落",
    "city-riverside": "沿江城市",
    "border-landmark": "边境地标",
    "coast": "海岸公路",
    "coast-city": "城市海边",
    "coast-scenic": "海边风景",
    "coast-history": "沿海历史线",
    "seasonal-landscape": "季节性景观",
    "plain-road": "平原公路",
    "mountain-near-city": "近郊山路",
    "mountain-county-road": "山地县道",
    "mountain-scenic": "山景线路",
    "mountain-landmark": "山地地标",
    "coast-checkin": "海边打卡",
}

SUPPORT_LABELS = {
    "fuel": "适合补油",
    "lodging": "适合过夜",
    "repair": "附近有维修支撑",
    "viewpoint": "适合观景停留",
}

SEASON_LABELS = {
    "spring": "春季",
    "summer": "夏季",
    "autumn": "秋季",
    "winter": "冬季",
}

RIDE_LEVEL_LABELS = {
    "beginner": "新手友好",
    "intermediate": "需要一定山路经验",
    "advanced": "适合长途老手",
}

STAY_DURATION_MAP = {
    "1 小时": {"min_hours": 1, "max_hours": 1, "is_overnight": False},
    "1-2 小时": {"min_hours": 1, "max_hours": 2, "is_overnight": False},
    "1-3 小时": {"min_hours": 1, "max_hours": 3, "is_overnight": False},
    "2 小时": {"min_hours": 2, "max_hours": 2, "is_overnight": False},
    "2-3 小时": {"min_hours": 2, "max_hours": 3, "is_overnight": False},
    "2-4 小时": {"min_hours": 2, "max_hours": 4, "is_overnight": False},
    "半天": {"min_hours": 4, "max_hours": 6, "is_overnight": False},
    "半天 / 过夜": {"min_hours": 4, "max_hours": 16, "is_overnight": True},
}

ROAD_FEATURES_BY_TYPE = {
    "mountain": ["连续弯道", "林间路段", "起伏明显"],
    "supply-stop": ["县城补给", "住宿友好", "停车方便"],
    "mountain-view": ["观景平台", "上山道路", "到达感强"],
    "scenic-water": ["景区慢速路", "山水观景", "适合停拍"],
    "county-road": ["县道探索", "补给稀疏", "节奏灵活"],
    "riverside-village": ["村道慢骑", "江边停靠", "适合晨昏拍摄"],
    "city-riverside": ["城市沿江", "夜景友好", "到达收官"],
    "border-landmark": ["边境地标", "短暂停靠", "目的地感强"],
    "coast": ["临海道路", "风景连续", "适合巡航"],
    "coast-city": ["城市近郊", "半日轻骑", "海景易出片"],
    "coast-scenic": ["景观路段", "停车拍照", "休闲节奏"],
    "coast-history": ["海景混合人文", "停靠点密集", "慢节奏"],
    "seasonal-landscape": ["季节窗口明显", "观景停留", "主题性强"],
    "plain-road": ["直线巡航", "风阻明显", "适合日落线"],
    "mountain-near-city": ["周末短途", "近郊盘山", "出发门槛低"],
    "mountain-county-road": ["穿山县道", "探索感强", "弯道更碎"],
    "mountain-scenic": ["山门地标", "盘山进出", "适合串联"],
    "mountain-landmark": ["地标到达", "支线路段", "停留型节点"],
    "coast-checkin": ["海边集合", "轻旅行开场", "短暂停靠"],
}

NEARBY_SPOT_SLUGS = {
    "benhuan-highway": ["huanren-county", "wunvshan"],
    "huanren-county": ["benhuan-highway", "wunvshan", "qingshangou"],
    "wunvshan": ["huanren-county", "benhuan-highway"],
    "qingshangou": ["kuandian-county-roads", "lujiang-village", "dandong-yalu-river"],
    "kuandian-county-roads": ["qingshangou", "lujiang-village", "hushan-great-wall-roads"],
    "lujiang-village": ["qingshangou", "kuandian-county-roads", "dandong-yalu-river"],
    "dandong-yalu-river": ["hushan-great-wall-roads", "phoenix-mountain-fengcheng", "lujiang-village"],
    "hushan-great-wall-roads": ["dandong-yalu-river", "kuandian-county-roads"],
    "dalian-binhai-road": ["bangchuidao-roads", "jinshitan", "lvshun-coast-road"],
    "bangchuidao-roads": ["dalian-binhai-road", "jinshitan"],
    "jinshitan": ["dalian-binhai-road", "bangchuidao-roads"],
    "lvshun-coast-road": ["dalian-binhai-road", "bangchuidao-roads"],
    "red-beach": ["panjin-wetland-roads"],
    "panjin-wetland-roads": ["red-beach"],
    "qianshan": ["xiuyan-mountain-roads"],
    "xiuyan-mountain-roads": ["qianshan", "phoenix-mountain-fengcheng"],
    "yiwulv-mountain": ["huludao-xingcheng-coast"],
    "phoenix-mountain-fengcheng": ["dandong-yalu-river", "xiuyan-mountain-roads"],
    "huludao-xingcheng-coast": ["juehua-island-departure", "yiwulv-mountain"],
    "juehua-island-departure": ["huludao-xingcheng-coast"],
}


LIAONING_MOTO_SPOTS: list[SpotDict] = []


def get_liaoning_moto_spots() -> list[SpotDict]:
    return [_enrich_spot(spot) for spot in _formal_spots_raw()]


def get_approved_moto_spots() -> list[SpotDict]:
    return [_enrich_spot(spot) for spot in _approved_spots_raw()]


def get_moto_spot_collection_schema() -> list[dict[str, Any]]:
    return [field.copy() for field in MOTO_SPOT_COLLECTION_SCHEMA]


def get_empty_moto_spot_record() -> SpotDict:
    return {
        key: value.copy() if isinstance(value, dict | list) else value
        for key, value in MOTO_SPOT_COLLECTION_TEMPLATE.items()
    }


def get_liaoning_moto_spot_by_slug(slug: str) -> SpotDict | None:
    spot = next((item for item in _formal_spots_raw() if item["slug"] == slug), None)
    return _enrich_spot(spot) if spot is not None else None


def build_liaoning_spot_image_gallery(spot: SpotDict) -> list[dict[str, str]]:
    return build_moto_spot_image_gallery(spot, mode="route")


def build_preview_spot_image_gallery(spot: SpotDict) -> list[dict[str, str]]:
    return build_moto_spot_image_gallery(spot, mode="inline")


def build_previewable_moto_spot_record(spot: SpotDict) -> SpotDict:
    return _enrich_spot(spot)


def build_moto_spot_image_gallery(spot: SpotDict, mode: str = "route") -> list[dict[str, str]]:
        variants = [
                {"slug": "cover", "label": "封面图卡", "caption": spot["summary"]},
                {"slug": "route", "label": "道路视角", "caption": " / ".join(spot["road_features"][:3])},
                {"slug": "photo", "label": "拍摄视角", "caption": " / ".join(spot["photo_focus"][:3])},
        ]
        return [
                {
                        "slug": item["slug"],
                        "label": item["label"],
                        "caption": item["caption"],
                    "image_url": _spot_image_url(spot, item["slug"], mode),
                }
                for item in variants
        ]


def render_liaoning_spot_image_svg(spot: SpotDict, variant: str) -> str:
        accent = {
                "cover": ("#17324d", "#8a5a2b"),
                "route": ("#0f766e", "#155e75"),
                "photo": ("#9a3412", "#7c2d12"),
        }.get(variant, ("#17324d", "#8a5a2b"))
        title = {
                "cover": spot["name"],
                "route": spot["route_type_label"],
                "photo": " / ".join(spot["photo_focus"][:2]) or spot["name"],
        }.get(variant, spot["name"])
        eyebrow = {
                "cover": f"{spot['city']} · {spot['region']}",
                "route": " · ".join(spot["best_time_of_day"]),
                "photo": "图卡浏览",
        }.get(variant, spot["city"])
        note = {
                "cover": spot["summary"],
                "route": " / ".join(spot["road_features"][:3]),
                "photo": " / ".join(spot["support_labels"][:3]),
        }.get(variant, spot["summary"])

        return f"""<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 1200 800' role='img' aria-label='{escape(spot['name'])}'>
    <defs>
        <linearGradient id='bg' x1='0%' x2='100%' y1='0%' y2='100%'>
            <stop offset='0%' stop-color='{accent[0]}' />
            <stop offset='100%' stop-color='{accent[1]}' />
        </linearGradient>
    </defs>
    <rect width='1200' height='800' fill='url(#bg)' rx='40' />
    <circle cx='1000' cy='140' r='160' fill='rgba(255,255,255,0.08)' />
    <circle cx='180' cy='660' r='220' fill='rgba(255,255,255,0.06)' />
    <path d='M80 570 C260 430 400 420 560 520 S900 650 1120 500' fill='none' stroke='rgba(255,255,255,0.24)' stroke-width='18' stroke-linecap='round' />
    <text x='90' y='120' fill='#f8fbff' font-size='28' font-family='Helvetica Neue, Arial, sans-serif' letter-spacing='4'>{escape(eyebrow)}</text>
    <text x='90' y='220' fill='#f8fbff' font-size='72' font-weight='700' font-family='Helvetica Neue, Arial, sans-serif'>{escape(title)}</text>
    <foreignObject x='90' y='270' width='860' height='180'>
        <div xmlns='http://www.w3.org/1999/xhtml' style='color:#f8fbff;font-size:30px;line-height:1.5;font-family:Helvetica Neue, Arial, sans-serif;'>
            {escape(note)}
        </div>
    </foreignObject>
    <rect x='90' y='640' width='260' height='64' rx='32' fill='rgba(255,255,255,0.16)' />
    <text x='125' y='683' fill='#f8fbff' font-size='28' font-family='Helvetica Neue, Arial, sans-serif'>{escape(spot['ride_level_label'])}</text>
    <rect x='372' y='640' width='320' height='64' rx='32' fill='rgba(255,255,255,0.16)' />
    <text x='407' y='683' fill='#f8fbff' font-size='28' font-family='Helvetica Neue, Arial, sans-serif'>{escape(spot['route_type_label'])}</text>
    <text x='900' y='700' fill='rgba(248,251,255,0.86)' font-size='24' text-anchor='end' font-family='Helvetica Neue, Arial, sans-serif'>{escape(spot['image_key'])}</text>
</svg>"""


def _spot_image_url(spot: SpotDict, variant: str, mode: str) -> str:
        preferred_image = _spot_collected_image_url(spot, variant)
        if preferred_image:
                return preferred_image
        if mode == "inline":
                svg = render_liaoning_spot_image_svg(spot, variant)
                return f"data:image/svg+xml;charset=utf-8,{quote(svg)}"
        return f"/moto/spots/liaoning/{spot['slug']}/images/{variant}.svg"


def _spot_collected_image_url(spot: SpotDict, variant: str) -> str:
    image_urls = spot.get("image_urls", [])
    if not isinstance(image_urls, list):
        return ""
    cleaned = [str(item).strip() for item in image_urls if str(item).strip()]
    if not cleaned:
        return ""
    variant_index = {"cover": 0, "route": 1, "photo": 2}.get(variant, 0)
    if variant_index < len(cleaned):
        return cleaned[variant_index]
    return cleaned[0]


def _enrich_spot(spot: SpotDict) -> SpotDict:
    base = get_empty_moto_spot_record()
    enriched = {
        key: value.copy() if isinstance(value, dict | list) else value
        for key, value in base.items()
    }
    for key, value in spot.items():
        enriched[key] = value.copy() if isinstance(value, dict | list) else value

    route_type = enriched["route_type"] or "unknown"
    ride_level = enriched["ride_level"] or "beginner"
    best_seasons = enriched["best_seasons"] if isinstance(enriched["best_seasons"], list) else []
    support_role = enriched["support_role"] if isinstance(enriched["support_role"], list) else []
    photo_focus = enriched["photo_focus"] if isinstance(enriched["photo_focus"], list) else []
    image_urls = enriched["image_urls"] if isinstance(enriched.get("image_urls"), list) else []

    if not enriched["name"]:
        enriched["name"] = "未命名点位"
    if not enriched["summary"]:
        enriched["summary"] = "这是一条等待补充摘要的摩旅点位记录。"
    enriched["image_urls"] = [str(item).strip() for item in image_urls if str(item).strip()]
    if not enriched["image_key"]:
        enriched["image_key"] = f"preview-{enriched['slug'] or 'spot'}"

    enriched["route_type_label"] = ROUTE_TYPE_LABELS.get(route_type, route_type if route_type != "unknown" else "未分类")
    enriched["season_labels"] = [SEASON_LABELS.get(item, item) for item in best_seasons]
    enriched["ride_level_label"] = RIDE_LEVEL_LABELS.get(ride_level, ride_level)
    enriched["support_labels"] = [SUPPORT_LABELS.get(item, item) for item in support_role]
    enriched["support_flags"] = {key: key in support_role for key in SUPPORT_LABELS}
    enriched["stay_duration"] = STAY_DURATION_MAP.get(
        enriched["recommended_stay"],
        {"min_hours": 1, "max_hours": 2, "is_overnight": False},
    )
    if not enriched["best_time_of_day"]:
        enriched["best_time_of_day"] = _best_time_of_day(photo_focus)
    if not enriched["road_features"]:
        enriched["road_features"] = _road_features(route_type, photo_focus)
    if not enriched["risk_notes"]:
        enriched["risk_notes"] = _risk_notes(enriched)
    if not enriched["route_tags"]:
        enriched["route_tags"] = _route_tags(enriched)
    enriched["nearby_spots"] = _nearby_spots(enriched["slug"])
    enriched["image_gallery"] = build_liaoning_spot_image_gallery(enriched)
    return enriched


def _best_time_of_day(photo_focus: list[str]) -> list[str]:
    joined = " ".join(photo_focus)
    slots: list[str] = []
    if "日出" in joined or "晨" in joined:
        slots.append("清晨")
    if "日落" in joined or "夕阳" in joined:
        slots.append("傍晚")
    if "夜景" in joined:
        slots.append("夜间")
    if not slots:
        slots.append("白天")
    return slots


def _road_features(route_type: str, photo_focus: list[str]) -> list[str]:
    features = list(ROAD_FEATURES_BY_TYPE.get(route_type, []))
    if any("弯" in item for item in photo_focus):
        features.append("适合动态骑行拍摄")
    if any("停车" in item or "停靠" in item for item in photo_focus):
        features.append("停车拍照方便")
    if any("夜景" in item for item in photo_focus):
        features.append("夜间氛围明显")
    return features


def _risk_notes(spot: SpotDict) -> list[str]:
    notes: list[str] = []
    if spot["ride_level"] == "intermediate":
        notes.append("更适合有山路或连续转弯经验的骑手")
    if spot["route_type"] in {"mountain", "mountain-county-road", "county-road"}:
        notes.append("出发前确认山区路况与天气，避免夜间压弯")
    if spot["route_type"] in {"coast", "coast-city", "coast-scenic", "coast-history", "coast-checkin", "plain-road"}:
        notes.append("沿海和平原路段风阻更明显，注意横风和补水")
    if spot["route_type"] == "seasonal-landscape":
        notes.append("季节窗口很强，非旺季观感会明显下降")
    if "lodging" not in spot["support_role"]:
        notes.append("建议作为中途停拍节点，不建议把住宿完全押在这里")
    return notes


def _route_tags(spot: SpotDict) -> list[str]:
    tags = [spot["region"], spot["route_type"], spot["ride_level"]]
    if "viewpoint" in spot["support_role"]:
        tags.append("photo-friendly")
    if "fuel" in spot["support_role"]:
        tags.append("fuel-friendly")
    if "lodging" in spot["support_role"]:
        tags.append("overnight-friendly")
    return tags


def _nearby_spots(slug: str) -> list[dict[str, str]]:
    catalog = {item["slug"]: item for item in _formal_spots_raw()}
    return [
        {
            "slug": item_slug,
            "name": catalog[item_slug]["name"],
            "city": catalog[item_slug]["city"],
            "href": f"/moto/spots/liaoning/{item_slug}",
        }
        for item_slug in NEARBY_SPOT_SLUGS.get(slug, [])
        if item_slug in catalog
    ]


def _formal_spots_raw() -> list[SpotDict]:
    return _approved_spots_raw()


def _approved_spots_raw() -> list[SpotDict]:
    if not APPROVED_SPOTS_PATH.exists():
        return []
    data = json.loads(APPROVED_SPOTS_PATH.read_text(encoding="utf-8"))
    items = data if isinstance(data, list) else []
    return [
        {
            key: value.copy() if isinstance(value, dict | list) else value
            for key, value in item.items()
        }
        for item in items
        if isinstance(item, dict) and item.get("slug")
    ]


def build_liaoning_spot_detail_context(spot: SpotDict) -> dict[str, Any]:
    video_analysis = _detail_video_analysis(spot)
    fixed_spot_info = _detail_fixed_spot_info(spot)
    keyframe_paths = _detail_keyframes(spot)
    return {
        "spot": {
            "name": spot["name"],
            "city": spot["city"],
            "region": spot["region"],
            "summary": spot["summary"],
            "recommended_stay": spot["recommended_stay"],
            "route_type": spot["route_type_label"],
            "best_seasons": spot["season_labels"],
            "ride_level": spot["ride_level_label"],
            "photo_focus": spot["photo_focus"],
            "support_role": spot["support_labels"],
            "best_time_of_day": spot["best_time_of_day"],
            "road_features": spot["road_features"],
            "risk_notes": spot["risk_notes"],
            "nearby_spots": spot["nearby_spots"],
            "stay_duration": spot["stay_duration"],
            "route_tags": spot["route_tags"],
            "image_gallery": spot["image_gallery"],
            "sources": [
                {
                    "type": item.get("type", ""),
                    "name": item.get("name", ""),
                    "url": item.get("url", ""),
                    "author": item.get("author", ""),
                    "verified": item.get("verified", False),
                    "note": item.get("note", ""),
                }
                for item in spot.get("sources", [])
            ],
            "video_url": str(spot.get("video_url") or spot.get("videoUrl") or "").strip(),
            "keyframes": [
                {
                    "path": item,
                    "label": f"关键帧 {index + 1}",
                    "href": f"/moto/spots/collect/keyframes/{item.replace('data/raw/openclaw_keyframes/', '', 1)}",
                }
                for index, item in enumerate(keyframe_paths)
            ],
            "video_analysis": video_analysis,
            "fixed_spot_info": fixed_spot_info,
        },
        "actions": [
            {"label": "返回路线规划", "href": "/moto/planner"},
            {"label": "查看热门路线", "href": "/moto/routes"},
        ],
    }


def _detail_keyframes(spot: SpotDict) -> list[str]:
    value = spot.get("keyframe_paths") or spot.get("keyframePaths") or []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


def _detail_video_analysis(spot: SpotDict) -> dict[str, Any]:
    value = spot.get("video_analysis") or spot.get("videoAnalysis") or {}
    if not isinstance(value, dict):
        value = {}
    return {
        "transcript": str(value.get("transcript") or "").strip(),
        "ocrText": str(value.get("ocrText") or value.get("ocr_text") or "").strip(),
        "summary": str(value.get("summary") or "").strip(),
        "sceneSummary": str(value.get("sceneSummary") or value.get("scene_summary") or "").strip(),
        "keywords": _detail_string_list(value.get("keywords")),
        "sceneLabels": _detail_string_list(value.get("sceneLabels") or value.get("scene_labels")),
        "placeHints": _detail_string_list(value.get("placeHints") or value.get("place_hints")),
        "supportHints": _detail_string_list(value.get("supportHints") or value.get("support_hints")),
        "routeHints": _detail_string_list(value.get("routeHints") or value.get("route_hints")),
        "spotMarkers": _detail_string_list(value.get("spotMarkers") or value.get("spot_markers")),
        "captions": _detail_string_list(value.get("captions")),
    }


def _detail_fixed_spot_info(spot: SpotDict) -> dict[str, Any]:
    value = spot.get("fixed_spot_info") or spot.get("fixedSpotInfo") or {}
    if not isinstance(value, dict):
        value = {}
    return {
        "city": str(value.get("city") or "").strip(),
        "region": str(value.get("region") or "").strip(),
        "poiType": str(value.get("poiType") or value.get("poi_type") or "").strip(),
        "routeType": str(value.get("routeType") or value.get("route_type") or "").strip(),
        "supportTags": _detail_string_list(value.get("supportTags") or value.get("support_tags")),
        "spotMarkers": _detail_string_list(value.get("spotMarkers") or value.get("spot_markers")),
        "photoTags": _detail_string_list(value.get("photoTags") or value.get("photo_tags")),
        "summary": str(value.get("summary") or "").strip(),
    }


def _detail_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if value in (None, ""):
        return []
    return [str(value).strip()]