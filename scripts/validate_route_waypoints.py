from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import create_app
from app.services.planner_service import (
    _route_cached_preview_polyline_points,
    _route_navigation_waypoints,
    _route_tencent_preview_polyline,
)
from app.services.route_templates_config import load_route_templates


def _distance_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    # Haversine distance in meters.
    r = 6371000.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    d_lat = math.radians(lat2 - lat1)
    d_lng = math.radians(lng2 - lng1)
    a = math.sin(d_lat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(d_lng / 2) ** 2
    return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _nearest_polyline_index_and_distance(
    point: Mapping[str, Any], polyline: list[Mapping[str, float]]
) -> tuple[int, float]:
    target_lat = float(point["lat"])
    target_lng = float(point["lng"])
    best_index = -1
    best_distance = float("inf")

    for idx, sample in enumerate(polyline):
        dist = _distance_m(target_lat, target_lng, float(sample["lat"]), float(sample["lng"]))
        if dist < best_distance:
            best_distance = dist
            best_index = idx

    return best_index, best_distance


def _validate_route(
    route: Mapping[str, Any], max_offset_m: float, use_live_polyline: bool
) -> list[str]:
    issues: list[str] = []
    slug = str(route.get("slug") or "")

    waypoints = _route_navigation_waypoints(route)
    coordinate_waypoints = [
        p for p in waypoints if p.get("has_coordinates") and p.get("lat") is not None and p.get("lng") is not None
    ]
    if len(coordinate_waypoints) < 2:
        return issues

    if use_live_polyline:
        poly_result = _route_tencent_preview_polyline(coordinate_waypoints)
        polyline = poly_result.get("points") if isinstance(poly_result.get("points"), list) else []
        status = str(poly_result.get("status") or "")
    else:
        polyline = _route_cached_preview_polyline_points(route)
        status = "cached"

    if len(polyline) < 2:
        issues.append(f"{slug}: no polyline points (status={status})")
        return issues

    snapped_indices: list[int] = []
    for idx, point in enumerate(coordinate_waypoints):
        nearest_idx, offset_m = _nearest_polyline_index_and_distance(point, polyline)
        snapped_indices.append(nearest_idx)
        if offset_m > max_offset_m:
            name = str(point.get("name") or f"point-{idx + 1}")
            issues.append(
                f"{slug}: off-route waypoint '{name}' offset={offset_m:.0f}m (> {max_offset_m:.0f}m)"
            )

    for i in range(1, len(snapped_indices)):
        if snapped_indices[i] < snapped_indices[i - 1]:
            prev_name = str(coordinate_waypoints[i - 1].get("name") or f"point-{i}")
            curr_name = str(coordinate_waypoints[i].get("name") or f"point-{i + 1}")
            issues.append(
                f"{slug}: waypoint order mismatch '{prev_name}' -> '{curr_name}' (polyline index {snapped_indices[i - 1]} -> {snapped_indices[i]})"
            )

    return issues


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate route waypoint quality: off-route offset and order mismatch against route polyline."
    )
    parser.add_argument("--slug", default="", help="Only validate one route slug")
    parser.add_argument(
        "--max-offset-m",
        type=float,
        default=1200.0,
        help="Maximum allowed waypoint-to-polyline offset in meters (default: 1200)",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Use live Tencent segmented polyline instead of cached polyline",
    )
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        routes = load_route_templates()
        target_routes = [r for r in routes if str(r.get("slug") or "") == args.slug] if args.slug else routes

        if args.slug and not target_routes:
            print(f"NOT FOUND: {args.slug}")
            return 1

        all_issues: list[str] = []
        for route in target_routes:
            all_issues.extend(_validate_route(route, args.max_offset_m, args.live))

    if all_issues:
        print("FOUND ISSUES:")
        for line in all_issues:
            print(f"- {line}")
        return 2

    print(f"OK: {len(target_routes)} route(s) passed waypoint quality checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
