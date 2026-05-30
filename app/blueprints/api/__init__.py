from flask import Blueprint


api_bp = Blueprint("api", __name__, url_prefix="/api")


from . import moto  # noqa: E402,F401
from . import status  # noqa: E402,F401