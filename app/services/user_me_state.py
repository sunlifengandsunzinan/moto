from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
USER_ME_STATE_PATH = PROJECT_ROOT / "data" / "raw" / "user_me_state.json"


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

    return {
        "favorite_count": len(favorites),
        "checkin_count": len(checkins),
    }


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


def _new_user_state() -> dict[str, Any]:
    return {
        "favorite_route_slugs": [],
        "checked_route_slugs": [],
        "updated_at": datetime.now().isoformat(timespec="seconds"),
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
