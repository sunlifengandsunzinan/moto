#!/usr/bin/env python3
"""
本机 GPX 处理脚本 — 包装 gpx_generator.py，处理状态实时推送到阿里云。

用法:
  python scripts/run_local_gpx.py --url <douyin_url> [--url <url2> ...]
  python scripts/run_local_gpx.py --batch <keyword_list>
  python scripts/run_local_gpx.py --file <video_links.txt>

每次处理一个视频时，都会向阿里云 POST 状态报告：
  POST http://<aliyun>:6001/api/moto/gpx/report
"""

import argparse
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ============================================================
# 配置
# ============================================================
ALIYUN_HOST = "8.141.4.69"
ALIYUN_PORT = 6001
REPORT_URL = f"http://{ALIYUN_HOST}:{ALIYUN_PORT}/api/moto/gpx/report"

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
GPX_GENERATOR = SCRIPT_DIR / "gpx_generator.py"

# ============================================================
# 报告推送
# ============================================================

def _get_hostname() -> str:
    try:
        return socket.gethostname()
    except Exception:
        return "unknown"


def _get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(1)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "unknown"


def send_report(payload: dict[str, Any]) -> dict[str, Any] | None:
    """向阿里云推送状态报告，失败时不中断主流程。"""
    try:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            REPORT_URL,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        # 5s timeout
        with urllib.request.urlopen(req, timeout=5) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return result
    except (urllib.error.URLError, urllib.error.HTTPError, socket.timeout, json.JSONDecodeError, OSError) as e:
        print(f"  [report] ⚠️  推送状态失败: {e}")
        return None


def send_heartbeat(state: str, **kwargs) -> None:
    """发送一次状态心跳"""
    payload = {
        "state": state,
        "hostname": _get_hostname(),
        "local_ip": _get_local_ip(),
        "source": "local-gpx",
        "last_heartbeat": datetime.now(timezone.utc).isoformat(),
        **kwargs,
    }
    send_report(payload)


def send_event(level: str, message: str, **kwargs) -> None:
    """发送事件消息"""
    payload = {
        "state": "running" if level != "error" else "error",
        "level": level,
        "event": message,
        "hostname": _get_hostname(),
        "local_ip": _get_local_ip(),
        "source": "local-gpx",
        "last_heartbeat": datetime.now(timezone.utc).isoformat(),
        **kwargs,
    }
    send_report(payload)


# ============================================================
# GPX 处理
# ============================================================

def process_single_url(url: str, conn: Any = None) -> dict[str, Any]:
    """处理单个视频URL，返回结果。"""
    task_id = f"gpx-{int(time.time())}"
    
    send_heartbeat(
        state="running",
        current_stage="extracting",
        current_video=url,
        task_id=task_id,
        message=f"开始处理视频: {url}",
    )

    try:
        result = subprocess.run(
            [sys.executable, str(GPX_GENERATOR), "--url", url],
            capture_output=True, text=True, timeout=300,
            cwd=str(PROJECT_ROOT),
            env={**os.environ, "PYTHONPATH": str(PROJECT_ROOT)},
        )
        ok = result.returncode == 0
        stdout = result.stdout[-2000:]
        stderr = result.stderr[-2000:]

        send_event(
            level="success" if ok else "error",
            message=f"{'✅ 处理成功' if ok else '❌ 处理失败'}: {url}",
            current_video=url,
            task_id=task_id,
            current_stage="done" if ok else "failed",
            success_count=1 if ok else 0,
            failure_count=0 if ok else 1,
            processed_count=1,
            stdout_sample=stdout[:500],
            stderr_sample=stderr[:500],
        )

        return {
            "ok": ok,
            "url": url,
            "stdout": stdout,
            "stderr": stderr,
            "task_id": task_id,
        }

    except subprocess.TimeoutExpired:
        send_event(
            level="error",
            message=f"⏰ 处理超时: {url}",
            current_video=url,
            task_id=task_id,
            current_stage="timeout",
        )
        return {"ok": False, "url": url, "error": "处理超时（300s）"}
    
    except Exception as e:
        send_event(
            level="error",
            message=f"💥 处理异常: {url} — {e}",
            current_video=url,
            task_id=task_id,
            current_stage="exception",
        )
        return {"ok": False, "url": url, "error": str(e)}


def process_urls(urls: list[str]) -> list[dict[str, Any]]:
    """批量处理多个URL"""
    total = len(urls)
    success = 0
    failure = 0
    results = []

    send_heartbeat(
        state="running",
        current_stage="starting",
        message=f"开始批量处理, 共 {total} 个视频",
        total_urls=total,
        processed_count=0,
        success_count=0,
        failure_count=0,
        remaining=total,
    )

    for i, url in enumerate(urls, 1):
        print(f"\n[{i}/{total}] 处理: {url}")
        send_heartbeat(
            state="running",
            current_stage="processing",
            current_video=url,
            processed_count=i - 1,
            success_count=success,
            failure_count=failure,
            remaining=total - i + 1,
            progress=f"{i-1}/{total}",
        )

        result = process_single_url(url)
        results.append(result)

        if result.get("ok"):
            success += 1
        else:
            failure += 1

    state = "success" if failure == 0 else ("completed_with_errors" if success > 0 else "error")
    send_heartbeat(
        state=state,
        current_stage="finished",
        message=f"批量处理完成: 成功 {success}, 失败 {failure}",
        total_urls=total,
        processed_count=total,
        success_count=success,
        failure_count=failure,
        remaining=0,
        progress=f"{total}/{total}",
        ended_at=datetime.now(timezone.utc).isoformat(),
    )

    return results


def read_urls_from_file(file_path: str) -> list[str]:
    """从文件读取视频链接"""
    path = Path(file_path).expanduser()
    if not path.exists():
        print(f"❌ 文件不存在: {file_path}")
        return []
    
    urls = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("[DONE"):
            continue
        # Extract any URL from the line
        m = re.search(r"https?://\S+", line)
        if m:
            urls.append(m.group(0))
    return urls


# ============================================================
# 主入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="本机 GPX 处理（带阿里云状态推送）")
    parser.add_argument("--url", action="append", dest="urls", help="抖音视频 URL（可多个 --url）")
    parser.add_argument("--file", help="视频链接文本文件")
    parser.add_argument("--test-report", action="store_true", help="仅测试阿里云报告连通性")
    args = parser.parse_args()

    if args.test_report:
        print("测试阿里云报告推送...")
        result = send_report({
            "state": "test",
            "message": "本机 GPX 处理脚本连通性测试",
            "hostname": _get_hostname(),
            "local_ip": _get_local_ip(),
            "source": "local-gpx-test",
            "last_heartbeat": datetime.now(timezone.utc).isoformat(),
        })
        if result and result.get("ok"):
            print(f"[OK] 阿里云报告推送成功: {result.get('received_at')}")
        else:
            print(f"[FAIL] 阿里云报告推送失败: {result}")
        return

    # 收集要处理的 URLs
    urls = []
    if args.urls:
        urls.extend(args.urls)
    if args.file:
        urls.extend(read_urls_from_file(args.file))

    # 去重
    seen = set()
    unique_urls = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            unique_urls.append(url)

    if not unique_urls:
        print("❌ 没有需要处理的视频 URL")
        parser.print_help()
        return

    print(f"🎯 共 {len(unique_urls)} 个视频待处理")
    print(f"📡 推送地址: {REPORT_URL}")

    results = process_urls(unique_urls)

    # 汇总
    print(f"\n{'='*50}")
    print(f"处理完成: {len(results)} 个视频")
    print(f"  ✅ 成功: {sum(1 for r in results if r.get('ok'))}")
    print(f"  ❌ 失败: {sum(1 for r in results if not r.get('ok'))}")
    for r in results:
        status = "✅" if r.get("ok") else "❌"
        print(f"  {status} {r.get('url', '?')[:60]}")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
