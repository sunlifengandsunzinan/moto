from flask import current_app, jsonify

from ...services import get_collection_monitor_api_payload, get_runtime_info
from . import api_bp


@api_bp.get("/status")
def status():
    runtime_info = get_runtime_info(current_app.config)
    return jsonify(runtime_info)


@api_bp.get("/collector-monitor")
def collector_monitor():
    return jsonify(get_collection_monitor_api_payload())
