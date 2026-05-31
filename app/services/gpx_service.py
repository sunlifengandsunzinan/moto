"""
GPX 服务层 — 桥接 GPX 生成结果与 moto 项目数据流

提供：
  - 获取 GPX 已处理视频列表
  - 导出途经点到候选点位
  - 处理新视频（通过命令行调用 playwright 脚本）
  - 获取 GPX 文件列表
"""

import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET

PROJECT_ROOT = Path(__file__).resolve().parents[2]
GPX_DIR = PROJECT_ROOT / "data" / "gpx"
DB_PATH = GPX_DIR / "processed_videos.db"
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
GPX_QUEUE_DEFAULT_PATH = PROJECT_ROOT / "data" / "raw" / "gpx_video_queue.txt"
GPX_QUEUE_STATUS_PATH = PROJECT_ROOT / "data" / "raw" / "gpx_queue_status.json"
GPX_QUEUE_LOG_PATH = PROJECT_ROOT / "data" / "raw" / "gpx_queue.log"
GPX_QUEUE_PID_PATH = PROJECT_ROOT / "data" / "raw" / "gpx_queue.pid"
GPX_SEARCH_EXPORT_DIRS = [PROJECT_ROOT / "data" / "raw", Path.home() / "Downloads"]

QUEUE_DONE_PATTERN = re.compile(r"^\[DONE(?:\s+[^\]]+)?\]\s+(?P<url>https?://\S+)\s*$", re.IGNORECASE)
QUEUE_URL_PATTERN = re.compile(r"(https?://[^\s]+)", re.IGNORECASE)
JSON_QUEUE_STATUS_KEY = "gpx_queue_status"
DOUYIN_VIDEO_ID_PATTERN = re.compile(r"(?:/video/|modal_id=)(\d{6,24})")
SEARCH_EXPORT_NAME_PATTERN = re.compile(r"^search_\d{8}_\d{6}\.json$", re.IGNORECASE)


def _connect_db() -> sqlite3.Connection | None:
    if not DB_PATH.exists():
        return None
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def get_processed_videos(limit=50) -> list[dict]:
    """获取已处理的视频记录"""
    try:
        conn = _connect_db()
        if conn is None:
            return []
        cur = conn.execute(
            "SELECT video_id, title, author, processed_at, spots_count, gpx_path, route_slug, route_days, distance_km, amap_href, navigation_mode, qualification_status, qualification_reason, source_channel "
            "FROM processed_videos WHERE COALESCE(record_type, 'video') = 'video' ORDER BY processed_at DESC LIMIT ?", (limit,)
        )
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows
    except Exception:
        return []


def get_processed_route_records(limit=50) -> list[dict]:
    """获取来自 OpenClaw / 自动脚本的合格路线记录。"""
    try:
        conn = _connect_db()
        if conn is None:
            return []
        cur = conn.execute(
            "SELECT video_id, title, author, processed_at, spots_count, gpx_path, route_slug, route_days, distance_km, amap_href, navigation_mode, qualification_status, qualification_reason, source_channel, waypoints_json "
            "FROM processed_videos WHERE record_type = 'route' ORDER BY processed_at DESC LIMIT ?",
            (limit,),
        )
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows
    except Exception:
        return []


def get_gpx_files() -> list[dict]:
    """获取所有 GPX 文件"""
    if not GPX_DIR.exists():
        return []
    files = []
    for f in sorted(GPX_DIR.glob("*.gpx"), key=lambda p: p.stat().st_mtime, reverse=True):
        files.append({
            "name": f.name,
            "path": str(f),
            "size": f.stat().st_size,
            "mtime": f.stat().st_mtime,
        })
    return files


def get_gpx_content(filename: str) -> str | None:
    """读取 GPX 文件内容"""
    fpath = GPX_DIR / filename
    if not fpath.exists() or not fpath.suffix == ".gpx":
        return None
    return fpath.read_text(encoding="utf-8")


def get_gpx_waypoints(filename: str, max_points: int = 16) -> list[dict]:
    """从 GPX 文件提取可用于高德导航的途经点。"""
    content = get_gpx_content(filename)
    if not content:
        return []

    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return []

    namespace = {"gpx": "http://www.topografix.com/GPX/1/1"}
    waypoints: list[dict] = []

    for track_point in root.findall(".//gpx:trkpt", namespace):
        lat = track_point.attrib.get("lat")
        lng = track_point.attrib.get("lon")
        name_node = track_point.find("gpx:name", namespace)
        name = (name_node.text or "").strip() if name_node is not None else ""
        if not name or lat in {None, ""} or lng in {None, ""}:
            continue

        try:
            waypoint = {
                "name": name,
                "lat": float(lat),
                "lng": float(lng),
                "has_coordinates": True,
            }
        except ValueError:
            continue

        if not waypoints or any(existing["name"] != waypoint["name"] or existing["lat"] != waypoint["lat"] or existing["lng"] != waypoint["lng"] for existing in [waypoints[-1]]):
            waypoints.append(waypoint)

        if len(waypoints) >= max_points:
            break

    return waypoints


def run_gpx_process_url(video_url: str) -> dict:
    """通过子进程调用 gpx_generator.py 处理单个视频"""
    try:
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "gpx_generator.py"), "--url", video_url],
            capture_output=True, text=True, timeout=120,
            cwd=str(PROJECT_ROOT)
        )
        return {
            "ok": result.returncode == 0,
            "stdout": result.stdout[-1000:],
            "stderr": result.stderr[-1000:],
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "stdout": "", "stderr": "处理超时（120s）"}
    except Exception as e:
        return {"ok": False, "stdout": "", "stderr": str(e)}


def _normalize_video_urls(urls: list[str] | None = None, raw_text: str = "") -> list[str]:
    candidates = list(urls or [])
    if raw_text:
        candidates.extend(re.split(r"[\n\r,，;；\t ]+", raw_text))

    normalized: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        url = str(item or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        normalized.append(url)
    return normalized


def run_gpx_process_urls(video_urls: list[str] | None = None, raw_text: str = "") -> dict:
    """批量处理多个视频链接，逐条复用现有单视频处理链路。"""
    normalized_urls = _normalize_video_urls(video_urls, raw_text)
    if not normalized_urls:
        return {
            "ok": False,
            "mode": "batch",
            "processed": 0,
            "success_count": 0,
            "failure_count": 0,
            "results": [],
            "error": "缺少可处理的 url",
        }

    results: list[dict] = []
    success_count = 0
    failure_count = 0
    for url in normalized_urls:
        item_result = run_gpx_process_url(url)
        item_payload = {
            "url": url,
            "ok": bool(item_result.get("ok")),
            "stdout": item_result.get("stdout", ""),
            "stderr": item_result.get("stderr", ""),
        }
        results.append(item_payload)
        if item_payload["ok"]:
            success_count += 1
        else:
            failure_count += 1

    return {
        "ok": failure_count == 0,
        "mode": "batch",
        "processed": len(normalized_urls),
        "success_count": success_count,
        "failure_count": failure_count,
        "results": results,
    }


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def _display_dynamic_path(value: Any, fallback: Path) -> str:
    text = str(value or "").strip()
    if not text:
        return _display_path(fallback)
    return _display_path(Path(text))


def _parse_time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _display_time(value: Any) -> str:
    parsed = _parse_time(value)
    if parsed is None:
        return "未记录"
    return parsed.astimezone().strftime("%Y-%m-%d %H:%M:%S")


def _display_duration(seconds: Any) -> str:
    try:
        value = float(seconds)
    except (TypeError, ValueError):
        return "未记录"
    return f"{value:.2f} 秒"


def _extract_queue_url(text: str) -> str:
    match = QUEUE_URL_PATTERN.search(str(text or "").strip())
    return match.group(1).rstrip("),。；;]") if match else ""


def _extract_video_id_from_url(url: str) -> str:
    match = DOUYIN_VIDEO_ID_PATTERN.search(str(url or ""))
    return match.group(1) if match else ""


def _normalize_source_title(value: Any) -> str:
    return str(value or "").strip()


def _normalize_source_author(value: Any) -> str:
    return str(value or "").strip().lstrip("@")


def update_processed_video_source_metadata(video_id: str, *, title: str = "", author: str = "") -> None:
    normalized_video_id = str(video_id or "").strip()
    if not normalized_video_id:
        return
    normalized_title = _normalize_source_title(title)
    normalized_author = _normalize_source_author(author)
    if not normalized_title and not normalized_author:
        return

    conn = _connect_db()
    if conn is None:
        return
    try:
        assignments: list[str] = []
        params: list[str] = []
        if normalized_title:
            assignments.append("title = ?")
            params.append(normalized_title)
        if normalized_author:
            assignments.append("author = ?")
            params.append(normalized_author)
        if not assignments:
            return
        params.append(normalized_video_id)
        conn.execute(
            f"UPDATE processed_videos SET {', '.join(assignments)} WHERE video_id = ? AND COALESCE(record_type, 'video') = 'video'",
            tuple(params),
        )
        conn.commit()
    finally:
        conn.close()


def _parse_queue_line(line: str) -> dict[str, str]:
    raw = line.rstrip("\n")
    stripped = raw.strip()
    if not stripped:
        return {"kind": "blank", "line": raw, "url": ""}
    if stripped.startswith("#"):
        return {"kind": "comment", "line": raw, "url": ""}

    done_match = QUEUE_DONE_PATTERN.match(stripped)
    if done_match:
        return {"kind": "done", "line": raw, "url": done_match.group("url")}

    url = _extract_queue_url(stripped)
    if url:
        return {"kind": "pending", "line": raw, "url": url}
    return {"kind": "invalid", "line": raw, "url": ""}


def _format_done_line(url: str, finished_at: str) -> str:
    return f"[DONE {finished_at}] {url}"


def _resolve_queue_file(queue_file: str | None = None, *, require_exists: bool = True) -> Path:
    raw_path = str(queue_file or "").strip()
    candidate = _resolve_default_queue_candidate(raw_path)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    resolved = candidate.resolve()
    project_root = PROJECT_ROOT.resolve()
    if not _is_allowed_queue_path(resolved):
        raise ValueError("队列文件必须位于当前项目目录内，或位于允许自动读取的搜索导出目录（如 Downloads）。")
    if require_exists:
        if not resolved.exists():
            raise FileNotFoundError(f"队列文件不存在: {_display_path(resolved)}")
        if not resolved.is_file():
            raise ValueError("队列路径不是文件。")
    return resolved


def _resolve_default_queue_candidate(raw_path: str) -> Path:
    if raw_path:
        explicit = Path(raw_path).expanduser()
        if explicit.name and SEARCH_EXPORT_NAME_PATTERN.match(explicit.name):
            discovered = _find_latest_search_export(explicit.name)
            if discovered is not None:
                return discovered
        return explicit

    discovered = _find_latest_search_export()
    if discovered is not None:
        return discovered
    return GPX_QUEUE_DEFAULT_PATH


def _find_latest_search_export(preferred_name: str | None = None) -> Path | None:
    candidates: list[Path] = []
    for search_dir in GPX_SEARCH_EXPORT_DIRS:
        if not search_dir.exists() or not search_dir.is_dir():
            continue
        if preferred_name:
            preferred_path = search_dir / preferred_name
            if preferred_path.exists() and preferred_path.is_file():
                candidates.append(preferred_path)
            continue
        candidates.extend(
            path for path in search_dir.glob("search_*.json")
            if path.is_file() and SEARCH_EXPORT_NAME_PATTERN.match(path.name)
        )
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _is_allowed_queue_path(path: Path) -> bool:
    resolved = path.resolve()
    project_root = PROJECT_ROOT.resolve()
    if resolved == project_root or project_root in resolved.parents:
        return True
    for search_dir in GPX_SEARCH_EXPORT_DIRS:
        resolved_search_dir = search_dir.resolve()
        if resolved == resolved_search_dir or resolved_search_dir in resolved.parents:
            return True
    return False


def _read_queue_lines(queue_path: Path) -> list[str]:
    if not queue_path.exists():
        return []
    return queue_path.read_text(encoding="utf-8").splitlines()


def _write_queue_lines(queue_path: Path, lines: list[str]) -> None:
    queue_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _default_queue_summary() -> dict[str, int | str]:
    return {
        "format": "text",
        "total_lines": 0,
        "total_urls": 0,
        "pending": 0,
        "done": 0,
        "invalid": 0,
        "comments": 0,
        "blanks": 0,
        "duplicate_entries": 0,
    }


def _read_queue_json_payload(queue_path: Path) -> dict[str, Any] | None:
    if queue_path.suffix.lower() != ".json" or not queue_path.exists():
        return None
    try:
        payload = json.loads(queue_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    results = payload.get("results")
    if not isinstance(results, dict):
        return None
    return payload


def _extract_json_queue_entries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    results = payload.get("results")
    if not isinstance(results, dict):
        return entries

    for keyword, items in results.items():
        if not isinstance(items, list):
            continue
        for item_index, item in enumerate(items):
            if not isinstance(item, dict):
                entries.append({
                    "kind": "invalid",
                    "keyword": str(keyword),
                    "item_index": item_index,
                    "url": "",
                    "item": None,
                })
                continue
            url = _extract_queue_url(str(item.get("url") or ""))
            status = item.get(JSON_QUEUE_STATUS_KEY)
            is_done = isinstance(status, dict) and str(status.get("state") or "") == "done"
            entries.append(
                {
                    "kind": "done" if is_done else ("pending" if url else "invalid"),
                    "keyword": str(keyword),
                    "item_index": item_index,
                    "url": url,
                    "item": item,
                }
            )
    return entries


def _write_queue_json_payload(queue_path: Path, payload: dict[str, Any]) -> None:
    queue_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _summarize_json_queue_payload(payload: dict[str, Any]) -> dict[str, int | str]:
    summary = _default_queue_summary()
    summary["format"] = "json-search-results"

    entries = _extract_json_queue_entries(payload)
    summary["total_lines"] = len(entries)
    unique_all_urls: set[str] = set()
    unique_done_urls: set[str] = set()
    unique_pending_urls: set[str] = set()

    for entry in entries:
        kind = str(entry.get("kind") or "invalid")
        url = str(entry.get("url") or "")
        if kind == "invalid":
            summary["invalid"] += 1
            continue
        if not url:
            summary["invalid"] += 1
            continue
        unique_all_urls.add(url)
        if kind == "done":
            unique_done_urls.add(url)
        else:
            unique_pending_urls.add(url)

    unique_pending_urls -= unique_done_urls
    summary["total_urls"] = len(unique_all_urls)
    summary["done"] = len(unique_done_urls)
    summary["pending"] = len(unique_pending_urls)
    summary["duplicate_entries"] = max(len(entries) - len(unique_all_urls) - int(summary["invalid"]), 0)
    return summary


def _summarize_queue_file(queue_path: Path) -> dict[str, int | str]:
    json_payload = _read_queue_json_payload(queue_path)
    if json_payload is not None:
        return _summarize_json_queue_payload(json_payload)
    return _summarize_queue_lines(_read_queue_lines(queue_path))


def _mark_json_queue_url(payload: dict[str, Any], url: str, *, state: str, finished_at: str, detail: str = "") -> None:
    for entry in _extract_json_queue_entries(payload):
        if str(entry.get("url") or "") != url:
            continue
        item = entry.get("item")
        if not isinstance(item, dict):
            continue
        item[JSON_QUEUE_STATUS_KEY] = {
            "state": state,
            "updated_at": finished_at,
            "detail": detail,
        }


def _summarize_queue_lines(lines: list[str]) -> dict[str, int]:
    summary = _default_queue_summary()
    summary["total_lines"] = len(lines)
    for line in lines:
        parsed = _parse_queue_line(line)
        kind = parsed["kind"]
        if kind == "pending":
            summary["total_urls"] += 1
            summary["pending"] += 1
        elif kind == "done":
            summary["total_urls"] += 1
            summary["done"] += 1
        elif kind == "invalid":
            summary["invalid"] += 1
        elif kind == "comment":
            summary["comments"] += 1
        else:
            summary["blanks"] += 1
    return summary


def _read_queue_status_payload() -> dict[str, Any]:
    if not GPX_QUEUE_STATUS_PATH.exists():
        return {}
    try:
        payload = json.loads(GPX_QUEUE_STATUS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"state": "error", "last_error": "队列状态文件损坏，无法解析。"}
    return payload if isinstance(payload, dict) else {}


def _read_pid(value: Any) -> int | None:
    if value not in {None, ""}:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
    if not GPX_QUEUE_PID_PATH.exists():
        return None
    try:
        return int(GPX_QUEUE_PID_PATH.read_text(encoding="utf-8").strip())
    except (TypeError, ValueError):
        return None


def _is_pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _append_status_event(payload: dict[str, Any], message: str, level: str = "info") -> None:
    events = payload.get("events")
    normalized_events = events if isinstance(events, list) else []
    normalized_events.append(
        {
            "at": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "message": message,
        }
    )
    payload["events"] = normalized_events[-20:]


def _append_recent_queue_result(payload: dict[str, Any], result: dict[str, Any]) -> None:
    results = payload.get("recent_results")
    normalized_results = results if isinstance(results, list) else []
    normalized_results.append(result)
    payload["recent_results"] = normalized_results[-20:]


def _update_queue_status(event_message: str = "", event_level: str = "info", **updates: Any) -> dict[str, Any]:
    payload = _read_queue_status_payload()
    payload.update({key: value for key, value in updates.items() if value is not None})
    payload["status_path"] = str(GPX_QUEUE_STATUS_PATH)
    payload["log_path"] = str(GPX_QUEUE_LOG_PATH)
    payload["pid_path"] = str(GPX_QUEUE_PID_PATH)
    payload["last_heartbeat"] = datetime.now(timezone.utc).isoformat()
    if event_message:
        _append_status_event(payload, event_message, event_level)
    GPX_QUEUE_STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    GPX_QUEUE_STATUS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def get_gpx_queue_process_info(status: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = status if isinstance(status, dict) else _read_queue_status_payload()
    pid = _read_pid(payload.get("pid"))
    is_running = _is_pid_alive(pid) if pid else False
    if pid and not is_running and GPX_QUEUE_PID_PATH.exists():
        GPX_QUEUE_PID_PATH.unlink()
    return {
        "pid": pid,
        "is_running": is_running,
        "can_start": not is_running,
        "can_stop": is_running,
        "log_file": _display_path(GPX_QUEUE_LOG_PATH),
    }


def _build_queue_health(status: dict[str, Any]) -> dict[str, str]:
    state = str(status.get("state") or "idle")
    heartbeat = _parse_time(status.get("last_heartbeat"))
    finished_at = _parse_time(status.get("last_finished_at") or status.get("last_success_at"))
    now = datetime.now(timezone.utc)

    if state in {"running", "preparing", "processing"}:
        if heartbeat and (now - heartbeat).total_seconds() <= 180:
            return {"kind": "ok", "label": "处理中"}
        return {"kind": "error", "label": "进程失联"}
    if state == "completed_with_errors":
        return {"kind": "warning", "label": "已完成，有失败项"}
    if state == "success":
        if finished_at and (now - finished_at).total_seconds() <= 24 * 3600:
            return {"kind": "ok", "label": "最近已完成"}
        return {"kind": "warning", "label": "已完成，长时间未刷新"}
    if state == "error":
        return {"kind": "error", "label": "任务异常"}
    if state == "stopped":
        return {"kind": "warning", "label": "已停止"}
    return {"kind": "warning", "label": "未启动"}


def _queue_state_label(state: Any) -> str:
    mapping = {
        "idle": "未启动",
        "preparing": "准备中",
        "running": "运行中",
        "processing": "处理中",
        "success": "已完成",
        "completed_with_errors": "已完成，有失败项",
        "error": "异常",
        "stopped": "已停止",
    }
    return mapping.get(str(state or "idle"), str(state or "未启动"))


def _queue_stage_label(stage: Any) -> str:
    mapping = {
        "idle": "空闲",
        "preparing": "读取队列文件",
        "scanning": "扫描待处理链接",
        "processing": "处理当前链接",
        "finished": "处理完成",
        "stopped": "人工停止",
    }
    return mapping.get(str(stage or "idle"), str(stage or "空闲"))


def _normalize_monitor_items(items: Any) -> list[dict[str, str]]:
    if not isinstance(items, list):
        return []
    normalized: list[dict[str, str]] = []
    for item in items[-20:]:
        if not isinstance(item, dict):
            continue
        normalized.append(
            {
                "at": _display_time(item.get("at")),
                "level": str(item.get("level") or "info"),
                "message": str(item.get("message") or ""),
                "url": str(item.get("url") or ""),
                "line": str(item.get("line") or ""),
                "detail": str(item.get("detail") or ""),
            }
        )
    return list(reversed(normalized))


def get_gpx_queue_monitor_context() -> dict[str, Any]:
    status = _read_queue_status_payload()
    process_info = get_gpx_queue_process_info(status)
    health = _build_queue_health(status)

    queue_file_text = str(status.get("queue_file") or "").strip()
    queue_path = Path(queue_file_text) if queue_file_text else _resolve_default_queue_candidate("")
    try:
        queue_path = _resolve_queue_file(str(queue_path), require_exists=False)
    except ValueError:
        queue_path = _resolve_default_queue_candidate("")

    queue_summary = _summarize_queue_file(queue_path) if queue_path.exists() else _default_queue_summary()

    return {
        "page": {
            "title": "GPX 队列监控",
            "description": "监控按文件排队的视频提取任务，查看当前进程、当前链接、成功失败统计，以及队列文件里的已完成标记。",
        },
        "monitor": {
            "health": health,
            "state_label": _queue_state_label(status.get("state")),
            "current_stage_label": _queue_stage_label(status.get("current_stage")),
            "queue_file": _display_dynamic_path(status.get("queue_file"), queue_path),
            "status_file": _display_dynamic_path(status.get("status_path"), GPX_QUEUE_STATUS_PATH),
            "log_file": _display_dynamic_path(status.get("log_path"), GPX_QUEUE_LOG_PATH),
            "current_url": str(status.get("current_url") or "当前无链接处理"),
            "current_task": str(status.get("current_task") or "当前无处理任务"),
            "last_started_at": _display_time(status.get("last_started_at")),
            "last_finished_at": _display_time(status.get("last_finished_at")),
            "last_success_at": _display_time(status.get("last_success_at")),
            "last_error_at": _display_time(status.get("last_error_at")),
            "last_error": str(status.get("last_error") or "无"),
            "process": process_info,
            "metrics": [
                {"label": "脚本状态", "value": _queue_state_label(status.get("state"))},
                {"label": "健康度", "value": health["label"]},
                {"label": "进程 PID", "value": str(process_info.get("pid") or "未运行")},
                {"label": "当前阶段", "value": _queue_stage_label(status.get("current_stage"))},
                {"label": "当前进度", "value": f"{int(status.get('processed_count') or 0)} / {int(status.get('total_urls') or queue_summary['total_urls'])}"},
                {"label": "成功", "value": str(status.get("success_count") or 0)},
                {"label": "失败", "value": str(status.get("failure_count") or 0)},
                {"label": "文件内已标记完成", "value": str(queue_summary["done"])},
                {"label": "文件内待处理", "value": str(queue_summary["pending"])},
                {"label": "无效行", "value": str(queue_summary["invalid"])},
                {"label": "重复结果", "value": str(queue_summary["duplicate_entries"])},
                {"label": "最近开始", "value": _display_time(status.get("last_started_at"))},
                {"label": "最近完成", "value": _display_time(status.get("last_finished_at"))},
            ],
            "summary": [
                {"label": "队列文件", "value": _display_dynamic_path(status.get("queue_file"), queue_path)},
                {"label": "日志文件", "value": _display_dynamic_path(status.get("log_path"), GPX_QUEUE_LOG_PATH)},
                {"label": "状态文件", "value": _display_dynamic_path(status.get("status_path"), GPX_QUEUE_STATUS_PATH)},
                {"label": "当前任务", "value": str(status.get("current_task") or "当前无处理任务")},
                {"label": "当前链接", "value": str(status.get("current_url") or "当前无链接处理")},
                {"label": "最近耗时", "value": _display_duration(status.get("last_duration_seconds"))},
                {"label": "队列总链接", "value": str(queue_summary["total_urls"])},
                {"label": "文件格式", "value": str(queue_summary["format"])},
                {"label": "队列注释/空行", "value": f"{queue_summary['comments']} / {queue_summary['blanks']}"},
                {"label": "最近错误", "value": str(status.get("last_error") or "无")},
            ],
            "events": _normalize_monitor_items(status.get("events")),
            "recent_results": _normalize_monitor_items(status.get("recent_results")),
        },
    }


def get_gpx_queue_monitor_api_payload() -> dict[str, Any]:
    context = get_gpx_queue_monitor_context()
    return {"page": context["page"], "monitor": context["monitor"]}


def start_gpx_queue_task(queue_file: str | None = None) -> dict[str, Any]:
    process_info = get_gpx_queue_process_info()
    if process_info["is_running"]:
        raise RuntimeError("GPX 队列任务已经在运行。")

    resolved_queue = _resolve_queue_file(queue_file)
    queue_summary = _summarize_queue_file(resolved_queue)
    python_executable = PROJECT_ROOT / ".venv" / "bin" / "python"
    command = [
        str(python_executable if python_executable.exists() else Path(sys.executable)),
        str(SCRIPTS_DIR / "run_gpx_queue_task.py"),
        "--file",
        str(resolved_queue),
    ]

    GPX_QUEUE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with GPX_QUEUE_LOG_PATH.open("a", encoding="utf-8") as log_file:
        process = subprocess.Popen(  # noqa: S603
            command,
            cwd=PROJECT_ROOT,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

    GPX_QUEUE_PID_PATH.write_text(str(process.pid), encoding="utf-8")
    _update_queue_status(
        state="preparing",
        current_stage="preparing",
        pid=process.pid,
        queue_file=str(resolved_queue),
        current_task="正在启动文件队列处理任务",
        current_url="",
        total_urls=queue_summary["total_urls"],
        processed_count=0,
        success_count=0,
        failure_count=0,
        skipped_completed_count=queue_summary["done"],
        invalid_line_count=queue_summary["invalid"],
        last_started_at=datetime.now(timezone.utc).isoformat(),
        last_finished_at="",
        last_error="",
        event_message=f"已启动 GPX 队列任务，PID={process.pid}，队列文件={_display_path(resolved_queue)}。",
    )
    return {"pid": process.pid, "queue_file": _display_path(resolved_queue)}


def stop_gpx_queue_task() -> dict[str, Any]:
    process_info = get_gpx_queue_process_info()
    if not process_info["pid"]:
        raise RuntimeError("没有找到正在运行的 GPX 队列任务。")

    pid = int(process_info["pid"])
    if process_info["is_running"]:
        os.kill(pid, 15)
        deadline = time.time() + 3
        while time.time() < deadline:
            if not _is_pid_alive(pid):
                break
            time.sleep(0.1)

    if GPX_QUEUE_PID_PATH.exists():
        GPX_QUEUE_PID_PATH.unlink()

    _update_queue_status(
        state="stopped",
        current_stage="stopped",
        pid=None,
        current_task="任务已停止",
        current_url="",
        last_finished_at=datetime.now(timezone.utc).isoformat(),
        event_message=f"已停止 GPX 队列任务，PID={pid}。",
        event_level="warning",
    )
    return {"pid": pid}


def run_gpx_queue_file(queue_file: str | None = None) -> dict[str, Any]:
    resolved_queue = _resolve_queue_file(queue_file)
    json_payload = _read_queue_json_payload(resolved_queue)
    if json_payload is not None:
        return _run_gpx_queue_json_file(resolved_queue, json_payload)

    lines = _read_queue_lines(resolved_queue)
    queue_summary = _summarize_queue_lines(lines)

    processed_count = 0
    success_count = 0
    failure_count = 0
    skipped_completed_count = queue_summary["done"]
    invalid_line_count = queue_summary["invalid"]
    started_at = datetime.now(timezone.utc)

    _update_queue_status(
        state="running",
        current_stage="scanning",
        pid=os.getpid(),
        queue_file=str(resolved_queue),
        current_task="正在扫描队列文件",
        current_url="",
        total_urls=queue_summary["total_urls"],
        processed_count=processed_count,
        success_count=success_count,
        failure_count=failure_count,
        skipped_completed_count=skipped_completed_count,
        invalid_line_count=invalid_line_count,
        last_started_at=started_at.isoformat(),
        event_message=f"开始读取队列文件：{_display_path(resolved_queue)}。",
    )

    status_payload = _read_queue_status_payload()
    for line_index, line in enumerate(lines, start=1):
        parsed = _parse_queue_line(line)
        if parsed["kind"] == "done":
            continue
        if parsed["kind"] in {"blank", "comment"}:
            continue
        if parsed["kind"] == "invalid":
            invalid_line_count += 1
            status_payload = _update_queue_status(
                state="running",
                current_stage="scanning",
                current_task=f"第 {line_index} 行不是可识别链接，已跳过",
                invalid_line_count=invalid_line_count,
                event_message=f"第 {line_index} 行无法识别为链接，已跳过。",
                event_level="warning",
            )
            continue

        url = parsed["url"]
        status_payload = _update_queue_status(
            state="running",
            current_stage="processing",
            current_task=f"正在处理第 {processed_count + 1} / {queue_summary['total_urls']} 条链接",
            current_url=url,
            current_line=line_index,
            processed_count=processed_count,
            success_count=success_count,
            failure_count=failure_count,
        )

        item_result = run_gpx_process_url(url)
        processed_count += 1
        finished_at = datetime.now(timezone.utc).isoformat()

        if item_result.get("ok"):
            success_count += 1
            lines[line_index - 1] = _format_done_line(url, finished_at)
            _write_queue_lines(resolved_queue, lines)
            _append_recent_queue_result(
                status_payload,
                {
                    "at": finished_at,
                    "level": "success",
                    "line": line_index,
                    "url": url,
                    "message": "处理成功，已在队列文件中标记完成。",
                    "detail": str(item_result.get("stdout") or ""),
                },
            )
            status_payload = _update_queue_status(
                state="running",
                current_stage="processing",
                current_task=f"已完成第 {processed_count} 条链接",
                current_url=url,
                processed_count=processed_count,
                success_count=success_count,
                failure_count=failure_count,
                last_success_at=finished_at,
                recent_results=status_payload.get("recent_results"),
                event_message=f"第 {line_index} 行处理成功，已标记完成。",
            )
        else:
            failure_count += 1
            _append_recent_queue_result(
                status_payload,
                {
                    "at": finished_at,
                    "level": "error",
                    "line": line_index,
                    "url": url,
                    "message": "处理失败，保留原始行以便下次重试。",
                    "detail": str(item_result.get("stderr") or item_result.get("stdout") or "未知错误"),
                },
            )
            status_payload = _update_queue_status(
                state="running",
                current_stage="processing",
                current_task=f"第 {line_index} 行处理失败",
                current_url=url,
                processed_count=processed_count,
                success_count=success_count,
                failure_count=failure_count,
                last_error_at=finished_at,
                last_error=str(item_result.get("stderr") or item_result.get("stdout") or "未知错误"),
                recent_results=status_payload.get("recent_results"),
                event_message=f"第 {line_index} 行处理失败：{item_result.get('stderr') or item_result.get('stdout') or '未知错误'}",
                event_level="error",
            )

    final_summary = _summarize_queue_lines(_read_queue_lines(resolved_queue))
    finished_at = datetime.now(timezone.utc)
    last_state = "success" if failure_count == 0 else "completed_with_errors"
    if GPX_QUEUE_PID_PATH.exists():
        GPX_QUEUE_PID_PATH.unlink()
    _update_queue_status(
        state=last_state,
        current_stage="finished",
        pid=None,
        current_task="当前无处理任务",
        current_url="",
        total_urls=final_summary["total_urls"],
        processed_count=processed_count,
        success_count=success_count,
        failure_count=failure_count,
        skipped_completed_count=final_summary["done"],
        invalid_line_count=final_summary["invalid"],
        last_finished_at=finished_at.isoformat(),
        last_duration_seconds=(finished_at - started_at).total_seconds(),
        event_message=f"队列处理完成：成功 {success_count} 条，失败 {failure_count} 条，文件内已标记完成 {final_summary['done']} 条。",
        event_level="warning" if failure_count else "info",
    )
    return {
        "ok": failure_count == 0,
        "queue_file": _display_path(resolved_queue),
        "processed": processed_count,
        "success_count": success_count,
        "failure_count": failure_count,
        "done_count": final_summary["done"],
        "pending_count": final_summary["pending"],
    }


def _run_gpx_queue_json_file(resolved_queue: Path, payload: dict[str, Any]) -> dict[str, Any]:
    queue_summary = _summarize_json_queue_payload(payload)

    processed_count = 0
    success_count = 0
    failure_count = 0
    skipped_completed_count = int(queue_summary["done"])
    invalid_line_count = int(queue_summary["invalid"])
    started_at = datetime.now(timezone.utc)
    attempted_urls: set[str] = set()

    _update_queue_status(
        state="running",
        current_stage="scanning",
        pid=os.getpid(),
        queue_file=str(resolved_queue),
        current_task="正在扫描 JSON 队列文件",
        current_url="",
        total_urls=queue_summary["total_urls"],
        processed_count=processed_count,
        success_count=success_count,
        failure_count=failure_count,
        skipped_completed_count=skipped_completed_count,
        invalid_line_count=invalid_line_count,
        last_started_at=started_at.isoformat(),
        event_message=f"开始读取 JSON 队列文件：{_display_path(resolved_queue)}。",
    )

    status_payload = _read_queue_status_payload()
    entries = _extract_json_queue_entries(payload)
    for entry_index, entry in enumerate(entries, start=1):
        kind = str(entry.get("kind") or "invalid")
        url = str(entry.get("url") or "")
        keyword = str(entry.get("keyword") or "")
        item = entry.get("item") if isinstance(entry.get("item"), dict) else {}
        if kind == "done":
            continue
        if kind == "invalid":
            invalid_line_count += 1
            status_payload = _update_queue_status(
                state="running",
                current_stage="scanning",
                current_task=f"{keyword} 下第 {entry_index} 条结果没有有效链接，已跳过",
                invalid_line_count=invalid_line_count,
                event_message=f"关键词 {keyword} 的第 {entry_index} 条结果没有有效链接，已跳过。",
                event_level="warning",
            )
            continue
        if url in attempted_urls:
            continue

        attempted_urls.add(url)
        status_payload = _update_queue_status(
            state="running",
            current_stage="processing",
            current_task=f"正在处理第 {processed_count + 1} / {queue_summary['total_urls']} 条唯一链接",
            current_url=url,
            current_line=entry_index,
            processed_count=processed_count,
            success_count=success_count,
            failure_count=failure_count,
        )

        item_result = run_gpx_process_url(url)
        processed_count += 1
        finished_at = datetime.now(timezone.utc).isoformat()
        detail = str(item_result.get("stderr") or item_result.get("stdout") or "")

        if item_result.get("ok"):
            success_count += 1
            update_processed_video_source_metadata(
                str(item.get("aweme_id") or _extract_video_id_from_url(url)),
                title=str(item.get("title") or ""),
                author=str(item.get("author") or ""),
            )
            _mark_json_queue_url(payload, url, state="done", finished_at=finished_at, detail=detail)
            _write_queue_json_payload(resolved_queue, payload)
            _append_recent_queue_result(
                status_payload,
                {
                    "at": finished_at,
                    "level": "success",
                    "line": entry_index,
                    "url": url,
                    "message": "处理成功，已在 JSON 队列文件中标记完成。",
                    "detail": detail,
                },
            )
            status_payload = _update_queue_status(
                state="running",
                current_stage="processing",
                current_task=f"已完成第 {processed_count} 条唯一链接",
                current_url=url,
                processed_count=processed_count,
                success_count=success_count,
                failure_count=failure_count,
                last_success_at=finished_at,
                recent_results=status_payload.get("recent_results"),
                event_message=f"链接处理成功，已回写到 JSON 文件：{url}",
            )
        else:
            failure_count += 1
            _mark_json_queue_url(payload, url, state="failed", finished_at=finished_at, detail=detail)
            _write_queue_json_payload(resolved_queue, payload)
            _append_recent_queue_result(
                status_payload,
                {
                    "at": finished_at,
                    "level": "error",
                    "line": entry_index,
                    "url": url,
                    "message": "处理失败，JSON 文件中保留 failed 状态以便下次重试。",
                    "detail": detail or "未知错误",
                },
            )
            status_payload = _update_queue_status(
                state="running",
                current_stage="processing",
                current_task=f"链接处理失败：{url}",
                current_url=url,
                processed_count=processed_count,
                success_count=success_count,
                failure_count=failure_count,
                last_error_at=finished_at,
                last_error=detail or "未知错误",
                recent_results=status_payload.get("recent_results"),
                event_message=f"JSON 队列链接处理失败：{url} · {detail or '未知错误'}",
                event_level="error",
            )

    final_summary = _summarize_queue_file(resolved_queue)
    finished_at = datetime.now(timezone.utc)
    last_state = "success" if failure_count == 0 else "completed_with_errors"
    if GPX_QUEUE_PID_PATH.exists():
        GPX_QUEUE_PID_PATH.unlink()
    _update_queue_status(
        state=last_state,
        current_stage="finished",
        pid=None,
        current_task="当前无处理任务",
        current_url="",
        total_urls=final_summary["total_urls"],
        processed_count=processed_count,
        success_count=success_count,
        failure_count=failure_count,
        skipped_completed_count=final_summary["done"],
        invalid_line_count=final_summary["invalid"],
        last_finished_at=finished_at.isoformat(),
        last_duration_seconds=(finished_at - started_at).total_seconds(),
        event_message=f"JSON 队列处理完成：成功 {success_count} 条，失败 {failure_count} 条，已标记完成 {final_summary['done']} 条。",
        event_level="warning" if failure_count else "info",
    )
    return {
        "ok": failure_count == 0,
        "queue_file": _display_path(resolved_queue),
        "processed": processed_count,
        "success_count": success_count,
        "failure_count": failure_count,
        "done_count": final_summary["done"],
        "pending_count": final_summary["pending"],
    }


def sync_openclaw_route_records() -> dict:
    """将 OpenClaw 自动搜索到的合格路线导入 GPX 数据库。"""
    try:
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "gpx_generator.py"), "--import-openclaw-routes"],
            capture_output=True, text=True, timeout=60,
            cwd=str(PROJECT_ROOT)
        )
        payload: dict[str, object]
        try:
            payload = json.loads(result.stdout.strip() or "{}")
        except json.JSONDecodeError:
            payload = {"ok": result.returncode == 0, "stdout": result.stdout[-1000:], "stderr": result.stderr[-1000:]}
        if "ok" not in payload:
            payload["ok"] = result.returncode == 0
        if result.stderr.strip():
            payload["stderr"] = result.stderr[-1000:]
        return payload
    except subprocess.TimeoutExpired:
        return {"ok": False, "stderr": "OpenClaw 路线导入超时（60s）"}
    except Exception as e:
        return {"ok": False, "stderr": str(e)}


def export_gpx_candidates() -> dict:
    """导出途经点到 candidate_spots.json"""
    try:
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "gpx_generator.py"), "--export-spots"],
            capture_output=True, text=True, timeout=30,
            cwd=str(PROJECT_ROOT)
        )
        return {"ok": result.returncode == 0, "output": result.stdout[-500:], "error": result.stderr[-500:]}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def get_gpx_stats() -> dict:
    """统计数据"""
    processed = get_processed_videos(999)
    route_records = get_processed_route_records(999)
    gpx_files = get_gpx_files()
    return {
        "total_videos": len(processed),
        "total_route_records": len(route_records),
        "qualified_route_records": sum(1 for item in route_records if item.get("qualification_status") == "qualified"),
        "total_gpx_files": len(gpx_files),
        "total_spots": sum(r.get("spots_count", 0) for r in processed) + sum(r.get("spots_count", 0) for r in route_records),
    }
