from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
COLLECTOR_STATUS_PATH = PROJECT_ROOT / "data" / "raw" / "local_collection_status.json"
COLLECTOR_OUTPUT_PATH = PROJECT_ROOT / "data" / "raw" / "openclaw_export.json"
COLLECTOR_SCRIPT_PATH = PROJECT_ROOT / "scripts" / "run_local_social_collection.py"
COLLECTOR_LOG_PATH = PROJECT_ROOT / "data" / "raw" / "local_collection.log"
COLLECTOR_PID_PATH = PROJECT_ROOT / "data" / "raw" / "local_collection.pid"


def get_collection_monitor_context() -> dict[str, Any]:
    status = _read_status_payload()
    output_payload = _read_output_payload()
    process_info = get_collection_process_info(status)
    health = _build_health(status)
    task_index = int(status.get("current_task_index") or status.get("tasks_completed") or 0)
    task_total = int(status.get("tasks_total") or 0)
    return {
        "page": {
            "title": "本地采集监控",
            "description": "查看本地采集脚本是否正在运行、最近一次是否成功，以及当前输出数据是否正常刷新。",
        },
        "monitor": {
            "health": health,
            "state_label": _state_label(status.get("state")),
            "run_mode_label": _run_mode_label(status.get("run_mode")),
            "current_stage_label": _stage_label(status.get("current_stage")),
            "pipeline_status_label": _pipeline_status_label(status.get("pipeline_status")),
            "script_command": f".venv/bin/python {COLLECTOR_SCRIPT_PATH.relative_to(PROJECT_ROOT)}",
            "status_file": _display_path(COLLECTOR_STATUS_PATH),
            "output_file": _display_path(COLLECTOR_OUTPUT_PATH),
            "log_file": _display_path(COLLECTOR_LOG_PATH),
            "last_heartbeat": _display_time(status.get("last_heartbeat")),
            "last_success_at": _display_time(status.get("last_success_at")),
            "last_error_at": _display_time(status.get("last_error_at")),
            "last_pipeline_at": _display_time(status.get("last_pipeline_at")),
            "last_error": str(status.get("last_error") or "无"),
            "current_task": str(status.get("current_task") or "当前无采集任务"),
            "pipeline_summary": str(status.get("pipeline_summary") or "未记录"),
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
                {"label": "待审批增量", "value": f"新增 {status.get('pending_candidates_added', 0)} · 更新 {status.get('pending_candidates_updated', 0)} · 队列总量 {status.get('pending_candidates_total', 0)}"},
                {"label": "日志文件", "value": _display_path(COLLECTOR_LOG_PATH)},
                {"label": "输出文件", "value": _display_path(COLLECTOR_OUTPUT_PATH)},
                {"label": "状态文件", "value": _display_path(COLLECTOR_STATUS_PATH)},
            ],
        },
    }


def get_collection_monitor_api_payload() -> dict[str, Any]:
    context = get_collection_monitor_context()
    return {
        "page": context["page"],
        "monitor": context["monitor"],
    }


def start_local_collector() -> dict[str, Any]:
    process_info = get_collection_process_info()
    if process_info["is_running"]:
        raise RuntimeError("本地采集脚本已经在运行。")

    python_executable = PROJECT_ROOT / ".venv" / "bin" / "python"
    command = [str(python_executable if python_executable.exists() else Path(sys.executable)), str(COLLECTOR_SCRIPT_PATH), "--continuous"]

    COLLECTOR_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with COLLECTOR_LOG_PATH.open("a", encoding="utf-8") as log_file:
        process = subprocess.Popen(  # noqa: S603
            command,
            cwd=PROJECT_ROOT,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

    COLLECTOR_PID_PATH.write_text(str(process.pid), encoding="utf-8")
    _update_status_file(
        state="running",
        health="running",
        run_mode="manual",
        current_stage="collecting",
        pid=process.pid,
        last_heartbeat=datetime.now(timezone.utc).isoformat(),
        current_task="正在启动本地采集进程",
        next_run_at="",
        event_message=f"已启动本地采集进程，PID={process.pid}，将持续采集直到手动停止。",
    )
    return {"pid": process.pid}


def stop_local_collector() -> dict[str, Any]:
    process_info = get_collection_process_info()
    if not process_info["pid"]:
        raise RuntimeError("没有找到本地采集进程。")

    pid = int(process_info["pid"])
    if process_info["is_running"]:
        os.kill(pid, signal.SIGTERM)
        deadline = time.time() + 3
        while time.time() < deadline:
            if not _is_pid_alive(pid):
                break
            time.sleep(0.1)

    if COLLECTOR_PID_PATH.exists():
        COLLECTOR_PID_PATH.unlink()

    _update_status_file(
        state="stopped",
        health="warning",
        current_stage="idle",
        pid=None,
        current_task="当前无采集任务",
        next_run_at="",
        event_message=f"已停止本地采集进程，PID={pid}。",
    )
    return {"pid": pid}


def get_collection_process_info(status: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = status if isinstance(status, dict) else _read_status_payload()
    pid = _read_pid(payload)
    is_running = _is_pid_alive(pid) if pid else False
    if pid and not is_running and COLLECTOR_PID_PATH.exists():
        COLLECTOR_PID_PATH.unlink()
    return {
        "pid": pid,
        "is_running": is_running,
        "can_start": not is_running,
        "can_stop": is_running,
        "log_file": _display_path(COLLECTOR_LOG_PATH),
    }


def _read_status_payload() -> dict[str, Any]:
    if not COLLECTOR_STATUS_PATH.exists():
        return {}
    try:
        payload = json.loads(COLLECTOR_STATUS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"state": "error", "last_error": "状态文件损坏，无法解析。"}
    return payload if isinstance(payload, dict) else {}


def _read_output_payload() -> dict[str, Any]:
    if not COLLECTOR_OUTPUT_PATH.exists():
        return {"items": []}
    try:
        payload = json.loads(COLLECTOR_OUTPUT_PATH.read_text(encoding="utf-8"))
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
                "pending_delta": f"新增 {item.get('pending_candidates_added', 0)} · 更新 {item.get('pending_candidates_updated', 0)} · 队列总量 {item.get('pending_candidates_total', 0)}",
            }
        )
    return result


def _build_pending_trend_cards(status: dict[str, Any]) -> list[dict[str, str]]:
    recent_cycles = status.get("recent_cycles") if isinstance(status.get("recent_cycles"), list) else []
    current_added = int(status.get("pending_candidates_added") or 0)
    current_updated = int(status.get("pending_candidates_updated") or 0)
    current_total = int(status.get("pending_candidates_total") or 0)

    previous_added = _recent_cycle_metric(recent_cycles, 1, "pending_candidates_added")
    previous_updated = _recent_cycle_metric(recent_cycles, 1, "pending_candidates_updated")
    previous_total = _recent_cycle_metric(recent_cycles, 1, "pending_candidates_total")

    recent_three_added = _recent_cycle_sum(recent_cycles, "pending_candidates_added")
    recent_three_updated = _recent_cycle_sum(recent_cycles, "pending_candidates_updated")

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


def _read_pid(status: dict[str, Any]) -> int | None:
    candidates = []
    if COLLECTOR_PID_PATH.exists():
        candidates.append(COLLECTOR_PID_PATH.read_text(encoding="utf-8"))
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


def _update_status_file(**changes: Any) -> None:
    payload = _read_status_payload()
    payload.update(changes)
    payload.setdefault("collector_name", "liaoning-local-social-collector")
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
    COLLECTOR_STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    COLLECTOR_STATUS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")