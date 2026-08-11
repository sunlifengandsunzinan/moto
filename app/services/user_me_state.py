from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
USER_ME_STATE_PATH = PROJECT_ROOT / "data" / "raw" / "user_me_state.json"
WANT_GO_PLAN_BUCKETS = {"this_month", "next_month", "later"}


def normalize_user_id(user_id: str | None) -> str:
    value = str(user_id or "").strip()
    if not value:
        return ""
    return value[:128]


def get_user_favorite_slugs(user_id: str | None) -> set[str]:
    normalized_user_id = normalize_user_id(user_id)
    if not normalized_user_id:
        return set()

    user_state = _read_user_state(normalized_user_id)
    return {
        str(slug).strip()
        for slug in user_state.get("favorite_route_slugs", [])
        if str(slug).strip()
    }


def get_user_me_metrics(user_id: str | None) -> dict[str, int]:
    normalized_user_id = normalize_user_id(user_id)
    if not normalized_user_id:
        return {
            "favorite_count": 0,
            "checkin_count": 0,
            "want_go_count": 0,
            "want_go_this_month_count": 0,
            "want_go_next_month_count": 0,
            "want_go_later_count": 0,
        }

    user_state = _read_user_state(normalized_user_id)
    favorites = {
        str(slug).strip()
        for slug in user_state.get("favorite_route_slugs", [])
        if str(slug).strip()
    }
    checkins = {
        str(slug).strip()
        for slug in user_state.get("checked_route_slugs", [])
        if str(slug).strip()
    }
    want_go_plans = _normalized_want_go_plans(user_state)
    want_go_bucket_counts = {
        "this_month": 0,
        "next_month": 0,
        "later": 0,
    }
    for bucket in want_go_plans.values():
        if bucket in want_go_bucket_counts:
            want_go_bucket_counts[bucket] += 1

    return {
        "favorite_count": len(favorites),
        "checkin_count": len(checkins),
        "want_go_count": len(want_go_plans),
        "want_go_this_month_count": want_go_bucket_counts["this_month"],
        "want_go_next_month_count": want_go_bucket_counts["next_month"],
        "want_go_later_count": want_go_bucket_counts["later"],
    }


def get_user_want_go_route_plans(user_id: str | None) -> dict[str, str]:
    normalized_user_id = normalize_user_id(user_id)
    if not normalized_user_id:
        return {}

    user_state = _read_user_state(normalized_user_id)
    return _normalized_want_go_plans(user_state)


def set_user_route_want_go_plan(user_id: str | None, slug: str, plan_bucket: str) -> dict[str, Any]:
    normalized_user_id = normalize_user_id(user_id)
    normalized_slug = str(slug or "").strip()
    normalized_bucket = _normalize_want_go_plan_bucket(plan_bucket)
    if not normalized_user_id or not normalized_slug or not normalized_bucket:
        return {
            "ok": False,
            "changed": False,
            "plan_bucket": "",
            "want_go_count": 0,
        }

    payload = _read_payload()
    users = payload.setdefault("users", {})
    user_state = users.setdefault(normalized_user_id, _new_user_state())
    plans = _normalized_want_go_plans(user_state)
    previous_bucket = plans.get(normalized_slug)
    changed = previous_bucket != normalized_bucket

    plans[normalized_slug] = normalized_bucket
    _assign_want_go_plans(user_state, plans)
    user_state["updated_at"] = datetime.now().isoformat(timespec="seconds")

    if changed:
        _write_payload(payload)

    metrics = get_user_me_metrics(normalized_user_id)
    return {
        "ok": True,
        "changed": changed,
        "plan_bucket": normalized_bucket,
        "want_go_count": int(metrics.get("want_go_count") or 0),
    }


def clear_user_route_want_go_plan(user_id: str | None, slug: str) -> dict[str, Any]:
    normalized_user_id = normalize_user_id(user_id)
    normalized_slug = str(slug or "").strip()
    if not normalized_user_id or not normalized_slug:
        return {
            "ok": False,
            "changed": False,
            "plan_bucket": "",
            "want_go_count": 0,
        }

    payload = _read_payload()
    users = payload.setdefault("users", {})
    user_state = users.setdefault(normalized_user_id, _new_user_state())
    plans = _normalized_want_go_plans(user_state)
    changed = normalized_slug in plans
    if changed:
        plans.pop(normalized_slug, None)
        _assign_want_go_plans(user_state, plans)
        user_state["updated_at"] = datetime.now().isoformat(timespec="seconds")
        _write_payload(payload)

    metrics = get_user_me_metrics(normalized_user_id)
    return {
        "ok": True,
        "changed": changed,
        "plan_bucket": "",
        "want_go_count": int(metrics.get("want_go_count") or 0),
    }


def get_route_want_go_stats(slug: str) -> dict[str, int]:
    normalized_slug = str(slug or "").strip()
    if not normalized_slug:
        return {
            "this_month_count": 0,
            "next_month_count": 0,
            "later_count": 0,
            "total_count": 0,
        }

    stats_map = get_route_want_go_stats_map([normalized_slug])
    return stats_map.get(
        normalized_slug,
        {
            "this_month_count": 0,
            "next_month_count": 0,
            "later_count": 0,
            "total_count": 0,
        },
    )


def get_route_want_go_stats_map(route_slugs: list[str] | None = None) -> dict[str, dict[str, int]]:
    normalized_slugs = {
        str(slug).strip()
        for slug in (route_slugs or [])
        if str(slug).strip()
    }

    payload = _read_payload()
    users = payload.get("users") if isinstance(payload.get("users"), dict) else {}
    stats: dict[str, dict[str, int]] = {}

    for user_state in users.values():
        if not isinstance(user_state, dict):
            continue
        plans = _normalized_want_go_plans(user_state)
        for slug, bucket in plans.items():
            if normalized_slugs and slug not in normalized_slugs:
                continue
            route_stats = stats.setdefault(
                slug,
                {
                    "this_month_count": 0,
                    "next_month_count": 0,
                    "later_count": 0,
                    "total_count": 0,
                },
            )
            if bucket == "this_month":
                route_stats["this_month_count"] += 1
            elif bucket == "next_month":
                route_stats["next_month_count"] += 1
            elif bucket == "later":
                route_stats["later_count"] += 1
            route_stats["total_count"] += 1

    if normalized_slugs:
        for slug in normalized_slugs:
            stats.setdefault(
                slug,
                {
                    "this_month_count": 0,
                    "next_month_count": 0,
                    "later_count": 0,
                    "total_count": 0,
                },
            )

    return stats


def set_user_route_favorite(user_id: str | None, slug: str, is_favorite: bool) -> dict[str, Any]:
    normalized_user_id = normalize_user_id(user_id)
    normalized_slug = str(slug or "").strip()
    if not normalized_user_id or not normalized_slug:
        return {
            "ok": False,
            "changed": False,
            "is_favorite": False,
            "favorite_count": 0,
        }

    payload = _read_payload()
    users = payload.setdefault("users", {})
    user_state = users.setdefault(normalized_user_id, _new_user_state())

    favorites = {
        str(item).strip()
        for item in user_state.get("favorite_route_slugs", [])
        if str(item).strip()
    }

    changed = False
    if is_favorite:
        if normalized_slug not in favorites:
            favorites.add(normalized_slug)
            changed = True
    else:
        if normalized_slug in favorites:
            favorites.remove(normalized_slug)
            changed = True

    user_state["favorite_route_slugs"] = sorted(favorites)
    user_state["updated_at"] = datetime.now().isoformat(timespec="seconds")

    if changed:
        _write_payload(payload)

    return {
        "ok": True,
        "changed": changed,
        "is_favorite": is_favorite,
        "favorite_count": len(favorites),
    }


def mark_user_route_checkin(user_id: str | None, slug: str) -> dict[str, Any]:
    normalized_user_id = normalize_user_id(user_id)
    normalized_slug = str(slug or "").strip()
    if not normalized_user_id or not normalized_slug:
        return {
            "ok": False,
            "changed": False,
            "checkin_count": 0,
        }

    payload = _read_payload()
    users = payload.setdefault("users", {})
    user_state = users.setdefault(normalized_user_id, _new_user_state())

    checkins = {
        str(item).strip()
        for item in user_state.get("checked_route_slugs", [])
        if str(item).strip()
    }

    changed = normalized_slug not in checkins
    if changed:
        checkins.add(normalized_slug)
        user_state["checked_route_slugs"] = sorted(checkins)
        user_state["updated_at"] = datetime.now().isoformat(timespec="seconds")
        _write_payload(payload)

    return {
        "ok": True,
        "changed": changed,
        "checkin_count": len(checkins),
    }


def get_user_navigation_preferences(user_id: str | None) -> dict[str, Any]:
    normalized_user_id = normalize_user_id(user_id)
    if not normalized_user_id:
        return {"preferred_map_app": ""}

    user_state = _read_user_state(normalized_user_id)
    preferences = user_state.get("navigation_preferences") if isinstance(user_state.get("navigation_preferences"), dict) else {}
    return {
        "preferred_map_app": str(preferences.get("preferred_map_app") or "").strip(),
    }


def set_user_navigation_preferences(user_id: str | None, *, preferred_map_app: str | None = None) -> dict[str, Any]:
    normalized_user_id = normalize_user_id(user_id)
    normalized_map_app = str(preferred_map_app or "").strip()
    if not normalized_user_id:
        return {"ok": False, "preferred_map_app": ""}

    payload = _read_payload()
    users = payload.setdefault("users", {})
    user_state = users.setdefault(normalized_user_id, _new_user_state())
    navigation_preferences = user_state.setdefault("navigation_preferences", {})
    if not isinstance(navigation_preferences, dict):
        navigation_preferences = {}
        user_state["navigation_preferences"] = navigation_preferences

    navigation_preferences["preferred_map_app"] = normalized_map_app
    user_state["updated_at"] = datetime.now().isoformat(timespec="seconds")
    _write_payload(payload)

    return {
        "ok": True,
        "preferred_map_app": normalized_map_app,
    }


def _new_user_state() -> dict[str, Any]:
    return {
        "favorite_route_slugs": [],
        "checked_route_slugs": [],
        "want_go_plans": {},
        "navigation_preferences": {
            "preferred_map_app": "",
        },
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }


def _normalize_want_go_plan_bucket(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in WANT_GO_PLAN_BUCKETS:
        return normalized
    return ""


def _normalized_want_go_plans(user_state: dict[str, Any]) -> dict[str, str]:
    raw = user_state.get("want_go_plans")
    if not isinstance(raw, dict):
        return {}

    plans: dict[str, str] = {}
    for slug, value in raw.items():
        normalized_slug = str(slug or "").strip()
        if not normalized_slug:
            continue

        bucket_value = value.get("bucket") if isinstance(value, dict) else value
        normalized_bucket = _normalize_want_go_plan_bucket(bucket_value)
        if not normalized_bucket:
            continue
        plans[normalized_slug] = normalized_bucket
    return plans


def _assign_want_go_plans(user_state: dict[str, Any], plans: dict[str, str]) -> None:
    user_state["want_go_plans"] = {
        slug: {
            "bucket": bucket,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }
        for slug, bucket in sorted(plans.items())
    }


def _read_user_state(user_id: str) -> dict[str, Any]:
    payload = _read_payload()
    users = payload.get("users") if isinstance(payload.get("users"), dict) else {}
    user_state = users.get(user_id)
    if not isinstance(user_state, dict):
        return _new_user_state()
    return user_state


def _read_payload() -> dict[str, Any]:
    if not USER_ME_STATE_PATH.exists():
        return {"users": {}}

    try:
        payload = json.loads(USER_ME_STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"users": {}}

    if not isinstance(payload, dict):
        return {"users": {}}
    if not isinstance(payload.get("users"), dict):
        payload["users"] = {}
    return payload


def _write_payload(payload: dict[str, Any]) -> None:
    USER_ME_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = USER_ME_STATE_PATH.with_suffix(".json.tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp_path.replace(USER_ME_STATE_PATH)
