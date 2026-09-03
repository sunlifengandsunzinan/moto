#!/usr/bin/env python3
import json
import os
import re
import subprocess
import sys
from urllib.parse import urlparse
from typing import Any

PREFERRED_SSIDS = ["BBA-Office-WLAN", "FF的Mate 60 Pro"]
WIFI_DEVICE = "en0"

TRIGGER_PATTERNS = [
    re.compile(r"(^|\s)pip(3)?\s+install(\s|$)", re.IGNORECASE),
    re.compile(r"python(3)?\s+-m\s+pip\s+install(\s|$)", re.IGNORECASE),
    re.compile(r"(^|\s)git\s+push(\s|$)", re.IGNORECASE),
    re.compile(r"wechat\s+devtools|微信开发者工具|wechatwebdevtools", re.IGNORECASE),
]


def load_payload() -> dict[str, Any]:
    raw = sys.stdin.read().strip()
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"raw": raw}


def extract_command(payload: dict[str, Any]) -> str:
    candidates = [
        payload.get("toolInput", {}).get("command"),
        payload.get("tool_input", {}).get("command"),
        payload.get("input", {}).get("command"),
        payload.get("arguments", {}).get("command"),
        payload.get("params", {}).get("command"),
        payload.get("command"),
    ]
    for value in candidates:
        if isinstance(value, str) and value.strip():
            return value.strip()
    raw = payload.get("raw")
    return raw if isinstance(raw, str) else ""


def extract_tool_name(payload: dict[str, Any]) -> str:
    candidates = [
        payload.get("toolName"),
        payload.get("tool_name"),
        payload.get("name"),
        payload.get("tool", {}).get("name") if isinstance(payload.get("tool"), dict) else None,
    ]
    for value in candidates:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def should_switch(tool_name: str, command: str) -> bool:
    if tool_name and "run_in_terminal" not in tool_name:
        return False
    if not command:
        return False
    return any(pattern.search(command) for pattern in TRIGGER_PATTERNS)


def run_command(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, check=False)


def run_shell(command: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, check=False, shell=True)


def current_ssid() -> str:
    result = run_command(["networksetup", "-getairportnetwork", WIFI_DEVICE])
    text = (result.stdout or result.stderr).strip()
    if result.returncode != 0:
        return ""
    marker = ": "
    return text.split(marker, 1)[1].strip() if marker in text else text


def reconnect_ssid(ssid: str) -> None:
    if not ssid:
        return
    run_command(["networksetup", "-setairportnetwork", WIFI_DEVICE, ssid])


def parse_git_remote_host() -> str:
    result = run_command(["git", "remote", "get-url", "origin"])
    remote_url = (result.stdout or "").strip()
    if result.returncode != 0 or not remote_url:
        return "github.com"

    if remote_url.startswith("git@"):
        host_part = remote_url.split("@", 1)[1]
        return host_part.split(":", 1)[0].strip() or "github.com"

    parsed = urlparse(remote_url)
    return parsed.hostname or "github.com"


def connectivity_target(command: str) -> tuple[str, str]:
    lower_command = command.lower()
    if "git push" in lower_command:
        host = parse_git_remote_host()
        return host, f"https://{host}"
    if "pip install" in lower_command or "-m pip install" in lower_command:
        return "pypi.org", "https://pypi.org/simple/pip/"
    return "developers.weixin.qq.com", "https://developers.weixin.qq.com/"


def network_is_reachable(command: str) -> bool:
    host, url = connectivity_target(command)
    curl_result = run_command(["curl", "-I", "--max-time", "8", url])
    if curl_result.returncode == 0:
        return True

    nc_command = f"nc -G 5 -z {host} 443"
    nc_result = run_shell(nc_command)
    return nc_result.returncode == 0


def candidate_ssids(current_ssid: str) -> list[str]:
    remaining = [ssid for ssid in PREFERRED_SSIDS if ssid != current_ssid]
    if current_ssid and current_ssid not in PREFERRED_SSIDS:
        return remaining + [current_ssid]
    return remaining


def emit_continue(message: str | None = None) -> None:
    payload: dict[str, Any] = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "permissionDecisionReason": "Network precheck passed"
        }
    }
    if message:
        payload["systemMessage"] = message
    print(json.dumps(payload, ensure_ascii=False))


def emit_ask(message: str) -> None:
    payload = {
        "systemMessage": message,
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": message
        }
    }
    print(json.dumps(payload, ensure_ascii=False))


def main() -> int:
    payload = load_payload()
    tool_name = extract_tool_name(payload)
    command = extract_command(payload)

    if not should_switch(tool_name, command):
        emit_continue()
        return 0

    previous_ssid = current_ssid()
    if previous_ssid and network_is_reachable(command):
        emit_continue(f"当前网络 {previous_ssid} 可用，继续执行命令。")
        return 0

    failures: list[str] = []
    for ssid in candidate_ssids(previous_ssid):
        switch_result = run_command([
            "networksetup",
            "-setairportnetwork",
            WIFI_DEVICE,
            ssid,
        ])

        switched_ssid = current_ssid()
        if switch_result.returncode == 0 and switched_ssid == ssid and network_is_reachable(command):
            emit_continue(f"当前网络不可用，已自动切换到 {ssid} 并通过连通性检查，继续执行命令。")
            return 0

        detail = (switch_result.stderr or switch_result.stdout or "未知错误").strip()
        failures.append(f"{ssid}: {detail or '切换后仍无法访问目标服务'}")

        if switched_ssid != previous_ssid:
            reconnect_ssid(previous_ssid)

    current_after_restore = current_ssid()
    if previous_ssid and current_after_restore != previous_ssid:
        reconnect_ssid(previous_ssid)

    failure_text = "；".join(failures) if failures else "未找到可切换网络"
    emit_ask(
        f"执行 `{command}` 前检测到当前网络不可用，已尝试在 {', '.join(PREFERRED_SSIDS)} 之间自动切换，但仍失败：{failure_text}。请确认备选网络可用且这台 Mac 已保存对应 Wi‑Fi。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
