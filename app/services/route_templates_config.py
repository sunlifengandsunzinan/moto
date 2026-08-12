from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
import json
from functools import lru_cache
from pathlib import Path
from typing import Any


RouteTemplate = dict[str, Any]
ROUTE_TEMPLATES_JSON_PATH = Path(__file__).with_name("route_templates.json")


@lru_cache(maxsize=1)
def _load_route_templates_cached(mtime_ns: int) -> list[RouteTemplate]:
    return validate_route_templates_file(ROUTE_TEMPLATES_JSON_PATH)


def load_route_templates() -> list[RouteTemplate]:
    return _load_route_templates_cached(_route_templates_mtime_ns())


def get_route_template_by_slug(slug: str) -> RouteTemplate | None:
    target_slug = str(slug or "").strip()
    return next((deepcopy(route) for route in load_route_templates() if str(route.get("slug") or "") == target_slug), None)


def validate_route_templates_file(path: str | Path) -> list[RouteTemplate]:
    route_path = Path(path)
    with route_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return _validate_route_templates(data)


def validate_route_templates_data(data: Any) -> list[RouteTemplate]:
    return _validate_route_templates(data)


def save_route_template(route: Mapping[str, Any], *, original_slug: str | None = None) -> RouteTemplate:
    target_slug = str(route.get("slug") or "").strip()
    if not target_slug:
        raise ValueError("route.slug must be a non-empty string")

    existing_routes = [deepcopy(item) for item in load_route_templates()]
    normalized_original_slug = str(original_slug or target_slug).strip()
    replacement = deepcopy(dict(route))

    duplicate_slug = next(
        (
            item for item in existing_routes
            if str(item.get("slug") or "").strip() == target_slug
            and str(item.get("slug") or "").strip() != normalized_original_slug
        ),
        None,
    )
    if duplicate_slug is not None:
        raise ValueError(f"route.slug '{target_slug}' already exists")

    replaced = False
    updated_routes: list[RouteTemplate] = []
    for item in existing_routes:
        if str(item.get("slug") or "").strip() == normalized_original_slug and not replaced:
            updated_routes.append(replacement)
            replaced = True
            continue
        updated_routes.append(item)

    if not replaced:
        updated_routes.append(replacement)

    validated = validate_route_templates_data(updated_routes)
    _write_route_templates(validated)
    return deepcopy(replacement)


def delete_route_template(slug: str) -> bool:
    target_slug = str(slug or "").strip()
    existing_routes = [deepcopy(item) for item in load_route_templates()]
    remaining = [item for item in existing_routes if str(item.get("slug") or "").strip() != target_slug]
    if len(remaining) == len(existing_routes):
        return False

    validated = validate_route_templates_data(remaining)
    _write_route_templates(validated)
    return True


def save_route_templates(routes: list[Mapping[str, Any]]) -> list[RouteTemplate]:
    validated = validate_route_templates_data(list(routes))
    _write_route_templates(validated)
    return [deepcopy(route) for route in validated]


def _write_route_templates(routes: list[RouteTemplate]) -> None:
    temp_path = ROUTE_TEMPLATES_JSON_PATH.with_suffix(".json.tmp")
    temp_path.write_text(json.dumps(routes, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp_path.replace(ROUTE_TEMPLATES_JSON_PATH)
    _load_route_templates_cached.cache_clear()


def _route_templates_mtime_ns() -> int:
    try:
        return ROUTE_TEMPLATES_JSON_PATH.stat().st_mtime_ns
    except FileNotFoundError:
        return -1


def _validate_route_templates(data: Any) -> list[RouteTemplate]:
    if not isinstance(data, list):
        raise ValueError("Route templates JSON must be a list")

    for index, route in enumerate(data):
        if not isinstance(route, dict):
            raise ValueError(f"route[{index}] must be an object")

        slug = _require_string(route, "slug", f"route[{index}]")
        context = f"route[{slug}]"
        _require_string(route, "title", context)
        _require_string(route, "region", context)
        _require_number(route, "days", context)
        _require_string(route, "difficulty", context)
        _require_list(route, "scenery_type", context)
        _require_list(route, "bike_types", context)
        _require_list(route, "experience_levels", context)
        _require_string(route, "best_season", context)
        _require_number(route, "distance_km", context)
        _require_string(route, "budget_range", context)
        _require_string(route, "summary", context)
        _require_list(route, "spot_slugs", context)

        navigation = _require_mapping(route, "navigation", context)
        provider = _require_string(navigation, "provider", f"{context}.navigation")
        if provider != "amap":
            raise ValueError(f"{context}.navigation.provider must be 'amap'")
        waypoints = _require_list(navigation, "waypoints", f"{context}.navigation")
        if len(waypoints) < 2:
            raise ValueError(f"{context}.navigation.waypoints must contain at least 2 items")
        for waypoint_index, waypoint in enumerate(waypoints):
            _validate_waypoint(waypoint, f"{context}.navigation.waypoints[{waypoint_index}]")

        days_plan = _require_list(route, "days_plan", context)
        if not days_plan:
            raise ValueError(f"{context}.days_plan must contain at least 1 item")
        for day_index, day in enumerate(days_plan):
            _validate_day_plan(day, f"{context}.days_plan[{day_index}]")

        pois = _require_mapping(route, "pois", context)
        for poi_group, entries in pois.items():
            if not isinstance(entries, list):
                raise ValueError(f"{context}.pois.{poi_group} must be a list")
            for poi_index, poi in enumerate(entries):
                _validate_named_meta_item(poi, f"{context}.pois.{poi_group}[{poi_index}]")

        if "detail_highlights" in route:
            _require_list(route, "detail_highlights", context)
        if "detail_for_whom" in route:
            _require_string(route, "detail_for_whom", context)
        if "detail_notes" in route:
            _require_list(route, "detail_notes", context)
        if "checkpoints" in route:
            checkpoints = _require_list(route, "checkpoints", context)
            for checkpoint_index, checkpoint in enumerate(checkpoints):
                checkpoint_context = f"{context}.checkpoints[{checkpoint_index}]"
                _require_string(checkpoint, "name", checkpoint_context)
                _require_string(checkpoint, "summary", checkpoint_context)
                _require_string(checkpoint, "timing", checkpoint_context)
                image_value = str(checkpoint.get("image") or "").strip()
                if not image_value:
                    checkpoint["image"] = "route-checkpoint-placeholder.jpg"
        if "is_navigation_state_demo" in route and not isinstance(route["is_navigation_state_demo"], bool):
            raise ValueError(f"{context}.is_navigation_state_demo must be a boolean")

    return data


def _validate_waypoint(waypoint: Any, context: str) -> None:
    if not isinstance(waypoint, dict):
        raise ValueError(f"{context} must be an object")

    _require_string(waypoint, "name", context)

    if "coordinates" in waypoint:
        coordinates = _require_mapping(waypoint, "coordinates", context)
        _require_number(coordinates, "lat", f"{context}.coordinates")
        _require_number(coordinates, "lng", f"{context}.coordinates")
        return

    has_lat_lng = "lat" in waypoint or "lng" in waypoint
    has_alias_lat_lng = "latitude" in waypoint or "longitude" in waypoint
    if has_lat_lng:
        _require_number(waypoint, "lat", context)
        _require_number(waypoint, "lng", context)
    elif has_alias_lat_lng:
        _require_number(waypoint, "latitude", context)
        _require_number(waypoint, "longitude", context)


def _validate_day_plan(day: Any, context: str) -> None:
    if not isinstance(day, dict):
        raise ValueError(f"{context} must be an object")

    _require_number(day, "day", context)
    _require_string(day, "title", context)
    _require_number(day, "distance", context)
    _require_string(day, "ride_time", context)
    _require_list(day, "highlights", context)
    _require_string(day, "note", context)


def _validate_named_meta_item(item: Any, context: str) -> None:
    if not isinstance(item, dict):
        raise ValueError(f"{context} must be an object")

    _require_string(item, "name", context)
    _require_string(item, "meta", context)


def _require_mapping(data: Mapping[str, Any], key: str, context: str) -> dict[str, Any]:
    value = data.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"{context}.{key} must be an object")
    return value


def _require_list(data: Mapping[str, Any], key: str, context: str) -> list[Any]:
    value = data.get(key)
    if not isinstance(value, list):
        raise ValueError(f"{context}.{key} must be a list")
    return value


def _require_string(data: Mapping[str, Any], key: str, context: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{context}.{key} must be a non-empty string")
    return value


def _require_number(data: Mapping[str, Any], key: str, context: str) -> float:
    value = data.get(key)
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise ValueError(f"{context}.{key} must be a number")
    return float(value)
