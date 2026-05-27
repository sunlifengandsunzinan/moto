from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SEED_PATH = PROJECT_ROOT / "data" / "raw" / "map_seed_queries.json"
RAW_PATH = PROJECT_ROOT / "data" / "raw" / "map_candidates.json"
SOURCE_AUTHOR = "OpenStreetMap contributors"


def fetch_nominatim(seed: dict[str, Any]) -> list[dict[str, Any]]:
    params = urlencode(
        {
            "q": f"{seed['city']} {seed['query']}",
            "format": "jsonv2",
            "limit": "5",
            "addressdetails": "1",
        }
    )
    request = Request(
        f"https://nominatim.openstreetmap.org/search?{params}",
        headers={"User-Agent": "moto-planner-candidate-collector/1.0"},
    )
    with urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def build_search_url(seed: dict[str, Any]) -> str:
    return f"https://nominatim.openstreetmap.org/search?{urlencode({'q': f"{seed['city']} {seed['query']}", 'format': 'jsonv2', 'limit': '5', 'addressdetails': '1'})}"


def build_item_url(item: dict[str, Any]) -> str:
    lat = item.get("lat")
    lon = item.get("lon")
    if lat and lon:
        return f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=15/{lat}/{lon}"
    return "https://www.openstreetmap.org"


def convert_result(seed: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    raw_name = item.get("display_name", seed["query"]).split(",")[0].strip()
    slug = raw_name.lower().replace(" ", "-").replace("/", "-")
    slug = "".join(ch for ch in slug if ch.isalnum() or ch == "-") or seed["query"].lower()
    return {
        "source_type": "map",
        "source_name": "nominatim",
        "source_author": SOURCE_AUTHOR,
        "source_query_url": build_search_url(seed),
        "source_item_url": build_item_url(item),
        "slug": f"{seed['city']}-{slug}",
        "raw_name": raw_name,
        "city": seed["city"],
        "region": seed["region"],
        "route_type": "supply-stop" if seed["category"] != "scenic-spot" else "coast",
        "lat": float(item.get("lat", 0.0)),
        "lng": float(item.get("lon", 0.0)),
        "category": seed["category"],
        "parking_friendly": seed["category"] != "support-stop",
        "support_tags": support_tags(seed["category"], seed["query"]),
        "summary_hint": f"来自地图采集的候选点：{raw_name}",
        "photo_tags": [seed["query"]],
        "captured_at": "2026-05-27",
    }


def support_tags(category: str, query: str) -> list[str]:
    tags: list[str] = []
    if category == "moto-station":
        tags.extend(["fuel", "lodging"])
    if "加油" in query:
        tags.append("fuel")
    if "停车" in query or category == "scenic-spot":
        tags.append("viewpoint")
    return sorted(set(tags))


def main() -> None:
    seeds = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    collected: list[dict[str, Any]] = []
    for seed in seeds:
        try:
            results = fetch_nominatim(seed)
        except Exception as exc:
            print(f"skip {seed['city']} {seed['query']}: {exc}")
            continue
        collected.extend(convert_result(seed, item) for item in results)

    existing = json.loads(RAW_PATH.read_text(encoding="utf-8")) if RAW_PATH.exists() else []
    merged = {item["slug"]: item for item in existing}
    for item in collected:
        merged[item["slug"]] = item

    RAW_PATH.write_text(json.dumps(list(merged.values()), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"collected {len(collected)} raw candidates -> {RAW_PATH}")


if __name__ == "__main__":
    main()