from __future__ import annotations

import math
import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
NORMALIZED_PATH = PROJECT_ROOT / "data" / "normalized" / "candidate_spots.json"

GENERIC_NAME_TOKENS = [
    "辽宁",
    "摩旅",
    "摩托",
    "机车",
    "骑士",
    "驿站",
    "集合点",
    "集合",
    "打卡点",
    "打卡",
    "停靠点",
    "停靠位",
    "停靠",
    "观景台",
    "观景点",
    "观景",
    "咖啡站",
    "咖啡",
    "加油站",
    "油站",
    "补给点",
    "补给",
    "服务点",
    "服务站",
    "骑行",
]


def infer_source_author(item: dict[str, Any]) -> str:
    if item.get("source_author"):
        return str(item["source_author"])
    if item.get("source_type") == "map" or item.get("source_name") in {"osm", "nominatim"}:
        return "OpenStreetMap contributors"
    return ""


def infer_source_url(item: dict[str, Any]) -> str:
    if item.get("source_item_url"):
        return str(item["source_item_url"])
    if item.get("source_query_url"):
        return str(item["source_query_url"])

    lat = item.get("lat")
    lng = item.get("lng")
    if (item.get("source_type") == "map" or item.get("source_name") in {"osm", "nominatim"}) and lat and lng:
        return f"https://www.openstreetmap.org/?mlat={lat}&mlon={lng}#map=15/{lat}/{lng}"
    return ""


def normalize_raw_candidate(item: dict[str, Any]) -> dict[str, Any]:
    slug = item.get("slug") or str(item.get("raw_name", "candidate")).strip().lower().replace(" ", "-")
    support_tags = item.get("support_tags", [])
    confidence_score = "B" if item.get("lat") and item.get("lng") and support_tags else "C"
    route_tags = [str(tag).strip() for tag in item.get("route_tags", []) if str(tag).strip()]
    if item.get("region") and item.get("region") not in route_tags:
        route_tags.insert(0, str(item.get("region")))
    road_features = [str(feature).strip() for feature in item.get("road_features", []) if str(feature).strip()]
    moto_station_features = [str(feature).strip() for feature in item.get("moto_station_features", []) if str(feature).strip()]
    return {
        "slug": slug,
        "name": item.get("raw_name", ""),
        "spot_type": item.get("category", "scenic-spot"),
        "spot_markers": normalize_string_list(item.get("spot_markers") or item.get("spotMarkers")),
        "city": item.get("city", ""),
        "region": item.get("region", ""),
        "route_type": item.get("route_type", ""),
        "coordinates": {"lat": item.get("lat"), "lng": item.get("lng")},
        "access_level": "easy",
        "parking_friendly": item.get("parking_friendly"),
        "best_seasons": [],
        "best_time_of_day": [],
        "ride_level": "beginner",
        "recommended_stay": "1-2 小时",
        "road_features": road_features,
        "risk_notes": [],
        "summary": item.get("summary_hint", ""),
        "photo_focus": item.get("photo_tags", []),
        "image_urls": normalize_image_urls(
            item.get("image_urls")
            or item.get("imageUrls")
            or item.get("source_images")
            or item.get("sourceImages")
        ),
        "image_key": f"candidate-{slug}",
        "route_tags": route_tags,
        "nearby_spot_slugs": [],
        "fuel_support": "nearby" if "fuel" in support_tags else "unknown",
        "repair_support": "available" if "repair" in support_tags else "unknown",
        "lodging_support": "available" if "lodging" in support_tags else "unknown",
        "food_support": "available" if "food" in support_tags else "unknown",
        "support_role": support_tags,
        "moto_station_features": moto_station_features or (["可停车"] if item.get("category") == "moto-station" else []),
        "confidence_score": confidence_score,
        "sources": [
            {
                "type": item.get("source_type", "raw"),
                "name": item.get("source_name", "unknown"),
                "url": infer_source_url(item),
                "author": infer_source_author(item),
                "verified": False,
                "note": " | ".join(
                    part
                    for part in [
                        f"captured_at={item.get('captured_at', '')}" if item.get("captured_at") else "",
                        f"query_url={item.get('source_query_url', '')}" if item.get("source_query_url") else "",
                    ]
                    if part
                ),
            }
        ],
        "last_verified_at": "",
    }


def normalize_image_urls(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if value in (None, ""):
        return []
    text = str(value).strip()
    return [text] if text else []


def normalize_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if value in (None, ""):
        return []
    text = str(value).replace("，", ",").replace("\n", ",")
    return [part.strip() for part in text.split(",") if part.strip()]


def merge_raw_candidates(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    for item in items:
        match_index = next((index for index, existing in enumerate(merged) if _raw_candidates_match(existing, item)), None)
        if match_index is None:
            merged.append(_copy_candidate(item))
            continue
        merged[match_index] = _merge_raw_candidate_pair(merged[match_index], item)
    return merged


def _raw_candidates_match(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_slug = str(left.get("slug") or "").strip()
    right_slug = str(right.get("slug") or "").strip()
    if left_slug and right_slug and left_slug == right_slug:
        return True

    left_url = str(left.get("source_item_url") or "").strip()
    right_url = str(right.get("source_item_url") or "").strip()
    if left_url and right_url and left_url == right_url:
        return True

    left_city = str(left.get("city") or "").strip()
    right_city = str(right.get("city") or "").strip()
    if not left_city or not right_city or left_city != right_city:
        return False

    left_name = _canonical_place_name(str(left.get("raw_name") or ""))
    right_name = _canonical_place_name(str(right.get("raw_name") or ""))
    if left_name and right_name and left_name == right_name:
        return True

    if left_name and right_name and _coordinates_close(left, right, max_distance_km=1.2):
        return _name_similarity(left_name, right_name) >= 0.55

    if _coordinates_close(left, right, max_distance_km=0.25):
        return True

    return False


def _merge_raw_candidate_pair(primary: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = _copy_candidate(primary)
    fallback = _copy_candidate(incoming)

    for key in [
        "slug",
        "city",
        "region",
        "route_type",
        "category",
        "source_type",
        "source_name",
        "source_author",
        "source_item_url",
        "source_query_url",
        "captured_at",
    ]:
        if not merged.get(key) and fallback.get(key):
            merged[key] = fallback[key]

    for key in ["raw_name", "summary_hint"]:
        merged[key] = _prefer_richer_text(merged.get(key), fallback.get(key))

    for key in ["lat", "lng"]:
        if merged.get(key) in (None, "") and fallback.get(key) not in (None, ""):
            merged[key] = fallback[key]

    if merged.get("parking_friendly") is None and fallback.get("parking_friendly") is not None:
        merged["parking_friendly"] = fallback["parking_friendly"]

    for key in [
        "support_tags",
        "photo_tags",
        "route_tags",
        "road_features",
        "moto_station_features",
        "image_urls",
        "spot_markers",
        "comment_location_hints",
    ]:
        merged[key] = _merge_string_lists(merged.get(key), fallback.get(key))

    return merged


def _copy_candidate(item: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value.copy() if isinstance(value, list | dict) else value
        for key, value in item.items()
    }


def _prefer_richer_text(left: Any, right: Any) -> str:
    left_text = str(left or "").strip()
    right_text = str(right or "").strip()
    return right_text if len(right_text) > len(left_text) else left_text


def _merge_string_lists(left: Any, right: Any) -> list[str]:
    merged: list[str] = []
    for value in [*normalize_string_list(left), *normalize_string_list(right)]:
        if value not in merged:
            merged.append(value)
    return merged


def _canonical_place_name(value: str) -> str:
    text = value.strip().lower().replace(" ", "")
    for token in GENERIC_NAME_TOKENS:
        text = text.replace(token, "")
    cleaned = []
    for character in text:
        if character.isalnum() or "\u4e00" <= character <= "\u9fff":
            cleaned.append(character)
    return "".join(cleaned)


def _name_similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    shared = len(set(left) & set(right))
    return shared / max(len(set(left + right)), 1)


def _coordinates_close(left: dict[str, Any], right: dict[str, Any], max_distance_km: float) -> bool:
    left_lat = _to_float(left.get("lat"))
    left_lng = _to_float(left.get("lng"))
    right_lat = _to_float(right.get("lat"))
    right_lng = _to_float(right.get("lng"))
    if None in {left_lat, left_lng, right_lat, right_lng}:
        return False
    return _haversine_km(left_lat, left_lng, right_lat, right_lng) <= max_distance_km


def _to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    radius_km = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lng = math.radians(lng2 - lng1)
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    a = math.sin(d_lat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(d_lng / 2) ** 2
    return 2 * radius_km * math.asin(math.sqrt(a))


def load_all_raw_candidates() -> list[dict[str, Any]]:
    collected: list[dict[str, Any]] = []
    for path in sorted(RAW_DIR.glob("*_candidates.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        items = data if isinstance(data, list) else []
        for item in items:
            if not isinstance(item, dict):
                continue
            slug = str(item.get("slug") or "").strip()
            if not slug:
                continue
            collected.append(item)
    return merge_raw_candidates(collected)


def main() -> None:
    raw_items = load_all_raw_candidates()
    normalized = [normalize_raw_candidate(item) for item in raw_items]
    NORMALIZED_PATH.write_text(json.dumps(normalized, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"normalized {len(normalized)} candidate spots -> {NORMALIZED_PATH}")


if __name__ == "__main__":
    main()
