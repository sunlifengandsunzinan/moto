from flask import Blueprint, current_app, render_template

from ...services import get_runtime_info


status_bp = Blueprint("status", __name__)


@status_bp.get("/status")
def status() -> str:
    runtime_info = get_runtime_info(current_app.config)
    return render_template("status.html", runtime_info=runtime_info)
