from flask import Blueprint, render_template, request

from ...services import (
    build_liaoning_spot_detail_context,
    build_plan_result,
    build_route_detail_context,
    build_routes_index_context,
    create_custom_plan_payload,
    get_custom_plan_context,
    get_home_context,
    get_planner_form_context,
    get_liaoning_moto_spot_by_slug,
    get_route_by_slug,
    get_route_templates,
)


moto_bp = Blueprint("moto", __name__)


@moto_bp.get("/moto")
def moto_home() -> str:
    return render_template("planner/home.html", **get_home_context())


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
    return render_template("planner/spot_detail.html", **build_liaoning_spot_detail_context(spot))


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