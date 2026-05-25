from pathlib import Path

from flask import Flask

from .blueprints import register_blueprints
from .config import apply_environment_overrides, get_config_class, load_env_file


def create_app() -> Flask:
    load_env_file(Path(__file__).resolve().parent.parent / ".env")
    app = Flask(__name__, instance_relative_config=True)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    app.config.from_object(get_config_class())
    app.config.from_pyfile("config.py", silent=True)
    apply_environment_overrides(app)
    register_blueprints(app)
    return app