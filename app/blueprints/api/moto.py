import os
from pathlib import Path

from flask import jsonify, request, send_file

from ...services import (
    build_route_detail_context,
    build_routes_index_context,
    clear_user_route_want_go_plan,
    get_route_want_go_stats,
    get_user_favorite_slugs,
    get_moto_me_context,
    get_liaoning_route_templates,
    get_user_navigation_preferences,
    get_user_want_go_route_plans,
    mark_user_route_checkin,
    get_route_by_slug,
    get_route_waypoint_collection_api_payload,
    set_user_navigation_preferences,
    set_user_route_favorite,
    set_user_route_want_go_plan,
    get_spots_index_context,
    gpx_service,
)
from ...services.route_engagement import get_route_engagement, increment_route_favorite, increment_route_navigation
from . import api_bp


def _resolve_user_id() -> str:
    return str(
        request.headers.get("X-Moto-User-Id")
        or request.args.get("user_id")
        or ""
    ).strip()


@api_bp.get("/moto/routes")
def moto_routes():
    user_id = _resolve_user_id()
    favorite_slugs = get_user_favorite_slugs(user_id)
    want_go_plans = get_user_want_go_route_plans(user_id)
    context = build_routes_index_context(get_liaoning_route_templates(), request.args)
    context["routes"] = [
        {
            **route,
            "is_favorite": str(route.get("slug") or "").strip() in favorite_slugs,
            "want_go": {
                **(route.get("want_go") if isinstance(route.get("want_go"), dict) else {}),
                "plan_bucket": want_go_plans.get(str(route.get("slug") or "").strip(), ""),
            },
        }
        for route in context.get("routes", [])
    ]
    return jsonify(context)


@api_bp.get("/moto/spots")
def moto_spots():
    context = get_spots_index_context(request.args)
    return jsonify(context)


@api_bp.get("/moto/me")
def moto_me():
    return jsonify(get_moto_me_context(_resolve_user_id()))


@api_bp.get("/moto/routes/<slug>")
def moto_route_detail(slug: str):
    route = get_route_by_slug(slug)
    if route is None:
        return jsonify({"message": "Route not found"}), 404
    payload = build_route_detail_context(route)
    user_id = _resolve_user_id()
    favorite_slugs = get_user_favorite_slugs(user_id)
    want_go_plans = get_user_want_go_route_plans(user_id)
    user_navigation_preferences = get_user_navigation_preferences(user_id)
    want_go_stats = get_route_want_go_stats(slug)
    payload["route"] = {
        **payload.get("route", {}),
        "is_favorite": str(slug).strip() in favorite_slugs,
        "engagement": {
            **(payload.get("route", {}).get("engagement") if isinstance(payload.get("route", {}).get("engagement"), dict) else {}),
            "want_go_count": int(want_go_stats.get("total_count") or 0),
        },
        "want_go": {
            **(payload.get("route", {}).get("want_go") if isinstance(payload.get("route", {}).get("want_go"), dict) else {}),
            "plan_bucket": want_go_plans.get(str(slug).strip(), ""),
            "this_month_count": int(want_go_stats.get("this_month_count") or 0),
            "next_month_count": int(want_go_stats.get("next_month_count") or 0),
            "later_count": int(want_go_stats.get("later_count") or 0),
            "total_count": int(want_go_stats.get("total_count") or 0),
        },
    }
    detail_sections = payload.get("detail_sections") if isinstance(payload.get("detail_sections"), dict) else {}
    navigation_import_assistant = detail_sections.get("navigation_import_assistant") if isinstance(detail_sections.get("navigation_import_assistant"), dict) else {}
    if navigation_import_assistant:
        navigation_import_assistant["preferred_map_app"] = str(user_navigation_preferences.get("preferred_map_app") or "").strip()
        detail_sections["navigation_import_assistant"] = navigation_import_assistant
        payload["detail_sections"] = detail_sections
    return jsonify(payload)


@api_bp.route("/moto/routes/<slug>/want-go", methods=["POST", "DELETE"])
def moto_route_want_go(slug: str):
    route = get_route_by_slug(slug)
    if route is None:
        return jsonify({"ok": False, "error": "Route not found"}), 404

    user_id = _resolve_user_id()
    if not user_id:
        return jsonify({"ok": False, "error": "Missing user id"}), 400

    if request.method == "DELETE":
        result = clear_user_route_want_go_plan(user_id, slug)
    else:
        data = request.get_json(silent=True) or {}
        plan_bucket = str(data.get("plan_bucket") or request.form.get("plan_bucket") or "").strip()
        result = set_user_route_want_go_plan(user_id, slug, plan_bucket)

    if not result.get("ok"):
        return jsonify({"ok": False, "error": "Invalid want-go plan bucket"}), 400

    want_go_stats = get_route_want_go_stats(slug)
    engagement = {
        **get_route_engagement(slug),
        "want_go_count": int(want_go_stats.get("total_count") or 0),
    }
    return jsonify({
        "ok": True,
        "slug": slug,
        "plan_bucket": str(result.get("plan_bucket") or ""),
        "want_go_count": int(result.get("want_go_count") or 0),
        "want_go": {
            "plan_bucket": str(result.get("plan_bucket") or ""),
            "this_month_count": int(want_go_stats.get("this_month_count") or 0),
            "next_month_count": int(want_go_stats.get("next_month_count") or 0),
            "later_count": int(want_go_stats.get("later_count") or 0),
            "total_count": int(want_go_stats.get("total_count") or 0),
        },
        "engagement": engagement,
    })


@api_bp.post("/moto/me/navigation-preferences")
def moto_me_navigation_preferences_save():
    user_id = _resolve_user_id()
    if not user_id:
        return jsonify({"ok": False, "error": "Missing user id"}), 400

    data = request.get_json(silent=True) or {}
    preferred_map_app = str(data.get("preferred_map_app") or request.form.get("preferred_map_app") or "").strip()
    result = set_user_navigation_preferences(user_id, preferred_map_app=preferred_map_app)
    if not result.get("ok"):
        return jsonify({"ok": False, "error": "Failed to save navigation preferences"}), 400

    return jsonify({
        "ok": True,
        "preferred_map_app": str(result.get("preferred_map_app") or ""),
    })


@api_bp.route("/moto/routes/<slug>/favorite", methods=["POST", "DELETE"])
def moto_route_favorite(slug: str):
    route = get_route_by_slug(slug)
    if route is None:
        return jsonify({"ok": False, "error": "Route not found"}), 404

    user_id = _resolve_user_id()
    if not user_id:
        return jsonify({"ok": False, "error": "Missing user id"}), 400

    is_favorite = request.method == "POST"
    favorite_result = set_user_route_favorite(user_id, slug, is_favorite)
    if not favorite_result.get("ok"):
        return jsonify({"ok": False, "error": "Failed to update favorite state"}), 400

    if is_favorite and favorite_result.get("changed"):
        increment_route_favorite(slug)

    stats = get_route_engagement(slug)
    return jsonify({
        "ok": True,
        "slug": slug,
        "is_favorite": bool(favorite_result.get("is_favorite")),
        "favorite_count": int(favorite_result.get("favorite_count") or 0),
        "engagement": stats,
    })


@api_bp.post("/moto/routes/<slug>/navigation")
def moto_route_navigation(slug: str):
    route = get_route_by_slug(slug)
    if route is None:
        return jsonify({"ok": False, "error": "Route not found"}), 404
    stats = increment_route_navigation(slug)

    user_id = _resolve_user_id()
    checkin_count = 0
    if user_id:
        checkin_result = mark_user_route_checkin(user_id, slug)
        checkin_count = int(checkin_result.get("checkin_count") or 0)

    return jsonify({"ok": True, "slug": slug, "engagement": stats, "checkin_count": checkin_count})


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


@api_bp.get("/moto/routes/<slug>/gpx")
def moto_route_gpx_download(slug: str):
    route = get_route_by_slug(slug)
    if route is None:
        return jsonify({"ok": False, "error": "Route not found"}), 404

    filename = str(route.get("gpx_file") or "").strip()
    if not filename:
        return jsonify({"ok": False, "error": "文件不存在"}), 404

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


@api_bp.get("/moto/gpx/queue/status")
def gpx_queue_status():
    """GPX 队列任务状态"""
    return jsonify({"ok": True, **gpx_service.get_gpx_queue_monitor_api_payload()})


@api_bp.post("/moto/gpx/queue/start")
def gpx_queue_start():
    """启动文件队列式 GPX 处理任务"""
    data = request.get_json(silent=True) or {}
    queue_file = str(data.get("queue_file") or request.form.get("queue_file") or "").strip()
    try:
        result = gpx_service.start_gpx_queue_task(queue_file)
    except (RuntimeError, FileNotFoundError, ValueError) as error:
        return jsonify({"ok": False, "error": str(error)}), 400
    return jsonify({"ok": True, **result})


@api_bp.post("/moto/gpx/queue/stop")
def gpx_queue_stop():
    """停止文件队列式 GPX 处理任务"""
    try:
        result = gpx_service.stop_gpx_queue_task()
    except RuntimeError as error:
        return jsonify({"ok": False, "error": str(error)}), 400
    return jsonify({"ok": True, **result})


@api_bp.post("/moto/gpx/process")
def gpx_process():
    """提交抖音视频 URL 处理"""
    data = request.get_json(force=True) or {}
    url = data.get("url", "").strip()
    urls = data.get("urls") if isinstance(data.get("urls"), list) else []
    urls_text = str(data.get("urls_text", "") or "")

    if urls or urls_text:
        result = gpx_service.run_gpx_process_urls(urls, urls_text)
        status_code = 200 if result.get("processed") else 400
        return jsonify(result), status_code

    if not url:
        return jsonify({"ok": False, "error": "缺少 url 参数"}), 400

    result = gpx_service.run_gpx_process_url(url)
    result["mode"] = "single"
    return jsonify(result)


@api_bp.post("/moto/gpx/export-candidates")
def gpx_export_candidates():
    """导出途经点为候选点位"""
    result = gpx_service.export_gpx_candidates()
    return jsonify(result)


@api_bp.post("/moto/gpx/sync-openclaw-routes")
def gpx_sync_openclaw_routes():
    """同步 OpenClaw 自动搜索到的合格路线到 GPX 页面数据源。"""
    return jsonify(gpx_service.sync_openclaw_route_records())