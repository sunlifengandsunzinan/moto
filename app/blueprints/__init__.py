from flask import Flask

from .api import api_bp
from .pages import main_bp, moto_bp, status_bp


def register_blueprints(app: Flask) -> None:
	app.register_blueprint(main_bp)
	app.register_blueprint(moto_bp)
	app.register_blueprint(status_bp)
	app.register_blueprint(api_bp)
