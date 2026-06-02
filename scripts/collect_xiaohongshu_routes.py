from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.adapt_openclaw_candidates import adapt_openclaw_candidate
from scripts.gpx_generator import analyze_video_route_content, extract_place_names, find_coords
from scripts.run_local_social_collection import TASK_SPEC
from scripts.run_local_social_collection import collect_text
from scripts.run_local_social_collection import dedupe_strings
from scripts.run_local_social_collection import extract_meta_tags
from scripts.run_local_social_collection import extract_text
from scripts.run_local_social_collection import fetch_remote_text
from scripts.run_local_social_collection import is_supported_search_result_url
from scripts.run_local_social_collection import normalize_string_list
from scripts.run_local_social_collection import now_iso
from scripts.run_local_social_collection import search_live_items
from scripts.run_local_social_collection import sync_pending_candidate_queue
from scripts.run_local_social_collection import update_status


DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "data" / "raw" / "xiaohongshu_route_manifest.json"
DEFAULT_RAW_CANDIDATES_PATH = PROJECT_ROOT / "data" / "raw" / "xiaohongshu_route_candidates.json"
DEFAULT_STATUS_PATH = PROJECT_ROOT / "data" / "raw" / "local_collection_status.json"
DEFAULT_LOG_PATH = PROJECT_ROOT / "data" / "raw" / "xiaohongshu_route_collection.log"
DEFAULT_TIMEOUT_SECONDS = 30

DEFAULT_ROUTE_KEYWORDS = [
    "摩旅路线",
    "摩旅路线推荐",
    "摩旅西藏路线",
    "摩旅新疆路线",
    "自驾路线",
    "自驾游路线推荐",
    "自驾川藏线",
    "阿里大环线",
    "滇藏线 路书",
    "318川藏线 攻略",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect Xiaohongshu moto route notes with live public search and free local route extraction.")
    parser.add_argument("--source", action="append", dest="sources", help="Wrapped JSON source file(s). If omitted, the script runs live Xiaohongshu keyword discovery.")
    parser.add_argument("--keyword", action="append", dest="keywords", help="Extra keyword(s) to search.")
    parser.add_argument("--max-items", type=int, default=6, help="Per-keyword result cap.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="Manifest output path.")
    parser.add_argument("--raw-candidates-output", default=str(DEFAULT_RAW_CANDIDATES_PATH), help="Raw candidate output path used before syncing into the pending-review queue.")
    parser.add_argument("--status", default=str(DEFAULT_STATUS_PATH), help="Status file path used by the collector monitor page.")
    parser.add_argument("--log-path", default=str(DEFAULT_LOG_PATH), help="Display-only log path written into the status payload for monitoring.")
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS, help="Timeout for metadata fetch.")
    parser.add_argument("--skip-queue-sync", action="store_true", help="Do not sync qualified route candidates into the pending-review queue.")
    return parser.parse_args()


def read_json_file(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def unwrap_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("items"), list):
        source = payload["items"]
    elif isinstance(payload, list):
        source = payload
    else:
        source = []
    return [item for item in source if isinstance(item, dict)]


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_status_payload(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = read_json_file(path)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def current_cycle_index(status_path: Path) -> int:
    return int(read_status_payload(status_path).get("cycle_count") or 0) + 1


def build_xiaohongshu_tasks(max_items: int, extra_keywords: list[str] | None = None) -> list[dict[str, Any]]:
    keyword_pool = [*DEFAULT_ROUTE_KEYWORDS, *(extra_keywords or [])]
    tasks: list[dict[str, Any]] = []
    for keyword in dedupe_strings(keyword_pool):
        tasks.append({"platform": "xiaohongshu", "keyword": keyword, "province": TASK_SPEC["province"], "limit": max_items})
        for hint in ["路书", "路线", "攻略", "行程", "摩旅", "自驾"]:
            tasks.append({"platform": "xiaohongshu", "keyword": f"{keyword} {hint}", "province": TASK_SPEC["province"], "limit": max_items, "content_hint": hint})
    return tasks


def discover_items(source_paths: list[Path], max_items: int, extra_keywords: list[str] | None = None) -> list[dict[str, Any]]:
    if source_paths:
        items: list[dict[str, Any]] = []
        for path in source_paths:
            if path.exists():
                items.extend(unwrap_items(read_json_file(path)))
        return items

    items: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for task in build_xiaohongshu_tasks(max_items, extra_keywords):
        for item in search_live_items(task):
            source_url = extract_text(item, ["sourceUrl", "source_url", "url", "link", "permalink"])
            if not source_url or source_url in seen_urls:
                continue
            seen_urls.add(source_url)
            items.append(item)
    return items


def build_dedupe_key(item: dict[str, Any]) -> str:
    for field_group in [
        ["sourceUrl", "source_url", "url", "link", "permalink"],
        ["name", "title", "poiName", "note_title"],
        ["summary", "excerpt", "description", "content"],
    ]:
        text = extract_text(item, field_group)
        if text:
            return text.strip()
    return json.dumps(item, ensure_ascii=False, sort_keys=True)


def normalize_manifest_item(raw_item: dict[str, Any], timeout_seconds: int) -> dict[str, Any]:
    source_url = extract_text(raw_item, ["sourceUrl", "source_url", "url", "link", "permalink"])
    title = extract_text(raw_item, ["title", "name", "poiName", "note_title"])
    excerpt = extract_text(raw_item, ["summary", "excerpt", "description", "content"])
    local_text = collect_text(raw_item)
    page_payload = ""
    page_meta: dict[str, str] = {}
    should_fetch_remote = not (title and excerpt and local_text)
    if should_fetch_remote and source_url and is_supported_search_result_url("xiaohongshu", source_url):
        try:
            page_payload = fetch_remote_text(source_url, timeout_seconds=timeout_seconds)
            page_meta = extract_meta_tags(page_payload)
        except Exception:
            page_payload = ""
            page_meta = {}

    title = title or page_meta.get("og:title", "")
    excerpt = excerpt or page_meta.get("description", "") or page_meta.get("og:description", "")
    all_text = local_text
    if page_payload and page_payload not in all_text:
        all_text = f"{title}\n{excerpt}\n{page_payload[:8000]}".strip()

    return {
        "platform": "xiaohongshu",
        "dedupeKey": build_dedupe_key(raw_item),
        "name": title or excerpt[:40] or "xiaohongshu-route",
        "sourceUrl": source_url,
        "owner": extract_text(raw_item, ["owner", "author", "creator", "userName", "nickname"]) or page_meta.get("author", "") or page_meta.get("og:site_name", ""),
        "excerpt": excerpt,
        "keywords": normalize_string_list(raw_item.get("keywords") or raw_item.get("tags") or raw_item.get("labels") or page_meta.get("keywords")),
        "imageUrls": normalize_string_list(raw_item.get("imageUrls") or raw_item.get("image_urls")),
        "capturedAt": now_iso(),
        "publishedAt": str(raw_item.get("publishedAt") or page_meta.get("article:published_time") or page_meta.get("og:time") or "").strip(),
        "text": all_text,
    }


def resolved_route_locations(location_names: list[str]) -> list[dict[str, Any]]:
    resolved: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for name in location_names:
        if name in seen_names:
            continue
        coords = find_coords(name)
        if coords is None:
            continue
        seen_names.add(name)
        resolved.append(
            {
                "name": name,
                "lat": float(coords["lat"]),
                "lng": float(coords["lng"]),
                "source": coords.get("source") or "坐标字典",
            }
        )
    return resolved


def analyze_route_candidate(item: dict[str, Any]) -> dict[str, Any]:
    info = {"title": item.get("name") or "", "author": item.get("owner") or ""}
    all_text = "\n".join(filter(None, [str(item.get("name") or "").strip(), str(item.get("excerpt") or "").strip(), str(item.get("text") or "").strip()]))
    place_candidates = extract_place_names(all_text)
    analysis = analyze_video_route_content(info, all_text, place_candidates)
    resolved_locations = resolved_route_locations(analysis.get("locations") or [])
    qualification_status = "qualified" if analysis.get("route_content") and len(resolved_locations) >= 2 else "rejected"
    qualification_reason = str(analysis.get("qualification_reason") or "").strip()
    if qualification_status != "qualified" and not qualification_reason:
        qualification_reason = "未提取到明确路线内容或可定位路线点不足 2 个"
    return {
        **item,
        "routeAnalysis": {
            "title": str(analysis.get("route_title") or item.get("name") or "").strip(),
            "summary": str(analysis.get("route_summary") or "").strip(),
            "content": str(analysis.get("route_content") or "").strip(),
            "routeDays": analysis.get("route_days"),
            "distanceKm": analysis.get("distance_km"),
            "locations": analysis.get("locations") or [],
            "resolvedLocations": resolved_locations,
            "qualificationStatus": qualification_status,
            "qualificationReason": qualification_reason,
        },
    }


def build_queue_source_item(item: dict[str, Any]) -> dict[str, Any]:
    route_analysis = item.get("routeAnalysis") if isinstance(item.get("routeAnalysis"), dict) else {}
    resolved_locations = route_analysis.get("resolvedLocations") if isinstance(route_analysis.get("resolvedLocations"), list) else []
    return {
        "platform": "xiaohongshu",
        "title": str(route_analysis.get("title") or item.get("name") or "").strip(),
        "summary": str(route_analysis.get("content") or item.get("excerpt") or "").strip(),
        "url": str(item.get("sourceUrl") or "").strip(),
        "author": str(item.get("owner") or "").strip(),
        "keywords": normalize_string_list(item.get("keywords")),
        "imageUrls": normalize_string_list(item.get("imageUrls")),
        "publishedAt": str(item.get("publishedAt") or item.get("capturedAt") or "").strip(),
        "videoAnalysis": {
            "summary": str(route_analysis.get("summary") or item.get("excerpt") or "").strip(),
            "sceneSummary": str(route_analysis.get("content") or "").strip(),
            "placeHints": [location.get("name") for location in resolved_locations if isinstance(location, dict)],
            "routeHints": [str(route_analysis.get("content") or "").strip()],
        },
        "fixedSpotInfo": {
            "summary": str(route_analysis.get("summary") or "").strip(),
            "routeType": "moto-route",
            "poiType": "route",
        },
        "metadata": {
            "route_days": route_analysis.get("routeDays"),
            "distance_km": route_analysis.get("distanceKm"),
            "resolved_locations": resolved_locations,
            "source_channel": "xiaohongshu-route-collector",
        },
    }


def build_raw_candidates(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    raw_candidates: list[dict[str, Any]] = []
    for item in items:
        route_analysis = item.get("routeAnalysis") if isinstance(item.get("routeAnalysis"), dict) else {}
        if str(route_analysis.get("qualificationStatus") or "") != "qualified":
            continue
        raw_candidate = adapt_openclaw_candidate(build_queue_source_item(item))
        raw_candidate["source_channel"] = "xiaohongshu-route-collector"
        raw_candidate["route_content"] = str(route_analysis.get("content") or "").strip()
        raw_candidate["resolved_locations"] = route_analysis.get("resolvedLocations") or []
        raw_candidates.append(raw_candidate)
    return raw_candidates


def update_monitor_status(
    status_path: Path,
    log_path: Path,
    output_path: Path,
    raw_candidates_path: Path,
    cycle_index: int,
    run_stats: dict[str, int],
    duration_seconds: float,
    queue_sync: dict[str, int],
) -> None:
    update_status(
        status_path,
        collector_name="xiaohongshu-route-collector",
        state="success",
        health="ok",
        run_mode="once",
        current_stage="idle",
        current_task="当前无采集任务",
        pipeline_status="skipped",
        pipeline_summary="collected xiaohongshu route notes -> filtered qualified route candidates",
        script_command=".venv/bin/python scripts/collect_xiaohongshu_routes.py",
        output_path=str(output_path),
        raw_candidates_path=str(raw_candidates_path),
        log_path=str(log_path),
        cycle_count=cycle_index,
        last_heartbeat=now_iso(),
        last_success_at=now_iso(),
        last_duration_seconds=duration_seconds,
        items_collected=run_stats["qualified"],
        tasks_completed=run_stats["matched"],
        tasks_total=run_stats["matched"],
        pending_candidates_processed=queue_sync["processed"],
        pending_candidates_added=queue_sync["added"],
        pending_candidates_updated=queue_sync["updated"],
        pending_candidates_total=queue_sync["total"],
        event_message=(
            f"小红书路线采集完成：匹配 {run_stats['matched']} 条，"
            f"合格路线 {run_stats['qualified']} 条，拒绝 {run_stats['rejected']} 条。"
        ),
        cycle_entry={
            "cycle": cycle_index,
            "finished_at": now_iso(),
            "state": "success",
            "items_collected": run_stats["qualified"],
            "tasks_completed": run_stats["matched"],
            "tasks_total": run_stats["matched"],
            "duration_seconds": duration_seconds,
            "pending_candidates_processed": queue_sync["processed"],
            "pending_candidates_added": queue_sync["added"],
            "pending_candidates_updated": queue_sync["updated"],
            "pending_candidates_total": queue_sync["total"],
        },
    )


def main() -> None:
    args = parse_args()
    started_at = datetime.now(timezone.utc)
    source_paths = [Path(value).resolve() for value in args.sources] if args.sources else []
    status_path = Path(args.status).resolve()
    output_path = Path(args.output).resolve()
    raw_candidates_path = Path(args.raw_candidates_output).resolve()
    log_path = Path(args.log_path).resolve()
    cycle_index = current_cycle_index(status_path)

    discovered = discover_items(source_paths, args.max_items, args.keywords or [])
    manifest_items = [normalize_manifest_item(item, args.timeout_seconds) for item in discovered if is_xiaohongshu_candidate(item)]
    analyzed_items = [analyze_route_candidate(item) for item in manifest_items]
    raw_candidates = build_raw_candidates(analyzed_items)

    payload = {
        "source": "xiaohongshu-route-collector",
        "exported_at": now_iso(),
        "items": analyzed_items,
        "stats": {
            "discovered": len(discovered),
            "matched": len(analyzed_items),
            "qualified": sum(1 for item in analyzed_items if str((item.get("routeAnalysis") or {}).get("qualificationStatus") or "") == "qualified"),
            "rejected": sum(1 for item in analyzed_items if str((item.get("routeAnalysis") or {}).get("qualificationStatus") or "") != "qualified"),
            "queued": len(raw_candidates),
        },
    }
    write_json(output_path, payload)
    write_json(raw_candidates_path, raw_candidates)

    if args.skip_queue_sync:
        queue_sync = {"processed": 0, "added": 0, "updated": 0, "total": 0}
    else:
        queue_sync = sync_pending_candidate_queue(raw_candidates)

    run_stats = {
        "matched": payload["stats"]["matched"],
        "qualified": payload["stats"]["qualified"],
        "rejected": payload["stats"]["rejected"],
    }
    duration_seconds = round((datetime.now(timezone.utc) - started_at).total_seconds(), 2)
    update_monitor_status(status_path, log_path, output_path, raw_candidates_path, cycle_index, run_stats, duration_seconds, queue_sync)

    print(
        "xiaohongshu route collection completed: "
        f"{payload['stats']['matched']} matched / {payload['stats']['qualified']} qualified / "
        f"{payload['stats']['rejected']} rejected / queue +{queue_sync['added']} ~{queue_sync['updated']} -> {args.output}"
    )


def is_xiaohongshu_candidate(item: dict[str, Any]) -> bool:
    platform = str(item.get("platform") or "").strip().lower()
    if platform and platform != "xiaohongshu":
        return False
    source_url = extract_text(item, ["sourceUrl", "source_url", "url", "link", "permalink"])
    return is_supported_search_result_url("xiaohongshu", source_url)


if __name__ == "__main__":
    main()