from __future__ import annotations

import argparse
import json
import math
import re
import sys
import tempfile
import time
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.route_templates_config import ROUTE_TEMPLATES_JSON_PATH, validate_route_templates_file


DEFAULT_SOURCE_DIR = Path("/root/data/moto")
IMPORT_MARKER = "data-moto-route-import"
WAYPOINT_DISTANCE_PATTERN = re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*km", re.IGNORECASE)
NON_WORD_PATTERN = re.compile(r"[^a-z0-9]+")

REGION_KEYWORDS = {
    "northeast": {"辽宁", "沈阳", "丹东", "本溪", "宽甸", "桓仁", "营口", "盖州", "盘锦", "大连", "旅顺", "锦州", "辽河", "七星山", "七星湖", "绿江村", "青山沟", "虎谷峡", "回龙湖"},
    "east": {"杭州", "上海", "苏州", "无锡", "宁波", "绍兴", "南京", "黄山", "皖南", "安吉", "莫干山"},
    "south": {"海南", "三亚", "海口", "桂林", "南宁", "广州", "深圳"},
    "north": {"北京", "天津", "河北", "承德", "秦皇岛", "山海关", "草原"},
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import route analysis files from data/moto into app/services/route_templates.json")
    parser.add_argument("--source-dir", default=str(DEFAULT_SOURCE_DIR), help="Directory containing route analysis JSON files")
    parser.add_argument("--source", action="append", dest="sources", help="Explicit source JSON file(s) to import in addition to --source-dir")
    parser.add_argument("--route-file", default=str(ROUTE_TEMPLATES_JSON_PATH), help="Canonical route template file to update")
    parser.add_argument("--dry-run", action="store_true", help="Do not write changes; print the import summary only")
    parser.add_argument("--interval-seconds", type=int, default=0, help="When > 0, keep polling and importing on a fixed interval")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source_dir = Path(args.source_dir).resolve()
    route_file = Path(args.route_file).resolve()
    explicit_sources = [Path(value).resolve() for value in args.sources or []]

    if args.interval_seconds > 0:
        while True:
            result = sync_once(source_dir, explicit_sources, route_file, dry_run=args.dry_run)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            time.sleep(args.interval_seconds)
    else:
        result = sync_once(source_dir, explicit_sources, route_file, dry_run=args.dry_run)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def sync_once(source_dir: Path, explicit_sources: list[Path], route_file: Path, *, dry_run: bool) -> dict[str, Any]:
    source_dir.mkdir(parents=True, exist_ok=True)
    source_files = discover_source_files(source_dir, explicit_sources)
    route_items = load_route_items(source_files)
    selected_items = dedupe_route_items(route_items)
    imported_routes = [build_route_template(item) for item in selected_items]
    existing_routes = json.loads(route_file.read_text(encoding="utf-8"))
    merged_routes, stats = merge_routes(existing_routes, imported_routes)
    validate_payload(merged_routes)

    if not dry_run:
        write_route_file(route_file, merged_routes)

    return {
        "ok": True,
        "dry_run": dry_run,
        "source_dir": str(source_dir),
        "source_files": [str(path) for path in source_files],
        "discovered_route_items": len(route_items),
        "selected_route_items": len(selected_items),
        "route_file": str(route_file),
        **stats,
        "imported_slugs": [route["slug"] for route in imported_routes],
    }


def discover_source_files(source_dir: Path, explicit_sources: list[Path]) -> list[Path]:
    discovered = sorted(path for path in source_dir.glob("*.json") if path.is_file())
    for path in explicit_sources:
        if path.is_file() and path not in discovered:
            discovered.append(path)
    return discovered


def load_route_items(source_files: list[Path]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for path in source_files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        raw_items = unwrap_route_items(payload)
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            if not is_importable_route(item):
                continue
            items.append({**item, "_source_file": str(path)})
    return items


def unwrap_route_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        for key in ("routes", "items", "candidates"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return []
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def is_importable_route(item: Mapping[str, Any]) -> bool:
    route_analysis = item.get("route_analysis") if isinstance(item.get("route_analysis"), dict) else {}
    route_order = route_analysis.get("route_order") if isinstance(route_analysis.get("route_order"), list) else []
    waypoint_names = route_analysis.get("waypoint_names") if isinstance(route_analysis.get("waypoint_names"), list) else []
    return bool(route_analysis.get("has_route_info")) and len(route_order or waypoint_names) >= 2


def dedupe_route_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best_by_key: dict[str, dict[str, Any]] = {}
    for item in items:
        key = dedupe_key(item)
        current = best_by_key.get(key)
        if current is None or compare_items(item, current) > 0:
            best_by_key[key] = item
    return list(best_by_key.values())


def dedupe_key(item: Mapping[str, Any]) -> str:
    note_id = str(item.get("note_id") or "").strip()
    if note_id:
        return f"note:{note_id}"
    note_url = str(((item.get("data_source") or {}).get("note_url") if isinstance(item.get("data_source"), dict) else "") or "").strip()
    if note_url:
        return f"url:{note_url}"
    title = str(((item.get("basic_info") or {}).get("title") if isinstance(item.get("basic_info"), dict) else "") or "").strip()
    route_order = item.get("route_analysis", {}).get("route_order", []) if isinstance(item.get("route_analysis"), dict) else []
    return f"fallback:{title}:{'|'.join(str(name) for name in route_order)}"


def compare_items(left: Mapping[str, Any], right: Mapping[str, Any]) -> int:
    left_tuple = item_priority(left)
    right_tuple = item_priority(right)
    return (left_tuple > right_tuple) - (left_tuple < right_tuple)


def item_priority(item: Mapping[str, Any]) -> tuple[float, int, int, int]:
    engagement = item.get("engagement") if isinstance(item.get("engagement"), dict) else {}
    route_analysis = item.get("route_analysis") if isinstance(item.get("route_analysis"), dict) else {}
    score = float((item.get("score") or (item.get("ollama_review") or {}).get("score") or 0) or 0)
    heat = sum(int(engagement.get(key) or 0) for key in ("likes", "collects", "comments", "shares"))
    waypoint_count = len(route_analysis.get("route_order") or route_analysis.get("waypoint_names") or [])
    description_len = len(str(((item.get("basic_info") or {}).get("description") if isinstance(item.get("basic_info"), dict) else "") or ""))
    return (score, heat, waypoint_count, description_len)


def build_route_template(item: Mapping[str, Any]) -> dict[str, Any]:
    basic_info = item.get("basic_info") if isinstance(item.get("basic_info"), dict) else {}
    route_analysis = item.get("route_analysis") if isinstance(item.get("route_analysis"), dict) else {}
    data_source = item.get("data_source") if isinstance(item.get("data_source"), dict) else {}
    title = str(basic_info.get("title") or "未命名路线").strip()
    description = str(basic_info.get("description") or "").strip()
    tags = split_tags(basic_info.get("tag_list"))
    waypoint_names = route_analysis.get("route_order") if isinstance(route_analysis.get("route_order"), list) and route_analysis.get("route_order") else route_analysis.get("waypoint_names") or []
    waypoints = build_navigation_waypoints(waypoint_names, route_analysis.get("waypoint_coords"))
    days = infer_days(route_analysis)
    distance_km = infer_distance_km(route_analysis)
    region = infer_region(title, description, tags, waypoint_names)
    difficulty = infer_difficulty(distance_km, days)
    scenery_type = infer_scenery_types(title, description, tags, waypoint_names)
    bike_types = infer_bike_types(distance_km, days, scenery_type)
    experience_levels = infer_experience_levels(difficulty)
    best_season = infer_best_season(tags, description)
    budget_range = infer_budget_range(distance_km, days)
    source_url = str(data_source.get("note_url") or "").strip()
    source_keyword = str(basic_info.get("source_keyword") or data_source.get("source_keyword") or "").strip()
    note_id = str(item.get("note_id") or "").strip()
    summary = build_summary(title, description, waypoint_names, days, distance_km)
    days_plan = build_days_plan(waypoint_names, route_analysis.get("segments"), days, distance_km)
    imported_at = datetime.now(timezone.utc).isoformat()

    return {
        "slug": build_slug(note_id, source_url),
        "title": title,
        "region": region,
        "spot_slugs": [],
        "days": days,
        "difficulty": difficulty,
        "scenery_type": scenery_type,
        "bike_types": bike_types,
        "experience_levels": experience_levels,
        "best_season": best_season,
        "distance_km": distance_km,
        "budget_range": budget_range,
        "summary": summary,
        "navigation": {
            "provider": "amap",
            "waypoints": waypoints,
        },
        "days_plan": days_plan,
        "pois": {
            "fuel": [],
            "repair": [],
            "lodging": [],
            "viewpoint": build_viewpoints(waypoint_names),
            "emergency": [],
        },
        "detail_highlights": build_detail_highlights(tags, waypoint_names, source_keyword),
        "detail_for_whom": build_detail_for_whom(difficulty, days),
        "detail_notes": build_detail_notes(source_url, description),
        "source_import": {
            "type": IMPORT_MARKER,
            "platform": str(item.get("platform") or "").strip() or "小红书",
            "note_id": note_id,
            "note_url": source_url,
            "source_keyword": source_keyword,
            "source_file": str(item.get("_source_file") or ""),
            "score": float(item.get("score") or (item.get("ollama_review") or {}).get("score") or 0),
            "analysis_time": str(item.get("analysis_time") or data_source.get("crawl_time") or "").strip(),
            "imported_at": imported_at,
        },
    }


def build_slug(note_id: str, note_url: str) -> str:
    if note_id:
        return f"xhs-route-{note_id.lower()}"
    if note_url:
        return f"xhs-route-{NON_WORD_PATTERN.sub('-', note_url.lower()).strip('-')[:48]}"
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"xhs-route-{timestamp}"


def split_tags(raw_value: Any) -> list[str]:
    if isinstance(raw_value, list):
        return [str(item).strip() for item in raw_value if str(item).strip()]
    text = str(raw_value or "")
    return [part.strip() for part in re.split(r"[,，\n]+", text) if part.strip()]


def build_navigation_waypoints(route_order: list[Any], waypoint_coords: Any) -> list[dict[str, Any]]:
    coords_lookup = waypoint_coords if isinstance(waypoint_coords, dict) else {}
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_name in route_order:
        name = str(raw_name or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        waypoint = {"name": name}
        raw_coords = coords_lookup.get(name)
        if isinstance(raw_coords, (list, tuple)) and len(raw_coords) >= 2:
            lng, lat = raw_coords[0], raw_coords[1]
            try:
                waypoint["lng"] = float(lng)
                waypoint["lat"] = float(lat)
            except (TypeError, ValueError):
                pass
        result.append(waypoint)
    return result


def infer_days(route_analysis: Mapping[str, Any]) -> int:
    raw_days = str(route_analysis.get("estimated_days") or "").strip()
    match = re.search(r"(\d+)", raw_days)
    if match:
        return max(1, int(match.group(1)))
    segment_count = len(route_analysis.get("segments") or [])
    if segment_count:
        return max(1, min(3, segment_count))
    return 1


def infer_distance_km(route_analysis: Mapping[str, Any]) -> int:
    raw_distance = route_analysis.get("estimated_motorcycle_km") or route_analysis.get("distance_km") or 0
    try:
        return max(1, int(round(float(raw_distance))))
    except (TypeError, ValueError):
        return 1


def infer_region(title: str, description: str, tags: list[str], waypoint_names: list[Any]) -> str:
    haystack = "\n".join([title, description, *tags, *(str(name) for name in waypoint_names)])
    for region, keywords in REGION_KEYWORDS.items():
        if any(keyword in haystack for keyword in keywords):
            return region
    return "north"


def infer_difficulty(distance_km: int, days: int) -> str:
    if distance_km <= 320 and days <= 2:
        return "easy"
    return "medium"


def infer_scenery_types(title: str, description: str, tags: list[str], waypoint_names: list[Any]) -> list[str]:
    haystack = "\n".join([title, description, *tags, *(str(name) for name in waypoint_names)])
    result = ["scenic"]
    if any(keyword in haystack for keyword in ("山", "峡", "谷", "林", "湖", "沟", "峡谷", "森林")):
        result.append("mountain")
    if any(keyword in haystack for keyword in ("海", "湾", "滩", "旅顺", "大连", "渤海", "海岸")):
        result.append("coast")
    if any(keyword in haystack for keyword in ("小众", "原生态", "秘境")):
        result.append("niche")
    if any(keyword in haystack for keyword in ("周末", "放松", "露营", "约会", "轻松")):
        result.append("relaxed")
    return dedupe_preserve([item for item in result if item in {"scenic", "mountain", "coast", "niche", "relaxed"}])


def infer_bike_types(distance_km: int, days: int, scenery_type: list[str]) -> list[str]:
    result = ["150-250cc", "300-500cc"]
    if distance_km <= 220 and days <= 1:
        result.insert(0, "125-150cc")
    if distance_km >= 500:
        result.append("500cc+")
    if days >= 2 or "mountain" in scenery_type or "coast" in scenery_type:
        result.append("adv-touring")
    return dedupe_preserve([item for item in result if item in {"125-150cc", "150-250cc", "300-500cc", "500cc+", "adv-touring"}])


def infer_experience_levels(difficulty: str) -> list[str]:
    if difficulty == "easy":
        return ["beginner", "intermediate"]
    return ["intermediate", "advanced"]


def infer_best_season(tags: list[str], description: str) -> str:
    haystack = "\n".join([*tags, description])
    if any(keyword in haystack for keyword in ("秋", "红叶")):
        return "秋季"
    if any(keyword in haystack for keyword in ("夏", "露营", "草原")):
        return "春季 / 夏季 / 秋季"
    return "春季 / 秋季"


def infer_budget_range(distance_km: int, days: int) -> str:
    if distance_km >= 600 or days >= 3:
        return "2000-4000"
    return "1000-2000"


def build_summary(title: str, description: str, waypoint_names: list[Any], days: int, distance_km: int) -> str:
    snippet = description.splitlines()[0].strip() if description else ""
    if snippet:
        return snippet[:88]
    path_text = " -> ".join(str(name) for name in waypoint_names[:4])
    return f"基于小红书内容导入的 {days} 天路线，约 {distance_km} km，覆盖 {path_text}。"


def build_days_plan(waypoint_names: list[Any], raw_segments: Any, days: int, total_distance_km: int) -> list[dict[str, Any]]:
    names = [str(name).strip() for name in waypoint_names if str(name).strip()]
    segment_entries = parse_segments(raw_segments, names, total_distance_km)
    if not segment_entries:
        title = " -> ".join(names[:4]) or "路线导入"
        return [
            {
                "day": 1,
                "title": title,
                "ride_time": format_ride_time(total_distance_km),
                "distance": total_distance_km,
                "highlights": ["小红书路线导入", "待人工复核", "可继续补充 POI"],
                "note": "导入后未拆出明确分段，建议后续人工调整每日行程。",
            }
        ]

    day_count = max(1, min(days, len(segment_entries)))
    chunks = split_segments(segment_entries, day_count)
    day_plans: list[dict[str, Any]] = []
    for index, chunk in enumerate(chunks, start=1):
        distance = int(round(sum(item["distance"] for item in chunk)))
        first_name = chunk[0]["from"]
        last_name = chunk[-1]["to"]
        titles = [f"{item['from']} -> {item['to']}" for item in chunk]
        day_plans.append(
            {
                "day": index,
                "title": f"{first_name} -> {last_name}",
                "ride_time": format_ride_time(distance),
                "distance": max(distance, 1),
                "highlights": build_day_highlights(titles),
                "note": "；".join(titles),
            }
        )
    return day_plans


def parse_segments(raw_segments: Any, names: list[str], total_distance_km: int) -> list[dict[str, Any]]:
    segments: list[dict[str, Any]] = []
    if isinstance(raw_segments, list):
        for item in raw_segments:
            text = str(item or "").strip()
            if not text or "→" not in text:
                continue
            left, rest = text.split("→", 1)
            to_name = rest.split(":", 1)[0].strip()
            match = WAYPOINT_DISTANCE_PATTERN.search(text)
            distance = float(match.group(1)) if match else 0.0
            segments.append({"from": left.strip(), "to": to_name, "distance": distance})
    if segments:
        return segments
    if len(names) >= 2:
        average_distance = total_distance_km / max(1, len(names) - 1)
        for index in range(len(names) - 1):
            segments.append({"from": names[index], "to": names[index + 1], "distance": average_distance})
    return segments


def split_segments(segments: list[dict[str, Any]], day_count: int) -> list[list[dict[str, Any]]]:
    chunks: list[list[dict[str, Any]]] = []
    start = 0
    remaining_segments = len(segments)
    remaining_days = day_count
    while start < len(segments) and remaining_days > 0:
        chunk_size = max(1, math.ceil(remaining_segments / remaining_days))
        chunk = segments[start:start + chunk_size]
        chunks.append(chunk)
        start += chunk_size
        remaining_segments -= len(chunk)
        remaining_days -= 1
    return chunks


def format_ride_time(distance_km: int) -> str:
    if distance_km <= 120:
        return "建议骑行 2-3 小时"
    if distance_km <= 220:
        return "建议骑行 3-4 小时"
    if distance_km <= 320:
        return "建议骑行 4-5 小时"
    return "建议骑行 5-6 小时"


def build_day_highlights(segment_titles: list[str]) -> list[str]:
    highlights = ["小红书路线导入", "按采集结果拆分", "建议人工复核"]
    if any("海" in title or "滩" in title for title in segment_titles):
        highlights[1] = "滨海路线"
    if any("山" in title or "峡" in title or "谷" in title for title in segment_titles):
        highlights[1] = "山水路段"
    return highlights


def build_viewpoints(waypoint_names: list[Any]) -> list[dict[str, str]]:
    if not waypoint_names:
        return []
    return [{"name": str(waypoint_names[-1]), "meta": "导入路线终点 · 建议人工补充景观点信息"}]


def build_detail_highlights(tags: list[str], waypoint_names: list[Any], source_keyword: str) -> list[str]:
    result = ["来自 data/moto 的定时导入路线", "路线结构已对齐小程序展示字段"]
    if source_keyword:
        result.append(f"采集关键词：{source_keyword}")
    elif waypoint_names:
        result.append(f"覆盖 {min(len(waypoint_names), 6)} 个关键途径点")
    return result[:3]


def build_detail_for_whom(difficulty: str, days: int) -> str:
    if difficulty == "easy":
        return f"适合想做 {days} 天内中短途摩旅、并希望先看热门内容路线再决定是否出发的骑手。"
    return f"适合已有一定摩旅经验、希望按照热门内容补齐 {days} 天左右路线参考的骑手。"


def build_detail_notes(source_url: str, description: str) -> list[str]:
    notes = ["此路线由外部采集文件导入主数据源，建议人工复核后再长期保留。"]
    if source_url:
        notes.append(f"原始笔记：{source_url}")
    if description:
        notes.append(f"内容摘要：{description[:80]}")
    return notes[:3]


def dedupe_preserve(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def merge_routes(existing_routes: list[dict[str, Any]], imported_routes: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    merged = list(existing_routes)
    index_by_slug = {route.get("slug"): index for index, route in enumerate(merged)}
    inserted = 0
    updated = 0
    skipped = 0
    for route in imported_routes:
        slug = route["slug"]
        existing_index = index_by_slug.get(slug)
        if existing_index is None:
            merged.append(route)
            index_by_slug[slug] = len(merged) - 1
            inserted += 1
            continue
        existing_route = merged[existing_index]
        import_meta = existing_route.get("source_import") if isinstance(existing_route.get("source_import"), dict) else {}
        if import_meta.get("type") != IMPORT_MARKER:
            skipped += 1
            continue
        merged[existing_index] = route
        updated += 1
    return merged, {"inserted": inserted, "updated": updated, "skipped": skipped, "route_count_after": len(merged)}


def validate_payload(routes: list[dict[str, Any]]) -> None:
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as handle:
        temp_path = Path(handle.name)
        handle.write(json.dumps(routes, ensure_ascii=False, indent=2) + "\n")
    try:
        validate_route_templates_file(temp_path)
    finally:
        temp_path.unlink(missing_ok=True)


def write_route_file(route_file: Path, routes: list[dict[str, Any]]) -> None:
    route_file.write_text(json.dumps(routes, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())