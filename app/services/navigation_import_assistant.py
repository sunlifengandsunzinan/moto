from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path
from typing import Any, Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[2]
IMPORT_ASSISTANT_CONFIG_PATH = PROJECT_ROOT / "app" / "services" / "navigation_import_assistant.json"


def build_navigation_import_assistant_payload(route_card: Mapping[str, Any]) -> dict[str, Any]:
    config = load_navigation_import_assistant_config()
    gpx_payload = route_card.get("gpx") if isinstance(route_card.get("gpx"), Mapping) else {}
    is_download_available = bool(gpx_payload.get("is_available"))

    map_apps = [
        _normalize_map_app(item)
        for item in config.get("map_apps", [])
        if isinstance(item, Mapping) and str(item.get("key") or "").strip()
    ]

    default_map_app = str(config.get("default_map_app") or "").strip()
    if default_map_app and all(item.get("key") != default_map_app for item in map_apps):
        default_map_app = ""

    troubleshooting = config.get("troubleshooting") if isinstance(config.get("troubleshooting"), Mapping) else {}

    return {
        "enabled": is_download_available,
        "title": str(config.get("title") or "导入助手").strip(),
        "subtitle": str(config.get("subtitle") or "已下载 GPX，按你常用地图继续导入导航。").strip(),
        "primary_button_label": str(config.get("primary_button_label") or "下载到地图导航").strip(),
        "helper_entry_label": str(config.get("helper_entry_label") or "不会导入？").strip(),
        "default_map_app": default_map_app,
        "open_helper_after_download": bool(config.get("open_helper_after_download", True)),
        "troubleshooting": {
            "title": str(troubleshooting.get("title") or "常见问题").strip(),
            "items": [
                str(item).strip()
                for item in troubleshooting.get("items", [])
                if str(item).strip()
            ],
        },
        "map_apps": map_apps,
    }


def load_navigation_import_assistant_config() -> dict[str, Any]:
    return _load_navigation_import_assistant_config_cached(_config_mtime_ns())


@lru_cache(maxsize=1)
def _load_navigation_import_assistant_config_cached(mtime_ns: int) -> dict[str, Any]:
    if not IMPORT_ASSISTANT_CONFIG_PATH.exists():
        return {}

    try:
        payload = json.loads(IMPORT_ASSISTANT_CONFIG_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}

    return payload if isinstance(payload, dict) else {}


def _config_mtime_ns() -> int:
    try:
        return IMPORT_ASSISTANT_CONFIG_PATH.stat().st_mtime_ns
    except FileNotFoundError:
        return -1


def _normalize_map_app(map_app: Mapping[str, Any]) -> dict[str, Any]:
    platform_steps = map_app.get("platform_steps") if isinstance(map_app.get("platform_steps"), Mapping) else {}

    normalized_steps: dict[str, list[str]] = {}
    for platform_key, values in platform_steps.items():
        if not isinstance(values, list):
            continue
        normalized_values = [str(item).strip() for item in values if str(item).strip()]
        if normalized_values:
            normalized_steps[str(platform_key).strip().lower()] = normalized_values

    return {
        "key": str(map_app.get("key") or "").strip(),
        "label": str(map_app.get("label") or "").strip(),
        "description": str(map_app.get("description") or "").strip(),
        "platform_steps": normalized_steps,
    }
