from pathlib import Path

from flask import Blueprint, Response, jsonify, redirect, render_template, request, send_file, url_for

from ...services import (
    build_liaoning_spot_detail_context,
    get_collection_monitor_context,
    start_local_collector,
    stop_local_collector,
    build_plan_result,
    build_route_recommendations_for_spot,
    build_spot_collection_record,
    build_route_detail_context,
    build_routes_index_context,
    clear_spot_review_data,
    create_custom_plan_payload,
    delete_reviewed_spots,
    get_custom_plan_context,
    get_home_context,
    render_liaoning_spot_image_svg,
    get_planner_form_context,
    get_liaoning_moto_spot_by_slug,
    get_route_by_slug,
    get_spots_index_context,
    get_spot_collection_context,
    get_route_templates,
    review_candidate_spot,
)


moto_bp = Blueprint("moto", __name__)
KEYFRAME_ROOT = Path(__file__).resolve().parents[3] / "data" / "raw" / "openclaw_keyframes"


@moto_bp.get("/moto")
def moto_home() -> str:
    return render_template("planner/home.html", **get_home_context())


@moto_bp.get("/moto/collector/monitor")
def moto_collector_monitor() -> str:
    context = get_collection_monitor_context()
    context["feedback"] = {
        "message": request.args.get("monitor_message", ""),
        "kind": request.args.get("monitor_kind", "info"),
    }
    return render_template("planner/collector_monitor.html", **context)


@moto_bp.get("/moto/collector/monitor.json")
def moto_collector_monitor_json():
    return jsonify(get_collection_monitor_context())


@moto_bp.post("/moto/collector/monitor/start")
def moto_collector_monitor_start():
    interval_raw = request.form.get("interval_seconds", "300")
    try:
        interval_seconds = max(int(interval_raw), 0)
        result = start_local_collector(interval_seconds)
        return redirect(
            url_for(
                "moto.moto_collector_monitor",
                monitor_kind="info",
                monitor_message=f"已启动本地采集进程，PID={result['pid']}，间隔 {result['interval_seconds']} 秒。",
            )
        )
    except Exception as error:
        return redirect(
            url_for(
                "moto.moto_collector_monitor",
                monitor_kind="error",
                monitor_message=str(error),
            )
        )


@moto_bp.post("/moto/collector/monitor/stop")
def moto_collector_monitor_stop():
    try:
        result = stop_local_collector()
        return redirect(
            url_for(
                "moto.moto_collector_monitor",
                monitor_kind="info",
                monitor_message=f"已停止本地采集进程，PID={result['pid']}。",
            )
        )
    except Exception as error:
        return redirect(
            url_for(
                "moto.moto_collector_monitor",
                monitor_kind="error",
                monitor_message=str(error),
            )
        )


@moto_bp.get("/moto/planner")
def moto_planner() -> str:
    route_slug = request.args.get("route")
    origin = request.args.get("origin")
    return render_template("planner/form.html", **get_planner_form_context(route_slug, origin))


@moto_bp.post("/moto/planner/result")
def moto_planner_result() -> str:
    return render_template("planner/result.html", **build_plan_result(request.form))


@moto_bp.get("/moto/routes")
def moto_routes() -> str:
    context = build_routes_index_context(get_route_templates(), request.args)
    return render_template("planner/routes.html", **context)


@moto_bp.get("/moto/routes/<slug>")
def moto_route_detail(slug: str) -> tuple[str, int] | str:
    route = get_route_by_slug(slug)
    if route is None:
        return render_template("404.html"), 404
    return render_template("planner/route_detail.html", **build_route_detail_context(route))


@moto_bp.get("/moto/spots/liaoning/<slug>")
def moto_liaoning_spot_detail(slug: str) -> tuple[str, int] | str:
    spot = get_liaoning_moto_spot_by_slug(slug)
    if spot is None:
        return render_template("404.html"), 404
    context = build_liaoning_spot_detail_context(spot)
    context["recommended_routes"] = build_route_recommendations_for_spot(spot)
    return render_template("planner/spot_detail.html", **context)


@moto_bp.get("/moto/spots/liaoning/<slug>/images/<variant>.svg")
def moto_liaoning_spot_image(slug: str, variant: str) -> Response | tuple[str, int]:
    spot = get_liaoning_moto_spot_by_slug(slug)
    if spot is None:
        return render_template("404.html"), 404
    svg = render_liaoning_spot_image_svg(spot, variant)
    return Response(svg, mimetype="image/svg+xml")


@moto_bp.get("/moto/spots")
def moto_spots() -> str:
    return render_template("planner/spots.html", **get_spots_index_context(request.args))


@moto_bp.route("/moto/spots/collect", methods=["GET", "POST"])
def moto_spot_collect() -> str:
    form_data = request.form if request.method == "POST" else None
    candidate_slug = request.args.get("candidate")
    apply_video_analysis = request.args.get("apply_video_analysis", "").strip().lower() in {"1", "true", "yes"}
    review_feedback = {
        "decision": request.args.get("review_decision", ""),
        "name": request.args.get("review_name", ""),
        "action": request.args.get("review_action", ""),
        "message": request.args.get("review_message", ""),
    }
    return render_template(
        "planner/spot_collect.html",
        **get_spot_collection_context(form_data, candidate_slug, review_feedback, apply_video_analysis),
    )


@moto_bp.get("/moto/spots/collect/keyframes/<path:keyframe_path>")
def moto_spot_collect_keyframe(keyframe_path: str):
    normalized = Path(keyframe_path)
    resolved = (KEYFRAME_ROOT / normalized).resolve()
    if KEYFRAME_ROOT.resolve() not in resolved.parents or not resolved.exists() or not resolved.is_file():
        return render_template("404.html"), 404
    return send_file(resolved)


@moto_bp.post("/moto/spots/review/<slug>/<decision>")
def moto_spot_review(slug: str, decision: str):
    result = review_candidate_spot(slug, decision)
    if result is None:
        return redirect(url_for("moto.moto_spot_collect"))

    if result["next_slug"]:
        return redirect(
            url_for(
                "moto.moto_spot_collect",
                candidate=result["next_slug"],
                review_decision=result["decision"],
                review_name=result["name"],
            )
        )

    return redirect(
        url_for(
            "moto.moto_spot_collect",
            review_decision=result["decision"],
            review_name=result["name"],
        )
    )


@moto_bp.post("/moto/spots/reviewed/delete")
def moto_spot_reviewed_delete():
    selected_keys = request.form.getlist("reviewed_item_keys")
    result = delete_reviewed_spots(selected_keys)
    message = "未选择任何已审批数据。" if result["deleted"] == 0 else f"已删除 {result['deleted']} 条已审批数据。"
    return redirect(
        url_for(
            "moto.moto_spot_collect",
            review_action="delete-reviewed",
            review_message=message,
        )
    )


@moto_bp.post("/moto/spots/reviewed/clear")
def moto_spot_reviewed_clear():
    result = clear_spot_review_data()
    return redirect(
        url_for(
            "moto.moto_spot_collect",
            review_action="clear-all",
            review_message=f"已清空 {result['total']} 条数据（待审核 {result['candidates']} / 已批准 {result['approved']} / 已拒绝 {result['rejected']}）。",
        )
    )


@moto_bp.route("/moto/custom", methods=["GET", "POST"])
def moto_custom() -> str:
    if request.method == "POST":
        submission = create_custom_plan_payload(request.form)
        return render_template(
            "planner/custom_success.html",
            submission=submission,
            page={
                "title": "需求已提交",
                "description": "我们会先判断你的行程条件，再联系你确认是否适合定制。",
            },
        )
    return render_template("planner/custom.html", **get_custom_plan_context())