from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.run_local_social_collection import HTTP_USER_AGENT
from scripts.run_local_social_collection import TASK_SPEC
from scripts.run_local_social_collection import sync_pending_candidate_queue
from scripts.run_local_social_collection import collect_text
from scripts.run_local_social_collection import dedupe_strings
from scripts.run_local_social_collection import extract_meta_tags
from scripts.run_local_social_collection import extract_text
from scripts.run_local_social_collection import fetch_remote_text
from scripts.run_local_social_collection import is_supported_search_result_url
from scripts.run_local_social_collection import normalize_string_list
from scripts.run_local_social_collection import now_iso
from scripts.run_local_social_collection import search_live_items
from scripts.run_local_social_collection import update_status
from scripts.adapt_openclaw_candidates import adapt_openclaw_candidate


DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "data" / "raw" / "douyin_video_manifest.json"
DEFAULT_DOWNLOAD_ROOT = PROJECT_ROOT / "data" / "raw" / "douyin_videos"
DEFAULT_RAW_CANDIDATES_PATH = PROJECT_ROOT / "data" / "raw" / "douyin_video_candidates.json"
DEFAULT_STATUS_PATH = PROJECT_ROOT / "data" / "raw" / "local_collection_status.json"
DEFAULT_LOG_PATH = PROJECT_ROOT / "data" / "raw" / "douyin_collection.log"
DEFAULT_REGISTRY_PATH = PROJECT_ROOT / "data" / "raw" / "douyin_video_registry.json"
DEFAULT_TIMEOUT_SECONDS = 45
DOUYIN_HOST_HINTS = ("douyin.com", "iesdouyin.com")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect Douyin video candidates with pure Python and download direct video files when available.")
    parser.add_argument("--source", action="append", dest="sources", help="Wrapped JSON source file(s). If omitted, the script runs live Douyin keyword discovery.")
    parser.add_argument("--keyword", action="append", dest="keywords", help="Extra keyword(s) to search, such as 辽宁 摩旅打卡点.")
    parser.add_argument("--max-items", type=int, default=6, help="Per-keyword result cap.")
    parser.add_argument("--download-limit", type=int, default=5, help="Maximum number of matching videos to download in one run.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="Manifest output path.")
    parser.add_argument("--download-root", default=str(DEFAULT_DOWNLOAD_ROOT), help="Local directory used to store downloaded MP4 files.")
    parser.add_argument("--raw-candidates-output", default=str(DEFAULT_RAW_CANDIDATES_PATH), help="Raw candidate output path used before syncing into the pending-review queue.")
    parser.add_argument("--status", default=str(DEFAULT_STATUS_PATH), help="Status file path used by the collector monitor page.")
    parser.add_argument("--log-path", default=str(DEFAULT_LOG_PATH), help="Display-only log path written into the status payload for monitoring.")
    parser.add_argument("--registry-path", default=str(DEFAULT_REGISTRY_PATH), help="Persistent registry used to avoid downloading the same video across runs.")
    parser.add_argument("--run-interval-minutes", type=int, default=10, help="Expected external run interval used for monitor display.")
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS, help="Timeout for metadata fetch and downloads.")
    parser.add_argument("--skip-queue-sync", action="store_true", help="Do not sync downloaded candidates into the pending-review queue.")
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


def load_registry(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"downloaded": []}
    try:
        payload = read_json_file(path)
    except json.JSONDecodeError:
        return {"downloaded": []}
    return payload if isinstance(payload, dict) else {"downloaded": []}


def save_registry(path: Path, payload: dict[str, Any]) -> None:
    write_json(path, payload)


def registry_entry_keys(value: Any) -> set[str]:
    entries = value if isinstance(value, list) else []
    keys: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        for field in ["dedupe_key", "sourceUrl", "videoUrl"]:
            text = str(entry.get(field) or "").strip()
            if text:
                keys.add(text)
    return keys


def build_dedupe_key(item: dict[str, Any]) -> str:
    for field_group in [
        ["sourceUrl", "source_url", "url", "link", "permalink"],
        ["videoUrl", "video_url", "playUrl", "downloadUrl"],
        ["name", "title", "poiName", "note_title"],
    ]:
        text = extract_text(item, field_group)
        if text:
            return text.strip()
    return json.dumps(item, ensure_ascii=False, sort_keys=True)


def build_douyin_tasks(max_items: int, extra_keywords: list[str] | None = None) -> list[dict[str, Any]]:
    keyword_pool = [*TASK_SPEC["keywords"], *(extra_keywords or [])]
    tasks = []
    for keyword in dedupe_strings(keyword_pool):
        tasks.append({"platform": "douyin", "keyword": keyword, "province": TASK_SPEC["province"], "limit": max_items})
        for hint in TASK_SPEC["social_keywords"]:
            tasks.append({"platform": "douyin", "keyword": f"{keyword} {hint}", "province": TASK_SPEC["province"], "limit": max_items, "content_hint": hint})
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
    for task in build_douyin_tasks(max_items, extra_keywords):
        for item in search_live_items(task):
            source_url = extract_text(item, ["sourceUrl", "source_url", "url", "link", "permalink", "videoUrl"])
            if not source_url or source_url in seen_urls:
                continue
            seen_urls.add(source_url)
            items.append(item)
    return items


def normalize_manifest_item(raw_item: dict[str, Any], timeout_seconds: int) -> dict[str, Any]:
    source_url = extract_text(raw_item, ["sourceUrl", "source_url", "url", "link", "permalink", "videoUrl"])
    video_url = extract_text(raw_item, ["videoUrl", "video_url", "playUrl", "downloadUrl"])
    page_payload = ""
    page_meta: dict[str, str] = {}
    if source_url and is_supported_search_result_url("douyin", source_url):
        try:
            page_payload = fetch_remote_text(source_url, timeout_seconds=timeout_seconds)
            page_meta = extract_meta_tags(page_payload)
        except Exception:
            page_payload = ""
            page_meta = {}
    if not video_url:
        video_url = resolve_douyin_video_url(source_url, page_payload, page_meta)
    return {
        "platform": "douyin",
        "dedupeKey": build_dedupe_key(raw_item),
        "name": extract_text(raw_item, ["name", "title", "poiName", "note_title"]) or extract_text(raw_item, ["summary", "excerpt", "description", "content"])[:40] or "douyin-candidate",
        "sourceUrl": source_url,
        "videoUrl": video_url,
        "owner": extract_text(raw_item, ["owner", "author", "creator", "userName", "nickname"]) or page_meta.get("author", ""),
        "excerpt": extract_text(raw_item, ["excerpt", "summary", "description", "content"]) or page_meta.get("description", ""),
        "keywords": normalize_string_list(raw_item.get("keywords") or raw_item.get("tags") or raw_item.get("labels")),
        "imageUrls": normalize_string_list(raw_item.get("imageUrls") or raw_item.get("image_urls")),
        "capturedAt": now_iso(),
        "downloadStatus": "pending" if video_url else "missing-video-url",
        "downloadError": "",
        "localVideoPath": "",
        "text": collect_text(raw_item),
    }


def resolve_douyin_video_url(source_url: str, payload: str, meta: dict[str, str]) -> str:
    direct_candidates = [
        meta.get("og:video", ""),
        meta.get("og:video:url", ""),
        meta.get("twitter:player:stream", ""),
    ]
    direct_candidates.extend(extract_video_candidates_from_payload(payload, source_url))
    for candidate in direct_candidates:
        normalized = normalize_candidate_url(candidate, source_url)
        if is_douyin_video_asset_url(normalized):
            return normalized
    return ""


def extract_video_candidates_from_payload(payload: str, base_url: str) -> list[str]:
    if not payload:
        return []
    patterns = [
        r'"playAddr"\s*:\s*"([^"]+)"',
        r'"downloadAddr"\s*:\s*"([^"]+)"',
        r'"playApi"\s*:\s*"([^"]+)"',
        r'"src"\s*:\s*"([^"]+iesdouyin\.com[^"]+)"',
        r'"url_list"\s*:\s*\[(.*?)\]',
    ]
    results: list[str] = []
    for pattern in patterns:
        for match in re.finditer(pattern, payload, flags=re.IGNORECASE | re.DOTALL):
            value = match.group(1).strip()
            if pattern.endswith(r'\[(.*?)\]'):
                results.extend(re.findall(r'"([^"]+)"', value))
                continue
            results.append(value)
    return [normalize_candidate_url(value, base_url) for value in results if value]


def normalize_candidate_url(value: str, base_url: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = text.replace("\\/", "/")
    text = text.encode("utf-8").decode("unicode_escape") if "\\u" in text else text
    if text.startswith("//"):
        return f"https:{text}"
    if text.startswith("/"):
        return urljoin(base_url, text)
    return text


def is_douyin_video_asset_url(url: str) -> bool:
    if not url:
        return False
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()
    if not any(hint in host for hint in DOUYIN_HOST_HINTS):
        return False
    text = f"{parsed.path}?{parsed.query}".lower()
    return any(token in text for token in ["/play/", "playwm", "video/tos", "download", ".mp4"])


def slugify(value: str) -> str:
    slug = re.sub(r"\s+", "-", str(value or "candidate").strip().lower())
    slug = re.sub(r"[^a-z0-9\u4e00-\u9fa5-]", "", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or "candidate"


def download_video(url: str, destination: Path, source_url: str, timeout_seconds: int) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = Request(
        url,
        headers={
            "User-Agent": HTTP_USER_AGENT,
            "Referer": source_url or "https://www.douyin.com/",
            "Accept": "video/*,*/*;q=0.8",
        },
    )
    with urlopen(request, timeout=timeout_seconds) as response:
        with destination.open("wb") as handle:
            while True:
                chunk = response.read(1024 * 256)
                if not chunk:
                    break
                handle.write(chunk)


def process_downloads(items: list[dict[str, Any]], download_root: Path, download_limit: int, timeout_seconds: int) -> list[dict[str, Any]]:
    downloaded = 0
    for item in items:
        if downloaded >= download_limit:
            if item.get("downloadStatus") == "pending":
                item["downloadStatus"] = "skipped-limit"
            continue
        video_url = str(item.get("videoUrl") or "").strip()
        if not video_url:
            continue
        file_slug = slugify(item.get("name") or item.get("sourceUrl") or "douyin-video")
        destination = download_root / f"{file_slug}.mp4"
        try:
            download_video(video_url, destination, str(item.get("sourceUrl") or ""), timeout_seconds)
        except Exception as error:
            item["downloadStatus"] = "download-error"
            item["downloadError"] = str(error)
            continue
        item["downloadStatus"] = "downloaded"
        item["downloadError"] = ""
        item["localVideoPath"] = str(destination.relative_to(PROJECT_ROOT))
        item["downloadedAt"] = now_iso()
        downloaded += 1
    return items


def dedupe_manifest_items(items: list[dict[str, Any]], registry: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    seen_in_run: set[str] = set()
    historical_keys = registry_entry_keys(registry.get("downloaded"))
    stats = {
        "duplicates_in_run": 0,
        "already_downloaded": 0,
        "eligible": 0,
    }
    result: list[dict[str, Any]] = []
    for item in items:
        keys = [
            str(item.get("dedupeKey") or "").strip(),
            str(item.get("sourceUrl") or "").strip(),
            str(item.get("videoUrl") or "").strip(),
        ]
        keys = [key for key in keys if key]
        if any(key in seen_in_run for key in keys):
            item["downloadStatus"] = "skipped-duplicate"
            stats["duplicates_in_run"] += 1
            result.append(item)
            continue
        if any(key in historical_keys for key in keys):
            item["downloadStatus"] = "skipped-downloaded-history"
            stats["already_downloaded"] += 1
            result.append(item)
            seen_in_run.update(keys)
            continue
        seen_in_run.update(keys)
        stats["eligible"] += 1
        result.append(item)
    return result, stats


def append_registry_downloads(registry: dict[str, Any], items: list[dict[str, Any]]) -> dict[str, Any]:
    downloaded = registry.get("downloaded") if isinstance(registry.get("downloaded"), list) else []
    existing_keys = registry_entry_keys(downloaded)
    for item in items:
        if str(item.get("downloadStatus") or "") != "downloaded":
            continue
        dedupe_key = str(item.get("dedupeKey") or "").strip()
        source_url = str(item.get("sourceUrl") or "").strip()
        video_url = str(item.get("videoUrl") or "").strip()
        if any(key in existing_keys for key in [dedupe_key, source_url, video_url] if key):
            continue
        downloaded.insert(
            0,
            {
                "dedupe_key": dedupe_key,
                "sourceUrl": source_url,
                "videoUrl": video_url,
                "localVideoPath": str(item.get("localVideoPath") or "").strip(),
                "downloadedAt": str(item.get("downloadedAt") or now_iso()),
                "name": str(item.get("name") or "").strip(),
            },
        )
        existing_keys.update(key for key in [dedupe_key, source_url, video_url] if key)
    registry["downloaded"] = downloaded[:2000]
    registry["last_updated_at"] = now_iso()
    return registry


def build_queue_source_item(item: dict[str, Any]) -> dict[str, Any]:
    local_video_path = str(item.get("localVideoPath") or "").strip()
    excerpt = str(item.get("excerpt") or "").strip()
    if local_video_path and local_video_path not in excerpt:
        excerpt = f"{excerpt} 本地视频: {local_video_path}".strip()
    return {
        "platform": "douyin",
        "title": str(item.get("name") or "").strip(),
        "summary": excerpt,
        "url": str(item.get("sourceUrl") or "").strip(),
        "author": str(item.get("owner") or "").strip(),
        "keywords": normalize_string_list(item.get("keywords")),
        "imageUrls": normalize_string_list(item.get("imageUrls")),
        "publishedAt": str(item.get("capturedAt") or item.get("downloadedAt") or "").strip(),
        "videoUrl": str(item.get("videoUrl") or "").strip(),
        "localVideoPath": local_video_path,
        "videoAnalysis": {
            "summary": excerpt,
            "captions": [local_video_path] if local_video_path else [],
        },
        "metadata": {
            "localVideoPath": local_video_path,
            "downloadStatus": str(item.get("downloadStatus") or "").strip(),
        },
    }


def build_raw_candidates(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    raw_candidates: list[dict[str, Any]] = []
    for item in items:
        if str(item.get("downloadStatus") or "") != "downloaded":
            continue
        raw_candidate = adapt_openclaw_candidate(build_queue_source_item(item))
        raw_candidate["local_video_path"] = str(item.get("localVideoPath") or "").strip()
        raw_candidates.append(raw_candidate)
    return raw_candidates


def build_run_stats(items: list[dict[str, Any]], dedupe_stats: dict[str, int], queue_sync: dict[str, int]) -> dict[str, int]:
    return {
        "matched": len(items),
        "downloaded": sum(1 for item in items if item.get("downloadStatus") == "downloaded"),
        "download_errors": sum(1 for item in items if item.get("downloadStatus") == "download-error"),
        "missing_video_url": sum(1 for item in items if item.get("downloadStatus") == "missing-video-url"),
        "duplicates_in_run": dedupe_stats.get("duplicates_in_run", 0),
        "already_downloaded": dedupe_stats.get("already_downloaded", 0),
        "skipped_limit": sum(1 for item in items if item.get("downloadStatus") == "skipped-limit"),
        "queued_added": int(queue_sync.get("added") or 0),
        "queued_updated": int(queue_sync.get("updated") or 0),
        "queued_total": int(queue_sync.get("total") or 0),
    }


def classify_failure_reason(item: dict[str, Any]) -> str:
    status = str(item.get("downloadStatus") or "").strip()
    if status == "missing-video-url":
        return "parse"
    error_text = str(item.get("downloadError") or "").strip().lower()
    if any(token in error_text for token in ["permission denied", "read-only", "no space left", "is a directory", "file exists", "not a directory"]):
        return "write"
    if any(token in error_text for token in ["timeout", "timed out", "connection", "ssl", "reset by peer", "temporarily unavailable", "name or service", "http error", "url error", "remote end closed"]):
        return "network"
    if status == "download-error":
        return "network"
    return "other"


def build_failure_event_messages(items: list[dict[str, Any]]) -> list[dict[str, str]]:
    buckets: dict[str, list[dict[str, Any]]] = {
        "parse": [],
        "network": [],
        "write": [],
        "other": [],
    }
    for item in items:
        status = str(item.get("downloadStatus") or "").strip()
        if status not in {"missing-video-url", "download-error"}:
            continue
        buckets[classify_failure_reason(item)].append(item)

    label_map = {
        "parse": "解析不到视频地址",
        "network": "网络失败",
        "write": "写文件失败",
        "other": "其他失败",
    }
    messages: list[dict[str, str]] = []
    for key in ["parse", "network", "write", "other"]:
        failures = buckets[key]
        if not failures:
            continue
        sample = failures[0]
        sample_name = str(sample.get("name") or sample.get("sourceUrl") or "未命名视频").strip()
        sample_reason = str(sample.get("downloadError") or sample.get("sourceUrl") or "未记录").strip()
        messages.append(
            {
                "level": "warning",
                "message": f"失败摘要：{label_map[key]} {len(failures)} 条。样例：{sample_name} · {sample_reason}",
            }
        )
    return messages


def update_monitor_status(
    status_path: Path,
    log_path: Path,
    output_path: Path,
    raw_candidates_path: Path,
    registry_path: Path,
    cycle_index: int,
    run_interval_minutes: int,
    download_limit: int,
    run_stats: dict[str, int],
    duration_seconds: float,
    queue_sync: dict[str, int],
) -> None:
    update_status(
        status_path,
        collector_name="douyin-python-video-collector",
        state="success",
        health="ok",
        run_mode="once",
        current_stage="idle",
        current_task="当前无采集任务",
        pipeline_status="skipped",
        pipeline_summary="downloaded direct videos -> synced pending review queue",
        script_command=".venv/bin/python scripts/collect_douyin_videos.py --download-limit 5",
        output_path=str(output_path),
        raw_candidates_path=str(raw_candidates_path),
        registry_path=str(registry_path),
        log_path=str(log_path),
        expected_run_interval_minutes=run_interval_minutes,
        download_limit=download_limit,
        cycle_count=cycle_index,
        last_heartbeat=now_iso(),
        last_success_at=now_iso(),
        last_duration_seconds=duration_seconds,
        items_collected=run_stats["downloaded"],
        tasks_completed=run_stats["matched"],
        tasks_total=run_stats["matched"],
        pending_candidates_processed=queue_sync["processed"],
        pending_candidates_added=queue_sync["added"],
        pending_candidates_updated=queue_sync["updated"],
        pending_candidates_total=queue_sync["total"],
        duplicate_candidates_in_run=run_stats["duplicates_in_run"],
        skipped_already_downloaded=run_stats["already_downloaded"],
        skipped_download_limit=run_stats["skipped_limit"],
        download_errors=run_stats["download_errors"],
        missing_video_url=run_stats["missing_video_url"],
        event_message=(
            f"抖音下载采集完成：下载 {run_stats['downloaded']} 条，"
            f"本轮去重跳过 {run_stats['duplicates_in_run']} 条，历史已下载跳过 {run_stats['already_downloaded']} 条。"
        ),
        cycle_entry={
            "cycle": cycle_index,
            "finished_at": now_iso(),
            "state": "success",
            "items_collected": run_stats["downloaded"],
            "tasks_completed": run_stats["matched"],
            "tasks_total": run_stats["matched"],
            "duration_seconds": duration_seconds,
            "pipeline_status": "skipped",
            "pending_candidates_processed": queue_sync["processed"],
            "pending_candidates_added": queue_sync["added"],
            "pending_candidates_updated": queue_sync["updated"],
            "pending_candidates_total": queue_sync["total"],
            "duplicate_candidates_in_run": run_stats["duplicates_in_run"],
            "skipped_already_downloaded": run_stats["already_downloaded"],
            "skipped_download_limit": run_stats["skipped_limit"],
            "download_errors": run_stats["download_errors"],
        },
    )


def main() -> None:
    args = parse_args()
    started_at = datetime.now(timezone.utc)
    source_paths = [Path(value).resolve() for value in args.sources] if args.sources else []
    status_path = Path(args.status).resolve()
    output_path = Path(args.output).resolve()
    raw_candidates_path = Path(args.raw_candidates_output).resolve()
    registry_path = Path(args.registry_path).resolve()
    log_path = Path(args.log_path).resolve()
    cycle_index = current_cycle_index(status_path)
    discovered = discover_items(source_paths, args.max_items, args.keywords or [])
    manifest_items = [normalize_manifest_item(item, args.timeout_seconds) for item in discovered if is_douyin_candidate(item)]
    registry = load_registry(registry_path)
    manifest_items, dedupe_stats = dedupe_manifest_items(manifest_items, registry)
    manifest_items = process_downloads(manifest_items, Path(args.download_root).resolve(), args.download_limit, args.timeout_seconds)
    registry = append_registry_downloads(registry, manifest_items)
    raw_candidates = build_raw_candidates(manifest_items)
    save_registry(registry_path, registry)
    payload = {
        "source": "douyin-python-collector",
        "exported_at": now_iso(),
        "items": manifest_items,
        "stats": {
            "discovered": len(discovered),
            "matched": len(manifest_items),
            "downloaded": sum(1 for item in manifest_items if item.get("downloadStatus") == "downloaded"),
            "queued": len(raw_candidates),
            "duplicates_in_run": dedupe_stats["duplicates_in_run"],
            "already_downloaded": dedupe_stats["already_downloaded"],
        },
    }
    write_json(output_path, payload)
    write_json(raw_candidates_path, raw_candidates)
    if args.skip_queue_sync:
        queue_sync = {"processed": 0, "added": 0, "updated": 0, "total": 0}
    else:
        queue_sync = sync_pending_candidate_queue(raw_candidates)
    run_stats = build_run_stats(manifest_items, dedupe_stats, queue_sync)
    duration_seconds = round((datetime.now(timezone.utc) - started_at).total_seconds(), 2)
    update_monitor_status(
        status_path,
        log_path,
        output_path,
        raw_candidates_path,
        registry_path,
        cycle_index,
        args.run_interval_minutes,
        args.download_limit,
        run_stats,
        duration_seconds,
        queue_sync,
    )
    for event in reversed(build_failure_event_messages(manifest_items)):
        update_status(
            status_path,
            event_level=event["level"],
            event_message=event["message"],
        )
    print(
        "douyin collection completed: "
        f"{payload['stats']['matched']} matched / {payload['stats']['downloaded']} downloaded / "
        f"duplicate {dedupe_stats['duplicates_in_run']} / history-skip {dedupe_stats['already_downloaded']} / "
        f"queue +{queue_sync['added']} ~{queue_sync['updated']} -> {args.output}"
    )


def is_douyin_candidate(item: dict[str, Any]) -> bool:
    platform = str(item.get("platform") or "").strip().lower()
    if platform and platform != "douyin":
        return False
    source_url = extract_text(item, ["sourceUrl", "source_url", "url", "link", "permalink", "videoUrl"])
    return is_supported_search_result_url("douyin", source_url) or bool(extract_text(item, ["videoUrl", "video_url", "playUrl", "downloadUrl"]))


if __name__ == "__main__":
    main()