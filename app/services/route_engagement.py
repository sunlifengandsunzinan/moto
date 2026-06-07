from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ROUTE_ENGAGEMENT_PATH = PROJECT_ROOT / "data" / "raw" / "route_engagement_stats.json"


def get_route_engagement(slug: str) -> dict[str, int]:
    stats = _read_route_engagement_stats().get(str(slug or "").strip(), {})
    favorite_count = _safe_count(stats.get("favorite_count"))
    navigation_count = _safe_count(stats.get("navigation_count"))
    return {
        "favorite_count": favorite_count,
        "navigation_count": navigation_count,
        "total_count": favorite_count + navigation_count,
    }


def get_route_engagement_map(route_slugs: list[str] | None = None) -> dict[str, dict[str, int]]:
    if route_slugs is None:
        route_slugs = list(_read_route_engagement_stats().keys())
    return {slug: get_route_engagement(slug) for slug in route_slugs}


def increment_route_favorite(slug: str) -> dict[str, int]:
    return _increment_route_counter(slug, "favorite_count")


def increment_route_navigation(slug: str) -> dict[str, int]:
    return _increment_route_counter(slug, "navigation_count")


def _increment_route_counter(slug: str, field_name: str) -> dict[str, int]:
    normalized_slug = str(slug or "").strip()
    if not normalized_slug:
        return get_route_engagement("")

    payload = _read_full_payload()
    route_stats = payload.setdefault("routes", {}).setdefault(normalized_slug, {})
    route_stats[field_name] = _safe_count(route_stats.get(field_name)) + 1
    route_stats["updated_at"] = datetime.now().isoformat(timespec="seconds")
    _write_full_payload(payload)
    return get_route_engagement(normalized_slug)


def _read_route_engagement_stats() -> dict[str, dict[str, Any]]:
    payload = _read_full_payload()
    routes = payload.get("routes")
    return routes if isinstance(routes, dict) else {}


def _read_full_payload() -> dict[str, Any]:
    if not ROUTE_ENGAGEMENT_PATH.exists():
        return {"routes": {}}

    try:
        payload = json.loads(ROUTE_ENGAGEMENT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"routes": {}}

    if not isinstance(payload, dict):
        return {"routes": {}}
    if not isinstance(payload.get("routes"), dict):
        payload["routes"] = {}
    return payload


def _write_full_payload(payload: dict[str, Any]) -> None:
    ROUTE_ENGAGEMENT_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = ROUTE_ENGAGEMENT_PATH.with_suffix(".json.tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp_path.replace(ROUTE_ENGAGEMENT_PATH)


def _safe_count(value: Any) -> int:
    try:
        count = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, count)