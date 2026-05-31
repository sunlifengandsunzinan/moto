"""
GPX 服务层 — 桥接 GPX 生成结果与 moto 项目数据流

提供：
  - 获取 GPX 已处理视频列表
  - 导出途经点到候选点位
  - 处理新视频（通过命令行调用 playwright 脚本）
  - 获取 GPX 文件列表
"""

import json
import sqlite3
import subprocess
import sys
from pathlib import Path
import xml.etree.ElementTree as ET

PROJECT_ROOT = Path(__file__).resolve().parents[2]
GPX_DIR = PROJECT_ROOT / "data" / "gpx"
DB_PATH = GPX_DIR / "processed_videos.db"
SCRIPTS_DIR = PROJECT_ROOT / "scripts"


def get_processed_videos(limit=50) -> list[dict]:
    """获取已处理的视频记录"""
    if not DB_PATH.exists():
        return []
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            "SELECT video_id, title, author, processed_at, spots_count, gpx_path "
            "FROM processed_videos ORDER BY processed_at DESC LIMIT ?", (limit,)
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
    gpx_files = get_gpx_files()
    return {
        "total_videos": len(processed),
        "total_gpx_files": len(gpx_files),
        "total_spots": sum(r.get("spots_count", 0) for r in processed),
    }
