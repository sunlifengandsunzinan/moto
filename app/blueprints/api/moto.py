from flask import jsonify, request

from ...services import (
    build_routes_index_context,
    get_moto_me_context,
    get_route_templates,
    get_route_waypoint_collection_api_payload,
    get_spots_index_context,
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


@api_bp.get("/moto/routes/collect/schema")
def moto_route_collect_schema():
    return jsonify(get_route_waypoint_collection_api_payload(request.args.get("route")))