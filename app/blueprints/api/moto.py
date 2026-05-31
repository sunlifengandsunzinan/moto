import os
from pathlib import Path

from flask import jsonify, request, send_file

from ...services import (
    build_route_detail_context,
    build_routes_index_context,
    get_moto_me_context,
    get_route_by_slug,
    get_route_templates,
    get_route_waypoint_collection_api_payload,
    get_spots_index_context,
    gpx_service,
)
from . import api_bp


@api_bp.get("/moto/routes")
def moto_routes():
    context = build_routes_index_context(get_route_templates(), request.args)
    return jsonify(context)


@api_bp.get("/moto/spots")
def moto_spots():
    context = get_spots_index_context(request.args)
    return jsonify(context)


@api_bp.get("/moto/me")
def moto_me():
    return jsonify(get_moto_me_context())


@api_bp.get("/moto/routes/<slug>")
def moto_route_detail(slug: str):
    route = get_route_by_slug(slug)
    if route is None:
        return jsonify({"message": "Route not found"}), 404
    return jsonify(build_route_detail_context(route))


@api_bp.get("/moto/routes/collect/schema")
def moto_route_collect_schema():
    return jsonify(get_route_waypoint_collection_api_payload(request.args.get("route")))


# ──────────────────────────────────────────────
# GPX 路线提取 API
# ──────────────────────────────────────────────

@api_bp.get("/moto/gpx/processed")
def gpx_processed():
    """已处理视频列表"""
    limit = request.args.get("limit", 50, type=int)
    return jsonify({"ok": True, "videos": gpx_service.get_processed_videos(limit)})


@api_bp.get("/moto/gpx/files")
def gpx_files():
    """GPX 文件列表"""
    return jsonify({"ok": True, "files": gpx_service.get_gpx_files()})


@api_bp.get("/moto/gpx/download/<filename>")
def gpx_download(filename: str):
    """下载 GPX 文件"""
    PROJECT_ROOT = Path(__file__).resolve().parents[3]
    fpath = PROJECT_ROOT / "data" / "gpx" / filename
    if not fpath.exists() or not fpath.suffix == ".gpx":
        return jsonify({"ok": False, "error": "文件不存在"}), 404
    return send_file(str(fpath), mimetype="application/gpx+xml",
                     as_attachment=True, download_name=filename)


@api_bp.get("/moto/gpx/stats")
def gpx_stats():
    """GPX 统计"""
    return jsonify({"ok": True, **gpx_service.get_gpx_stats()})


@api_bp.post("/moto/gpx/process")
def gpx_process():
    """提交抖音视频 URL 处理"""
    data = request.get_json(force=True) or {}
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"ok": False, "error": "缺少 url 参数"}), 400
    result = gpx_service.run_gpx_process_url(url)
    return jsonify(result)


@api_bp.post("/moto/gpx/export-candidates")
def gpx_export_candidates():
    """导出途经点为候选点位"""
    result = gpx_service.export_gpx_candidates()
    return jsonify(result)