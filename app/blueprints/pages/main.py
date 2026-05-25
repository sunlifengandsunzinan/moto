from flask import Blueprint, current_app, render_template

from ...services import get_runtime_info


main_bp = Blueprint("main", __name__)


@main_bp.get("/")
def index() -> str:
    runtime_info = get_runtime_info(current_app.config)
    return render_template("index.html", runtime_info=runtime_info)

