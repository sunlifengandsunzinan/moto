from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INPUT_PATH = PROJECT_ROOT / "data" / "raw" / "openclaw_export.json"
OUTPUT_PATH = PROJECT_ROOT / "data" / "raw" / "openclaw_candidates.json"

CITY_REGION_MAP = {
    "沈阳": "辽中",
    "辽阳": "辽中",
    "铁岭": "辽中",
    "抚顺": "辽中",
    "本溪": "辽东",
    "桓仁": "辽东",
    "丹东": "辽东",
    "宽甸": "辽东",
    "大连": "辽南",
    "旅顺": "辽南",
    "盘锦": "辽南",
    "营口": "辽南",
    "锦州": "辽南",
    "葫芦岛": "辽南",
    "兴城": "辽南",
    "朝阳": "辽南",
    "鞍山": "辽南",
    "凤城": "辽东",
}

CITY_ALIASES = {
    "沈阳": "沈阳",
    "本溪": "本溪",
    "本桓": "本溪",
    "桓仁": "本溪",
    "五女山": "本溪",
    "丹东": "丹东",
    "宽甸": "丹东",
    "绿江村": "丹东",
    "鸭绿江": "丹东",
    "青山沟": "丹东",
    "凤城": "丹东",
    "大连": "大连",
    "旅顺": "大连",
    "滨海路": "大连",
    "棒棰岛": "大连",
    "金石滩": "大连",
    "盘锦": "盘锦",
    "红海滩": "盘锦",
    "兴城": "葫芦岛",
    "葫芦岛": "葫芦岛",
    "觉华岛": "葫芦岛",
    "千山": "鞍山",
    "岫岩": "鞍山",
}

ROUTE_TEXT_PATTERNS = [
    ("riverside-village", ["绿江村", "江边村", "村落", "边境村"]),
    ("city-riverside", ["沿江", "鸭绿江", "滨江", "江景", "河景", "river"]),
    ("coast", ["滨海", "海边", "沿海", "海岸", "海景", "coast", "sea"]),
    ("mountain-county-road", ["县道", "盘山", "穿山", "小众路", "边境线"]),
    ("mountain", ["山路", "跑山", "本桓", "凤凰山", "千山", "五女山", "mountain"]),
    ("supply-stop", ["驿站", "补给", "加油", "维修", "住宿", "休整", "service", "station"]),
    ("scenic-water", ["湖", "湿地", "景区", "观景", "打卡", "viewpoint"]),
]

SUPPORT_TEXT_PATTERNS = {
    "fuel": ["加油", "油站", "fuel", "gas", "补油"],
    "repair": ["维修", "修车", "repair", "机修", "简修", "快修"],
    "lodging": ["住宿", "过夜", "民宿", "酒店", "客栈", "lodging", "hotel"],
    "food": ["餐饮", "吃饭", "面馆", "饭店", "咖啡", "coffee", "早餐", "补给餐"],
    "viewpoint": ["观景", "拍照", "出片", "夜景", "机车合影", "view", "photo"],
}

MOTO_STATION_FEATURE_PATTERNS = {
    "可停车": ["停车", "停车位", "院内停车", "好停车"],
    "骑友集合": ["集合", "骑友", "机车聚会", "发车点"],
    "可过夜": ["住宿", "过夜", "民宿", "酒店"],
    "可补给": ["加油", "补给", "餐饮", "便利店"],
    "可简单维修": ["维修", "修车", "机修", "简修", "快修"],
}


def adapt_openclaw_candidate(item: dict[str, Any]) -> dict[str, Any]:
    text_blob = collect_text_blob(item)
    title = infer_title(item, text_blob)
    slug = str(first_value(item, ["slug", "id", "poi_id", "poiId"]) or title).strip().lower().replace(" ", "-")
    slug = "".join(ch for ch in slug if ch.isalnum() or ch == "-") or "openclaw-candidate"

    lat, lng = extract_coordinates(item)
    city = infer_city(item, text_blob)
    region = infer_region(item, city, text_blob)
    category = infer_category(item, text_blob)
    tags = collect_tags(item)
    support_tags = infer_support_tags(category, tags, text_blob)
    route_type = infer_route_type(category, tags, text_blob)
    route_tags = infer_route_tags(city, region, route_type, tags, text_blob)
    photo_tags = infer_photo_tags(item, tags, text_blob)
    summary = infer_summary(item, title, city, route_type, support_tags)
    author = infer_author(item)
    source_name = str(first_value(item, ["platform", "platformName", "provider", "source_name", "sourceName"]) or "openclaw")
    road_features = infer_road_features(route_type, text_blob)
    moto_station_features = infer_moto_station_features(text_blob, category)
    image_urls = infer_image_urls(item)
    spot_markers = infer_spot_markers(item, category, tags, text_blob)

    return {
        "source_type": "content",
        "source_name": source_name,
        "source_author": author,
        "source_item_url": str(first_value(item, ["url", "link", "permalink", "source_url", "sourceUrl", "noteUrl", "videoUrl", "shareUrl"]) or ""),
        "slug": slug,
        "raw_name": title,
        "city": city,
        "region": region,
        "route_type": route_type,
        "lat": lat,
        "lng": lng,
        "category": category,
        "spot_markers": spot_markers,
        "parking_friendly": infer_parking_friendly(item, category),
        "support_tags": support_tags,
        "summary_hint": summary,
        "photo_tags": photo_tags,
        "image_urls": image_urls,
        "comment_location_hints": normalize_string_list(first_value(item, ["commentLocationHints", "comment_location_hints"]) or item.get("commentLocationHints") or item.get("comment_location_hints")),
        "route_tags": route_tags,
        "road_features": road_features,
        "moto_station_features": moto_station_features,
        "captured_at": str(first_value(item, ["captured_at", "capturedAt", "collected_at", "collectedAt", "discovered_at", "discoveredAt", "published_at", "publishedAt"]) or ""),
    }


def collect_text_blob(item: dict[str, Any]) -> str:
    values = [
        first_value(item, ["title", "name", "poi_name", "poiName", "note_title", "noteTitle"]),
        first_value(item, ["summary", "excerpt", "description", "snippet", "content", "desc"]),
        first_value(item, ["city", "city_name", "cityName"], nested=["location", "address"]),
        first_value(item, ["region", "district", "region_name", "regionName", "address"] , nested=["location", "address"]),
    ]
    for key in ["tags", "labels", "keywords", "topics", "photoTags", "contentTags"]:
        values.extend(normalize_string_list(item.get(key)))
    values.extend(normalize_string_list(item.get("comment_location_hints")))
    values.extend(normalize_string_list(item.get("commentLocationHints")))
    values.extend(normalize_string_list(item.get("comments")))
    for container_key in ["location", "address", "metadata", "content", "author", "user", "profile"]:
        container = item.get(container_key)
        if not isinstance(container, dict):
            continue
        for value in container.values():
            if isinstance(value, str):
                values.append(value)
            elif isinstance(value, list):
                values.extend(str(entry) for entry in value if str(entry).strip())
    text = " ".join(str(value).strip() for value in values if value not in (None, ""))
    return re.sub(r"\s+", " ", text)


def infer_title(item: dict[str, Any], text_blob: str) -> str:
    direct_title = str(first_value(item, ["title", "name", "poi_name", "poiName", "note_title", "noteTitle"]) or "").strip()
    if direct_title:
        return direct_title
    summary = str(first_value(item, ["summary", "excerpt", "description", "snippet", "content", "desc"]) or "").strip()
    if summary:
        return summary.split("。", 1)[0][:40].strip() or "candidate"
    return text_blob[:24].strip() or "candidate"


def infer_author(item: dict[str, Any]) -> str:
    direct_author = str(first_value(item, ["author", "creator", "owner", "uploader", "source_author", "sourceAuthor"]) or "").strip()
    if direct_author:
        return direct_author
    for container_key in ["author", "user", "account", "profile", "creator"]:
        container = item.get(container_key)
        if not isinstance(container, dict):
            continue
        value = first_non_empty(container, ["nickname", "name", "userName", "username", "displayName", "handle"])
        if value not in (None, ""):
            return str(value).strip()
    return ""


def infer_city(item: dict[str, Any], text_blob: str) -> str:
    direct_city = str(first_value(item, ["city", "city_name", "cityName"], nested=["location", "address"]) or "").strip()
    if direct_city:
        return canonical_city(direct_city)
    for alias, city in CITY_ALIASES.items():
        if alias in text_blob:
            return city
    return ""


def infer_region(item: dict[str, Any], city: str, text_blob: str) -> str:
    direct_region = str(first_value(item, ["region", "district", "region_name", "regionName"], nested=["location", "address"]) or "").strip()
    if direct_region:
        return direct_region
    if city:
        return CITY_REGION_MAP.get(city, "")
    for alias, canonical_city_name in CITY_ALIASES.items():
        if alias in text_blob:
            return CITY_REGION_MAP.get(canonical_city_name, "")
    return ""


def canonical_city(value: str) -> str:
    normalized = value.strip()
    for alias, city in CITY_ALIASES.items():
        if alias in normalized or normalized in alias:
            return city
    return normalized


def infer_category(item: dict[str, Any], text_blob: str) -> str:
    raw_value = str(first_value(item, ["category", "type", "poi_type", "poiType"]) or "").strip().lower()
    normalized = normalize_category(raw_value) if raw_value else ""
    if normalized and normalized != "scenic-spot":
        return normalized
    if any(keyword in text_blob.lower() for keyword in ["驿站", "rider station", "moto station", "集合点"]):
        return "moto-station"
    if any(keyword in text_blob.lower() for keyword in ["加油", "补给", "服务区", "repair", "fuel"]):
        return "support-stop"
    return normalized or "scenic-spot"


def first_value(item: dict[str, Any], keys: list[str], nested: list[str] | None = None) -> Any:
    for key in keys:
        if item.get(key) not in (None, ""):
            return item[key]
    for container_key in nested or []:
        container = item.get(container_key)
        if isinstance(container, dict):
            for key in keys:
                if container.get(key) not in (None, ""):
                    return container[key]
    return None


def extract_coordinates(item: dict[str, Any]) -> tuple[Any, Any]:
    coordinate_containers = [
        item.get("coordinates"),
        item.get("coordinate"),
        item.get("location"),
        item.get("geo"),
    ]
    for container in coordinate_containers:
        if not isinstance(container, dict):
            continue
        lat = first_non_empty(container, ["lat", "latitude"])
        lng = first_non_empty(container, ["lng", "lon", "longitude"])
        if lat not in (None, "") and lng not in (None, ""):
            return lat, lng
    return item.get("lat") or item.get("latitude"), item.get("lng") or item.get("lon") or item.get("longitude")


def infer_image_urls(item: dict[str, Any]) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for key in ["image_urls", "imageUrls", "images", "photos", "media", "gallery", "album", "covers", "thumbnails", "image", "imageUrl", "cover", "coverUrl", "thumbnail", "thumb"]:
        _collect_image_values(item.get(key), values, seen)
    for container_key in ["content", "metadata", "post", "note"]:
        container = item.get(container_key)
        if isinstance(container, dict):
            for key in ["image_urls", "imageUrls", "images", "photos", "media", "gallery", "album", "covers", "thumbnails", "image", "imageUrl", "cover", "coverUrl", "thumbnail", "thumb"]:
                _collect_image_values(container.get(key), values, seen)
    return values


def _collect_image_values(value: Any, values: list[str], seen: set[str]) -> None:
    if value in (None, ""):
        return
    if isinstance(value, list):
        for item in value:
            _collect_image_values(item, values, seen)
        return
    if isinstance(value, str):
        candidate = value.strip()
        if not candidate or candidate in seen:
            return
        if candidate.startswith("data:image/") or re.match(r"^(https?:)?//", candidate):
            seen.add(candidate)
            values.append(candidate)
        return
    if not isinstance(value, dict):
        return
    for key in ["url", "src", "href", "origin", "original", "originalUrl", "downloadUrl", "imageUrl", "imageURL", "coverUrl", "thumbnail", "thumb"]:
        _collect_image_values(value.get(key), values, seen)
    for key in ["urls", "list", "images", "items", "sources", "media"]:
        _collect_image_values(value.get(key), values, seen)


def first_non_empty(item: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        if item.get(key) not in (None, ""):
            return item[key]
    return None


def collect_tags(item: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ["tags", "labels", "keywords", "topics"]:
        values.extend(normalize_string_list(item.get(key)))
    for container_key in ["content", "metadata"]:
        container = item.get(container_key)
        if not isinstance(container, dict):
            continue
        for key in ["tags", "labels", "keywords"]:
            values.extend(normalize_string_list(container.get(key)))
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def infer_parking_friendly(item: dict[str, Any], category: str) -> bool:
    value = first_value(item, ["parking_friendly", "parkingFriendly", "parking"], nested=["features", "metadata"])
    if value in (None, ""):
        return category != "support-stop"
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"yes", "true", "1", "是"}


def normalize_category(value: str) -> str:
    mapping = {
        "fuel-stop": "support-stop",
        "gas-station": "support-stop",
        "rider-station": "moto-station",
        "viewpoint": "scenic-spot",
    }
    return mapping.get(value, value)


def normalize_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if value in (None, ""):
        return []
    text = str(value).replace("，", ",").replace("#", " ")
    if "," in text or "\n" in text:
        return [part.strip() for part in re.split(r"[,\n]", text) if part.strip()]
    return [text.strip()]


def infer_support_tags(category: str, tags: list[str], text_blob: str) -> list[str]:
    joined = f"{' '.join(tags)} {text_blob}".lower()
    support: set[str] = set()
    if category == "moto-station":
        support.update({"fuel", "lodging"})
    for tag, keywords in SUPPORT_TEXT_PATTERNS.items():
        if any(keyword.lower() in joined for keyword in keywords):
            support.add(tag)
    if category == "support-stop":
        support.add("fuel")
    if category == "scenic-spot" or any(keyword in joined for keyword in ["观景", "拍照", "view"]):
        support.add("viewpoint")
    return sorted(support)


def infer_route_type(category: str, tags: list[str], text_blob: str) -> str:
    joined = f"{' '.join(tags)} {text_blob}".lower()
    for route_type, keywords in ROUTE_TEXT_PATTERNS:
        if any(keyword.lower() in joined for keyword in keywords):
            return route_type
    if category == "moto-station" or category == "support-stop":
        return "supply-stop"
    return "scenic-water" if "江" in joined or "湖" in joined else "coast"


def infer_route_tags(city: str, region: str, route_type: str, tags: list[str], text_blob: str) -> list[str]:
    derived = [region, city, route_type]
    joined = f"{' '.join(tags)} {text_blob}".lower()
    if any(keyword in joined for keyword in ["打卡", "出片", "夜景", "封面"]):
        derived.append("photo-friendly")
    if any(keyword in joined for keyword in ["边境", "探索", "县道"]):
        derived.append("exploration")
    if any(keyword in joined for keyword in ["补给", "加油", "维修", "住宿"]):
        derived.append("support")
    if any(keyword in joined for keyword in ["轻骑", "慢节奏", "休闲"]):
        derived.append("relaxed")
    return [value for index, value in enumerate(derived) if value and value not in derived[:index]]


def infer_photo_tags(item: dict[str, Any], tags: list[str], text_blob: str) -> list[str]:
    values = normalize_string_list(first_value(item, ["content_tags", "contentTags", "photo_tags", "photoTags"]))
    values.extend(tags)
    joined = text_blob.lower()
    if any(keyword in joined for keyword in ["夜景", "灯光"]):
        values.append("夜景")
    if any(keyword in joined for keyword in ["机车合影", "人车同框", "合影"]):
        values.append("人车同框")
    if any(keyword in joined for keyword in ["沿江", "鸭绿江", "江景"]):
        values.append("沿江路")
    if any(keyword in joined for keyword in ["滨海", "海边", "海景"]):
        values.append("海景")
    if any(keyword in joined for keyword in ["盘山", "山路", "本桓"]):
        values.append("山路")
    deduped: list[str] = []
    for value in values:
        cleaned = str(value).strip()
        if cleaned and cleaned not in deduped:
            deduped.append(cleaned)
    return deduped


def infer_summary(item: dict[str, Any], title: str, city: str, route_type: str, support_tags: list[str]) -> str:
    summary = str(first_value(item, ["summary", "excerpt", "description", "snippet", "content", "desc"]) or "").strip()
    if summary:
        return summary
    support_text = "、".join(tag for tag in support_tags if tag != "viewpoint")
    if support_text:
        return f"来自 OpenClaw 的辽宁候选点：{title}，位于{city or '辽宁'}，偏 {route_type}，可提供{support_text}线索。"
    return f"来自 OpenClaw 的辽宁候选点：{title}，位于{city or '辽宁'}，偏 {route_type}。"


def infer_road_features(route_type: str, text_blob: str) -> list[str]:
    features: list[str] = []
    joined = text_blob.lower()
    if route_type.startswith("coast") or any(keyword in joined for keyword in ["滨海", "海边", "沿海"]):
        features.append("临海道路")
    if route_type.startswith("mountain") or any(keyword in joined for keyword in ["盘山", "弯道", "跑山", "本桓"]):
        features.append("山路弯道")
    if any(keyword in joined for keyword in ["县道", "边境线", "探索"]):
        features.append("县道探索")
    if any(keyword in joined for keyword in ["沿江", "鸭绿江", "江边"]):
        features.append("沿江停靠")
    return features


def infer_moto_station_features(text_blob: str, category: str) -> list[str]:
    if category != "moto-station":
        return []
    features: list[str] = []
    joined = text_blob.lower()
    for feature, keywords in MOTO_STATION_FEATURE_PATTERNS.items():
        if any(keyword.lower() in joined for keyword in keywords):
            features.append(feature)
    return features


def infer_spot_markers(item: dict[str, Any], category: str, tags: list[str], text_blob: str) -> list[str]:
    values = normalize_string_list(first_value(item, ["spotMarkers", "spot_markers"]))
    joined = f"{' '.join(tags)} {text_blob}".lower()
    if category == "moto-station" or any(keyword in joined for keyword in ["驿站", "骑士站", "moto station", "rider station"]):
        values.append("moto-station")
    if any(keyword in joined for keyword in ["加油", "油站", "fuel", "gas station", "petrol"]):
        values.append("fuel-station")
    if any(keyword in joined for keyword in ["咖啡", "coffee", "cafe"]):
        values.append("coffee-stop")
    if category == "support-stop":
        values.append("support-stop")
    if category == "scenic-spot" or any(keyword in joined for keyword in ["打卡", "观景", "拍照", "出片", "checkpoint", "check in", "check-in", "viewpoint"]):
        values.append("checkin-point")
    deduped: list[str] = []
    for value in values:
        marker = str(value).strip()
        if marker and marker not in deduped:
            deduped.append(marker)
    return deduped


def load_input_items() -> list[dict[str, Any]]:
    data = json.loads(INPUT_PATH.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        for key in ["items", "results", "records", "data"]:
            items = data.get(key)
            if isinstance(items, list):
                return [item for item in items if isinstance(item, dict)]
    return []


def load_existing_output() -> list[dict[str, Any]]:
    if not OUTPUT_PATH.exists():
        return []
    data = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else []


def main() -> None:
    items = load_input_items()
    adapted = [adapt_openclaw_candidate(item) for item in items]

    merged = {item["slug"]: item for item in load_existing_output()}
    for item in adapted:
        merged[item["slug"]] = item

    OUTPUT_PATH.write_text(json.dumps(list(merged.values()), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"adapted {len(adapted)} OpenClaw candidates -> {OUTPUT_PATH}")


if __name__ == "__main__":
    main()