from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[2]
COLLECTOR_PROFILES: dict[str, dict[str, Any]] = {
    "local-social": {
        "key": "local-social",
        "label": "本地采集",
        "title": "本地采集监控",
        "description": "查看本地采集脚本是否正在运行、最近一次是否成功，以及当前输出数据是否正常刷新。",
        "status_path": PROJECT_ROOT / "data" / "raw" / "local_collection_status.json",
        "output_path": PROJECT_ROOT / "data" / "raw" / "openclaw_export.json",
        "script_path": PROJECT_ROOT / "scripts" / "run_local_social_collection.py",
        "log_path": PROJECT_ROOT / "data" / "raw" / "local_collection.log",
        "pid_path": PROJECT_ROOT / "data" / "raw" / "local_collection.pid",
        "start_args": ["--continuous"],
        "start_button_label": "启动采集",
        "stop_button_label": "停止采集",
        "start_hint": "点击启动后会持续采集，直到你手动点“停止采集”。",
    },
    "xiaohongshu-route": {
        "key": "xiaohongshu-route",
        "label": "小红书路线",
        "title": "小红书路线采集监控",
        "description": "查看小红书摩旅路线采集脚本是否正在运行、最近一次是否成功，以及当前路线清单是否正常刷新。",
        "status_path": PROJECT_ROOT / "data" / "raw" / "xiaohongshu_route_status.json",
        "output_path": PROJECT_ROOT / "data" / "raw" / "xiaohongshu_route_manifest.json",
        "script_path": PROJECT_ROOT / "scripts" / "collect_xiaohongshu_routes.py",
        "log_path": PROJECT_ROOT / "data" / "raw" / "xiaohongshu_route_collection.log",
        "pid_path": PROJECT_ROOT / "data" / "raw" / "xiaohongshu_route_collection.pid",
        "start_args": [],
        "start_button_label": "启动路线采集",
        "stop_button_label": "停止路线采集",
        "start_hint": "点击启动后会执行一轮小红书路线采集；如需再次运行，可以重新点击启动。",
    },
}


def get_collection_monitor_context(collector_key: str = "local-social") -> dict[str, Any]:
    profile = _resolve_profile(collector_key)
    status = _read_status_payload(profile)
    output_payload = _read_output_payload(profile)
    process_info = get_collection_process_info(status, collector_key)
    health = _build_health(status)
    task_index = int(status.get("current_task_index") or status.get("tasks_completed") or 0)
    task_total = int(status.get("tasks_total") or 0)
    return {
        "page": {
            "title": str(profile["title"]),
            "description": str(profile["description"]),
        },
        "monitor": {
            "collector_key": str(profile["key"]),
            "collector_label": str(profile["label"]),
            "collector_options": [
                {"key": item["key"], "label": item["label"], "is_active": item["key"] == profile["key"]}
                for item in COLLECTOR_PROFILES.values()
            ],
            "health": health,
            "state_label": _state_label(status.get("state")),
            "run_mode_label": _run_mode_label(status.get("run_mode")),
            "current_stage_label": _stage_label(status.get("current_stage")),
            "pipeline_status_label": _pipeline_status_label(status.get("pipeline_status")),
            "script_command": str(status.get("script_command") or _default_script_command(profile)),
            "status_file": _display_dynamic_path(status.get("status_path"), Path(profile["status_path"])),
            "output_file": _display_dynamic_path(status.get("output_path"), Path(profile["output_path"])),
            "log_file": _display_dynamic_path(status.get("log_path"), Path(profile["log_path"])),
            "last_heartbeat": _display_time(status.get("last_heartbeat")),
            "last_success_at": _display_time(status.get("last_success_at")),
            "last_error_at": _display_time(status.get("last_error_at")),
            "last_pipeline_at": _display_time(status.get("last_pipeline_at")),
            "last_error": str(status.get("last_error") or "无"),
            "current_task": str(status.get("current_task") or "当前无采集任务"),
            "pipeline_summary": str(status.get("pipeline_summary") or "未记录"),
            "start_button_label": str(profile["start_button_label"]),
            "stop_button_label": str(profile["stop_button_label"]),
            "start_hint": str(profile["start_hint"]),
            "pending_queue_delta": {
                "processed": str(status.get("pending_candidates_processed", 0)),
                "added": str(status.get("pending_candidates_added", 0)),
                "updated": str(status.get("pending_candidates_updated", 0)),
                "total": str(status.get("pending_candidates_total", 0)),
            },
            "pending_trend_cards": _build_pending_trend_cards(status),
            "process": process_info,
            "recent_cycles": _normalize_recent_cycles(status.get("recent_cycles")),
            "events": _normalize_events(status.get("events")),
            "metrics": [
                {"label": "脚本状态", "value": _state_label(status.get("state"))},
                {"label": "健康度", "value": health["label"]},
                {"label": "最近输出", "value": str(len(output_payload.get("items") or []))},
                {"label": "运行模式", "value": _run_mode_label(status.get("run_mode"))},
                {"label": "当前阶段", "value": _stage_label(status.get("current_stage"))},
                {"label": "当前任务序号", "value": f"{task_index} / {task_total}"},
                {"label": "本轮采集", "value": str(status.get("items_collected", 0))},
                {"label": "单轮下载上限", "value": str(status.get("download_limit") or "未记录")},
                {"label": "本轮去重跳过", "value": str(status.get("duplicate_candidates_in_run", 0))},
                {"label": "历史已下载跳过", "value": str(status.get("skipped_already_downloaded", 0))},
                {"label": "新增待审批", "value": str(status.get("pending_candidates_added", 0))},
                {"label": "更新待审批", "value": str(status.get("pending_candidates_updated", 0))},
                {"label": "流水线状态", "value": _pipeline_status_label(status.get("pipeline_status"))},
                {"label": "轮次", "value": str(status.get("cycle_count", 0))},
                {"label": "最近耗时", "value": _display_duration(status.get("last_duration_seconds"))},
            ],
            "summary": [
                {"label": "最近心跳", "value": _display_time(status.get("last_heartbeat"))},
                {"label": "最近成功", "value": _display_time(status.get("last_success_at"))},
                {"label": "最近流水线", "value": _display_time(status.get("last_pipeline_at"))},
                {"label": "最近错误", "value": _display_time(status.get("last_error_at"))},
                {"label": "当前任务", "value": str(status.get("current_task") or "当前无采集任务")},
                {"label": "流水线摘要", "value": str(status.get("pipeline_summary") or "未记录")},
                {"label": "运行计划", "value": f"计划每 {status.get('expected_run_interval_minutes', '未记录')} 分钟运行一次，每轮最多下载 {status.get('download_limit', '未记录')} 个视频"},
                {"label": "去重结果", "value": f"本轮重复 {status.get('duplicate_candidates_in_run', 0)} · 历史已下载 {status.get('skipped_already_downloaded', 0)} · 下载上限跳过 {status.get('skipped_download_limit', 0)}"},
                {"label": "待审批增量", "value": f"新增 {status.get('pending_candidates_added', 0)} · 更新 {status.get('pending_candidates_updated', 0)} · 队列总量 {status.get('pending_candidates_total', 0)}"},
                {"label": "日志文件", "value": _display_dynamic_path(status.get('log_path'), Path(profile['log_path']))},
                {"label": "输出文件", "value": _display_dynamic_path(status.get('output_path'), Path(profile['output_path']))},
                {"label": "状态文件", "value": _display_dynamic_path(status.get('status_path'), Path(profile['status_path']))},
            ],
        },
    }


def get_collection_monitor_api_payload(collector_key: str = "local-social") -> dict[str, Any]:
    context = get_collection_monitor_context(collector_key)
    return {
        "page": context["page"],
        "monitor": context["monitor"],
    }


def start_local_collector(collector_key: str = "local-social") -> dict[str, Any]:
    profile = _resolve_profile(collector_key)
    process_info = get_collection_process_info(collector_key=collector_key)
    if process_info["is_running"]:
        raise RuntimeError(f"{profile['label']}脚本已经在运行。")

    python_executable = PROJECT_ROOT / ".venv" / "bin" / "python"
    command = [
        str(python_executable if python_executable.exists() else Path(sys.executable)),
        str(profile["script_path"]),
        *[str(arg) for arg in profile.get("start_args", [])],
    ]

    log_path = Path(profile["log_path"])
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as log_file:
        process = subprocess.Popen(  # noqa: S603
            command,
            cwd=PROJECT_ROOT,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

    Path(profile["pid_path"]).write_text(str(process.pid), encoding="utf-8")
    _update_status_file(
        profile,
        state="running",
        health="running",
        run_mode="manual",
        current_stage="collecting",
        pid=process.pid,
        last_heartbeat=datetime.now(timezone.utc).isoformat(),
        current_task=f"正在启动{profile['label']}进程",
        next_run_at="",
        event_message=f"已启动{profile['label']}进程，PID={process.pid}。",
    )
    return {"pid": process.pid}


def stop_local_collector(collector_key: str = "local-social") -> dict[str, Any]:
    profile = _resolve_profile(collector_key)
    process_info = get_collection_process_info(collector_key=collector_key)
    if not process_info["pid"]:
        raise RuntimeError(f"没有找到{profile['label']}进程。")

    pid = int(process_info["pid"])
    if process_info["is_running"]:
        os.kill(pid, signal.SIGTERM)
        deadline = time.time() + 3
        while time.time() < deadline:
            if not _is_pid_alive(pid):
                break
            time.sleep(0.1)

    pid_path = Path(profile["pid_path"])
    if pid_path.exists():
        pid_path.unlink()

    _update_status_file(
        profile,
        state="stopped",
        health="warning",
        current_stage="idle",
        pid=None,
        current_task="当前无采集任务",
        next_run_at="",
        event_message=f"已停止{profile['label']}进程，PID={pid}。",
    )
    return {"pid": pid}


def get_collection_process_info(status: dict[str, Any] | None = None, collector_key: str = "local-social") -> dict[str, Any]:
    profile = _resolve_profile(collector_key)
    payload = status if isinstance(status, dict) else _read_status_payload(profile)
    pid = _read_pid(payload, profile)
    is_running = _is_pid_alive(pid) if pid else False
    pid_path = Path(profile["pid_path"])
    if pid and not is_running and pid_path.exists():
        pid_path.unlink()
    return {
        "pid": pid,
        "is_running": is_running,
        "can_start": not is_running,
        "can_stop": is_running,
        "log_file": _display_path(Path(profile["log_path"])),
    }


def _read_status_payload(profile: Mapping[str, Any]) -> dict[str, Any]:
    status_path = Path(profile["status_path"])
    if not status_path.exists():
        return {}
    try:
        payload = json.loads(status_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"state": "error", "last_error": "状态文件损坏，无法解析。"}
    return payload if isinstance(payload, dict) else {}


def _read_output_payload(profile: Mapping[str, Any]) -> dict[str, Any]:
    output_path = Path(profile["output_path"])
    if not output_path.exists():
        return {"items": []}
    try:
        payload = json.loads(output_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"items": []}
    return payload if isinstance(payload, dict) else {"items": []}


def _build_health(status: dict[str, Any]) -> dict[str, str]:
    state = str(status.get("state") or "idle")
    heartbeat = _parse_time(status.get("last_heartbeat"))
    success = _parse_time(status.get("last_success_at"))
    now = datetime.now(timezone.utc)

    if state in {"running", "sleeping"}:
        if heartbeat and (now - heartbeat).total_seconds() <= 180:
            return {"kind": "ok", "label": "采集中"}
        return {"kind": "error", "label": "采集中断"}
    if state == "success":
        if success and (now - success).total_seconds() <= 24 * 3600:
            return {"kind": "ok", "label": "正常"}
        return {"kind": "warning", "label": "长时间未刷新"}
    if state == "error":
        return {"kind": "error", "label": "异常"}
    if state == "stopped":
        return {"kind": "warning", "label": "已停止"}
    return {"kind": "warning", "label": "未启动"}


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
    local = parsed.astimezone()
    return local.strftime("%Y-%m-%d %H:%M:%S")


def _display_duration(value: Any) -> str:
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return "未记录"
    return f"{seconds:.2f} 秒"


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


def _state_label(value: Any) -> str:
    mapping = {
        "idle": "未启动",
        "running": "运行中",
        "sleeping": "运行中",
        "success": "最近一次成功",
        "error": "最近一次失败",
        "stopped": "已停止",
    }
    return mapping.get(str(value or "idle"), str(value or "idle"))


def _run_mode_label(value: Any) -> str:
    mapping = {
        "once": "单次执行",
        "loop": "手动常驻",
        "manual": "手动常驻",
    }
    return mapping.get(str(value or "once"), str(value or "once"))


def _stage_label(value: Any) -> str:
    mapping = {
        "collecting": "正在采集",
        "running-pipeline": "正在执行流水线",
        "sleeping": "正在采集",
        "idle": "空闲",
        "error": "异常",
    }
    return mapping.get(str(value or "idle"), str(value or "idle"))


def _pipeline_status_label(value: Any) -> str:
    mapping = {
        "idle": "未开始",
        "running": "执行中",
        "success": "已完成",
        "skipped": "已跳过",
        "error": "失败",
    }
    return mapping.get(str(value or "idle"), str(value or "idle"))


def _normalize_events(value: Any) -> list[dict[str, str]]:
    events = value if isinstance(value, list) else []
    result: list[dict[str, str]] = []
    for item in events[:10]:
        if not isinstance(item, dict):
            continue
        result.append(
            {
                "at": _display_time(item.get("at")),
                "level": str(item.get("level") or "info"),
                "message": str(item.get("message") or ""),
            }
        )
    return result


def _normalize_recent_cycles(value: Any) -> list[dict[str, str]]:
    items = value if isinstance(value, list) else []
    result: list[dict[str, str]] = []
    for item in items[:8]:
        if not isinstance(item, dict):
            continue
        result.append(
            {
                "cycle": str(item.get("cycle") or "0"),
                "finished_at": _display_time(item.get("finished_at")),
                "state_label": _state_label(item.get("state")),
                "items_collected": str(item.get("items_collected", 0)),
                "task_progress": f"{item.get('tasks_completed', 0)} / {item.get('tasks_total', 0)}",
                "duration": _display_duration(item.get("duration_seconds")),
                "pipeline_status_label": _pipeline_status_label(item.get("pipeline_status")),
                "pending_delta": (
                    f"新增 {item.get('pending_candidates_added', 0)} · 更新 {item.get('pending_candidates_updated', 0)} · 队列总量 {item.get('pending_candidates_total', 0)}"
                    f" · 本轮重复 {item.get('duplicate_candidates_in_run', 0)} · 历史已下载 {item.get('skipped_already_downloaded', 0)}"
                ),
            }
        )
    return result


def _build_pending_trend_cards(status: dict[str, Any]) -> list[dict[str, str]]:
    recent_cycles = status.get("recent_cycles") if isinstance(status.get("recent_cycles"), list) else []
    current_added = int(status.get("pending_candidates_added") or 0)
    current_updated = int(status.get("pending_candidates_updated") or 0)
    current_total = int(status.get("pending_candidates_total") or 0)
    current_duplicates = int(status.get("duplicate_candidates_in_run") or 0)
    current_history_skips = int(status.get("skipped_already_downloaded") or 0)
    current_download_errors = int(status.get("download_errors") or 0)

    previous_added = _recent_cycle_metric(recent_cycles, 1, "pending_candidates_added")
    previous_updated = _recent_cycle_metric(recent_cycles, 1, "pending_candidates_updated")
    previous_total = _recent_cycle_metric(recent_cycles, 1, "pending_candidates_total")
    previous_duplicates = _recent_cycle_metric(recent_cycles, 1, "duplicate_candidates_in_run")
    previous_history_skips = _recent_cycle_metric(recent_cycles, 1, "skipped_already_downloaded")
    previous_download_errors = _recent_cycle_metric(recent_cycles, 1, "download_errors")

    recent_three_added = _recent_cycle_sum(recent_cycles, "pending_candidates_added")
    recent_three_updated = _recent_cycle_sum(recent_cycles, "pending_candidates_updated")
    recent_three_duplicates = _recent_cycle_sum(recent_cycles, "duplicate_candidates_in_run")
    recent_three_history_skips = _recent_cycle_sum(recent_cycles, "skipped_already_downloaded")
    recent_three_download_errors = _recent_cycle_sum(recent_cycles, "download_errors")

    return [
        {
            "label": "新增待审批",
            "value": str(current_added),
            "hint": f"上一轮 {previous_added} · 最近 3 轮累计 {recent_three_added}",
        },
        {
            "label": "更新待审批",
            "value": str(current_updated),
            "hint": f"上一轮 {previous_updated} · 最近 3 轮累计 {recent_three_updated}",
        },
        {
            "label": "队列总量",
            "value": str(current_total),
            "hint": f"上一轮 {previous_total} · 当前待审批池规模",
        },
        {
            "label": "本轮重复跳过",
            "value": str(current_duplicates),
            "hint": f"上一轮 {previous_duplicates} · 最近 3 轮累计 {recent_three_duplicates}",
        },
        {
            "label": "历史已下载跳过",
            "value": str(current_history_skips),
            "hint": f"上一轮 {previous_history_skips} · 最近 3 轮累计 {recent_three_history_skips}",
        },
        {
            "label": "下载失败",
            "value": str(current_download_errors),
            "hint": f"上一轮 {previous_download_errors} · 最近 3 轮累计 {recent_three_download_errors}",
        },
    ]


def _recent_cycle_metric(cycles: list[Any], index: int, key: str) -> int:
    if len(cycles) <= index or not isinstance(cycles[index], dict):
        return 0
    return int(cycles[index].get(key) or 0)


def _recent_cycle_sum(cycles: list[Any], key: str) -> int:
    total = 0
    for item in cycles[:3]:
        if not isinstance(item, dict):
            continue
        total += int(item.get(key) or 0)
    return total


def _read_pid(status: dict[str, Any], profile: Mapping[str, Any]) -> int | None:
    candidates = []
    pid_path = Path(profile["pid_path"])
    if pid_path.exists():
        candidates.append(pid_path.read_text(encoding="utf-8"))
    candidates.append(status.get("pid"))
    for value in candidates:
        try:
            pid = int(str(value).strip())
        except (TypeError, ValueError):
            continue
        if pid > 0:
            return pid
    return None


def _is_pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _update_status_file(profile: Mapping[str, Any], **changes: Any) -> None:
    payload = _read_status_payload(profile)
    payload.update(changes)
    payload.setdefault("collector_name", Path(profile["script_path"]).stem)
    payload.setdefault("events", [])
    if "event_message" in changes:
        payload["events"] = [
            {
                "at": datetime.now(timezone.utc).isoformat(),
                "level": str(changes.get("event_level") or "info"),
                "message": str(changes["event_message"]),
            },
            *[entry for entry in payload.get("events", []) if isinstance(entry, dict)],
        ][:20]
        payload.pop("event_message", None)
        payload.pop("event_level", None)
    status_path = Path(profile["status_path"])
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _resolve_profile(collector_key: str) -> dict[str, Any]:
    return COLLECTOR_PROFILES.get(str(collector_key or "").strip(), COLLECTOR_PROFILES["local-social"])


def _default_script_command(profile: Mapping[str, Any]) -> str:
    script_path = Path(profile["script_path"]).relative_to(PROJECT_ROOT)
    extra_args = " ".join(str(arg) for arg in profile.get("start_args", []))
    command = f".venv/bin/python {script_path}"
    return f"{command} {extra_args}".strip()