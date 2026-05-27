from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
NORMALIZED_PATH = PROJECT_ROOT / "data" / "normalized" / "candidate_spots.json"


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


def load_all_raw_candidates() -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for path in sorted(RAW_DIR.glob("*_candidates.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        items = data if isinstance(data, list) else []
        for item in items:
            if not isinstance(item, dict):
                continue
            slug = str(item.get("slug") or "").strip()
            if not slug:
                continue
            merged[slug] = item
    return list(merged.values())


def main() -> None:
    raw_items = load_all_raw_candidates()
    normalized = [normalize_raw_candidate(item) for item in raw_items]
    NORMALIZED_PATH.write_text(json.dumps(normalized, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"normalized {len(normalized)} candidate spots -> {NORMALIZED_PATH}")


if __name__ == "__main__":
    main()
