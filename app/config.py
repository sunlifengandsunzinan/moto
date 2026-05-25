import os
from pathlib import Path

from flask import Flask


def load_env_file(env_path: Path) -> None:
    if not env_path.exists():
        return

    for raw_line in env_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class BaseConfig:
    SECRET_KEY = "change-me-in-production"
    HOST = "0.0.0.0"
    PORT = 6001
    DEBUG = False
    TESTING = False


class DevelopmentConfig(BaseConfig):
    DEBUG = _as_bool(os.getenv("DEBUG"), True)


class ProductionConfig(BaseConfig):
    DEBUG = _as_bool(os.getenv("DEBUG"), False)


CONFIG_MAP = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
}


def get_config_class() -> type[BaseConfig]:
    app_env = os.getenv("APP_ENV", "development").strip().lower()
    return CONFIG_MAP.get(app_env, DevelopmentConfig)


def apply_environment_overrides(app: Flask) -> None:
    if "SECRET_KEY" in os.environ:
        app.config["SECRET_KEY"] = os.environ["SECRET_KEY"]

    if "HOST" in os.environ:
        app.config["HOST"] = os.environ["HOST"]

    if "PORT" in os.environ:
        app.config["PORT"] = int(os.environ["PORT"])

    if "DEBUG" in os.environ:
        app.config["DEBUG"] = _as_bool(os.environ["DEBUG"])