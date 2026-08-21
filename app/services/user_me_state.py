from __future__ import annotations

from datetime import datetime, timedelta
import json
from pathlib import Path
from typing import Any
import uuid


PROJECT_ROOT = Path(__file__).resolve().parents[2]
USER_ME_STATE_PATH = PROJECT_ROOT / "data" / "raw" / "user_me_state.json"
WANT_GO_PLAN_BUCKETS = {"this_month", "next_month", "later"}
ACTIVE_WANT_GO_PLAN_BUCKETS = {"this_month", "next_month"}


def _current_timestamp() -> str:
    return datetime.now().isoformat(timespec="seconds")


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
    route_collections = _normalized_route_checkpoint_collections(user_state)
    checkin_count = sum(int(collection.get("checked_count") or 0) for collection in route_collections.values())
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
        "checkin_count": checkin_count,
        "want_go_count": len(want_go_plans),
        "want_go_this_month_count": want_go_bucket_counts["this_month"],
        "want_go_next_month_count": want_go_bucket_counts["next_month"],
        "want_go_later_count": want_go_bucket_counts["later"],
    }


def get_user_want_go_route_plans(user_id: str | None) -> dict[str, str]:
    normalized_user_id = normalize_user_id(user_id)
    if not normalized_user_id:
        return {}

    payload = _read_payload()
    users = payload.setdefault("users", {})
    user_state = _ensure_user_state(users.setdefault(normalized_user_id, _new_user_state()))
    if _expire_user_state_want_go_plans(user_state):
        _write_payload(payload)
    return _normalized_want_go_plans(user_state)


def get_user_want_go_route_plan_details(user_id: str | None) -> dict[str, dict[str, str]]:
    normalized_user_id = normalize_user_id(user_id)
    if not normalized_user_id:
        return {}

    payload = _read_payload()
    users = payload.setdefault("users", {})
    user_state = _ensure_user_state(users.setdefault(normalized_user_id, _new_user_state()))
    if _expire_user_state_want_go_plans(user_state):
        _write_payload(payload)
    return _normalized_want_go_plan_details(user_state)


def get_user_want_go_records(user_id: str | None) -> list[dict[str, str]]:
    normalized_user_id = normalize_user_id(user_id)
    if not normalized_user_id:
        return []

    user_state = _read_user_state(normalized_user_id)
    records = _normalized_want_go_records(user_state)
    active_details = _normalized_want_go_plan_details(user_state)
    for slug, detail in active_details.items():
        selected_at = str(detail.get("updated_at") or "").strip()
        records.append(
            {
                "id": f"active:{slug}:{selected_at}",
                "slug": slug,
                "bucket": str(detail.get("bucket") or "").strip(),
                "selected_at": selected_at,
                "updated_at": selected_at,
                "archived_at": "",
                "status": "active",
            }
        )

    records.sort(
        key=lambda item: (
            str(item.get("selected_at") or item.get("updated_at") or ""),
            str(item.get("slug") or ""),
            str(item.get("id") or ""),
        ),
        reverse=True,
    )
    return records


def upsert_user_profile(user_id: str | None, profile: dict[str, Any] | None) -> dict[str, Any]:
    normalized_user_id = normalize_user_id(user_id)
    normalized_profile = _normalize_user_profile(profile)
    if not normalized_user_id or not normalized_profile:
        return {"ok": False, "profile": {}}

    payload = _read_payload()
    users = payload.setdefault("users", {})
    user_state = _ensure_user_state(users.setdefault(normalized_user_id, _new_user_state()))
    now = _current_timestamp()
    merged_profile = {
        **(user_state.get("profile") if isinstance(user_state.get("profile"), dict) else {}),
        **normalized_profile,
    }
    user_state["profile"] = merged_profile
    user_state["updated_at"] = now
    _write_payload(payload)

    return {"ok": True, "profile": merged_profile}


def get_admin_user_summaries() -> list[dict[str, Any]]:
    payload = _read_payload()
    users = payload.get("users") if isinstance(payload.get("users"), dict) else {}
    summaries: list[dict[str, Any]] = []

    for user_id, raw_user_state in users.items():
        normalized_user_id = normalize_user_id(user_id)
        if not normalized_user_id or not isinstance(raw_user_state, dict):
            continue

        user_state = _ensure_user_state(raw_user_state)
        profile = user_state.get("profile") if isinstance(user_state.get("profile"), dict) else {}
        vehicles = _normalized_vehicles(user_state)
        maintenance_record_count = sum(
            len(vehicle.get("maintenance_records") if isinstance(vehicle.get("maintenance_records"), list) else [])
            for vehicle in vehicles
        )
        vehicle_summaries = [
            {
                "vehicle_id": str(vehicle.get("id") or "").strip(),
                "title": " ".join(
                    part
                    for part in [
                        str(vehicle.get("nickname") or "").strip(),
                        str(vehicle.get("brand") or "").strip(),
                        str(vehicle.get("model") or "").strip(),
                    ]
                    if part
                ).strip()
                or "未命名爱车",
                "plate_no": str(vehicle.get("plate_no") or "").strip(),
                "maintenance_count": len(vehicle.get("maintenance_records") if isinstance(vehicle.get("maintenance_records"), list) else []),
                "maintenance_preview": [
                    " / ".join(
                        part
                        for part in [
                            str(record.get("date") or "").strip(),
                            str(record.get("item") or "").strip(),
                            (
                                f"{str(record.get('mileage_km') or '').strip()}km"
                                if str(record.get("mileage_km") or "").strip()
                                else ""
                            ),
                        ]
                        if part
                    ).strip()
                    for record in (
                        vehicle.get("maintenance_records")
                        if isinstance(vehicle.get("maintenance_records"), list)
                        else []
                    )[:5]
                ],
                "updated_at": str(vehicle.get("updated_at") or "").strip(),
            }
            for vehicle in vehicles
        ]
        metrics = get_user_me_metrics(normalized_user_id)
        display_name = str(profile.get("nickName") or "").strip() or "未填写昵称"
        avatar_url = str(profile.get("avatarUrl") or "").strip()
        summaries.append(
            {
                "user_id": normalized_user_id,
                "display_name": display_name,
                "avatar_url": avatar_url,
                "city": str(profile.get("city") or "").strip(),
                "province": str(profile.get("province") or "").strip(),
                "created_at": str(user_state.get("created_at") or user_state.get("updated_at") or "").strip(),
                "updated_at": str(user_state.get("updated_at") or "").strip(),
                "favorite_count": int(metrics.get("favorite_count") or 0),
                "want_go_count": int(metrics.get("want_go_count") or 0),
                "checkin_count": int(metrics.get("checkin_count") or 0),
                "vehicle_count": len(vehicles),
                "maintenance_record_count": int(maintenance_record_count),
                "vehicles": vehicle_summaries,
            }
        )

    summaries.sort(
        key=lambda item: (
            str(item.get("created_at") or ""),
            str(item.get("updated_at") or ""),
            str(item.get("user_id") or ""),
        ),
        reverse=True,
    )
    return summaries


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
    user_state = _ensure_user_state(users.setdefault(normalized_user_id, _new_user_state()))
    changed = _expire_user_state_want_go_plans(user_state)
    plan_details = _normalized_want_go_plan_details(user_state)
    previous_detail = plan_details.get(normalized_slug) or {}
    previous_bucket = str(previous_detail.get("bucket") or "").strip()
    previous_updated_at = str(previous_detail.get("updated_at") or "").strip()

    if previous_bucket and not _is_want_go_plan_expired(previous_bucket, previous_updated_at):
        metrics = get_user_me_metrics(normalized_user_id)
        return {
            "ok": False,
            "changed": False,
            "plan_bucket": previous_bucket,
            "want_go_count": int(metrics.get("want_go_count") or 0),
            "error": _build_want_go_locked_message(previous_bucket, previous_updated_at),
        }

    now = _current_timestamp()
    changed = changed or previous_bucket != normalized_bucket
    plan_details[normalized_slug] = {
        "bucket": normalized_bucket,
        "updated_at": now,
    }
    _assign_want_go_plan_details(user_state, plan_details)
    user_state["updated_at"] = now

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
    user_state = _ensure_user_state(users.setdefault(normalized_user_id, _new_user_state()))
    changed = _expire_user_state_want_go_plans(user_state)
    plan_details = _normalized_want_go_plan_details(user_state)
    changed = normalized_slug in plan_details or changed
    if changed:
        plan_details.pop(normalized_slug, None)
        _assign_want_go_plan_details(user_state, plan_details)
        user_state["updated_at"] = _current_timestamp()
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
    changed = False

    for user_state in users.values():
        if not isinstance(user_state, dict):
            continue
        user_state = _ensure_user_state(user_state)
        changed = _expire_user_state_want_go_plans(user_state) or changed
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

    if changed:
        _write_payload(payload)

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
    user_state = _ensure_user_state(users.setdefault(normalized_user_id, _new_user_state()))

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
    user_state["updated_at"] = _current_timestamp()

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
    user_state = _ensure_user_state(users.setdefault(normalized_user_id, _new_user_state()))

    checkins = {
        str(item).strip()
        for item in user_state.get("checked_route_slugs", [])
        if str(item).strip()
    }

    changed = normalized_slug not in checkins
    if changed:
        checkins.add(normalized_slug)
        user_state["checked_route_slugs"] = sorted(checkins)
        user_state["updated_at"] = _current_timestamp()
        _write_payload(payload)

    return {
        "ok": True,
        "changed": changed,
        "checkin_count": len(checkins),
    }


def get_user_route_checkpoint_collection(
    user_id: str | None,
    slug: str,
    *,
    checkpoint_total: int | None = None,
) -> dict[str, Any]:
    normalized_user_id = normalize_user_id(user_id)
    normalized_slug = str(slug or "").strip()
    normalized_total = _normalize_checkpoint_total(checkpoint_total)
    if not normalized_user_id or not normalized_slug:
        return _empty_route_checkpoint_collection(normalized_slug, normalized_total)

    user_state = _read_user_state(normalized_user_id)
    collections = _normalized_route_checkpoint_collections(user_state)
    collection = collections.get(normalized_slug)
    if not collection:
        return _empty_route_checkpoint_collection(normalized_slug, normalized_total)

    total = max(int(collection.get("checkpoint_total") or 0), normalized_total)
    checked_indexes = sorted({
        int(index)
        for index in collection.get("checked_indexes", [])
        if isinstance(index, int) and index > 0
    })
    if total > 0:
        checked_indexes = [index for index in checked_indexes if index <= total]
    checked_count = len(checked_indexes)
    completion_percent = int(round((checked_count / total) * 100)) if total > 0 else 0
    badge = collection.get("badge") if isinstance(collection.get("badge"), dict) else None

    return {
        "slug": normalized_slug,
        "route_title": str(collection.get("route_title") or "").strip(),
        "checkpoint_total": total,
        "checked_indexes": checked_indexes,
        "checked_count": checked_count,
        "completion_percent": completion_percent,
        "is_completed": bool(total > 0 and checked_count >= total),
        "badge": badge or {},
        "has_badge": bool(badge),
        "updated_at": str(collection.get("updated_at") or "").strip(),
    }


def mark_user_route_checkpoint_checkin(
    user_id: str | None,
    slug: str,
    *,
    checkpoint_index: int,
    checkpoint_total: int,
    route_title: str | None = None,
) -> dict[str, Any]:
    normalized_user_id = normalize_user_id(user_id)
    normalized_slug = str(slug or "").strip()
    normalized_total = _normalize_checkpoint_total(checkpoint_total)
    normalized_index = _normalize_checkpoint_index(checkpoint_index, normalized_total)
    normalized_route_title = str(route_title or "").strip()
    if not normalized_user_id or not normalized_slug or normalized_total <= 0 or normalized_index <= 0:
        return {
            "ok": False,
            "changed": False,
            "collection": _empty_route_checkpoint_collection(normalized_slug, normalized_total),
            "badge_unlocked": False,
        }

    payload = _read_payload()
    users = payload.setdefault("users", {})
    user_state = _ensure_user_state(users.setdefault(normalized_user_id, _new_user_state()))
    collections = _normalized_route_checkpoint_collections(user_state)
    collection = collections.setdefault(
        normalized_slug,
        {
            "route_title": normalized_route_title,
            "checkpoint_total": normalized_total,
            "checked_indexes": [],
            "badge": {},
            "updated_at": _current_timestamp(),
        },
    )

    if normalized_route_title:
        collection["route_title"] = normalized_route_title
    collection["checkpoint_total"] = max(int(collection.get("checkpoint_total") or 0), normalized_total)

    checked_indexes = {
        int(index)
        for index in collection.get("checked_indexes", [])
        if isinstance(index, int) and index > 0
    }
    before_checked_count = len(checked_indexes)
    checked_indexes.add(normalized_index)
    changed = len(checked_indexes) != before_checked_count
    total = int(collection.get("checkpoint_total") or 0)
    checked_indexes = {index for index in checked_indexes if index <= total}
    checked_count = len(checked_indexes)
    is_completed = bool(total > 0 and checked_count >= total)

    existing_badge = collection.get("badge") if isinstance(collection.get("badge"), dict) else {}
    has_existing_badge = bool(existing_badge.get("awarded_at"))
    badge_unlocked = False
    badge_payload: dict[str, Any] = dict(existing_badge) if isinstance(existing_badge, dict) else {}
    if is_completed and not has_existing_badge:
        awarded_at = _current_timestamp()
        route_title_text = str(collection.get("route_title") or normalized_slug).strip() or normalized_slug
        badge_payload = {
            "title": f"{route_title_text} 征服者",
            "subtitle": "路线打卡已集齐",
            "awarded_at": awarded_at,
            "share_text": f"我已完成 {route_title_text} 全部打卡点，拿到征服者徽章！",
        }
        badge_unlocked = True
        changed = True

    collection["checked_indexes"] = sorted(checked_indexes)
    collection["badge"] = badge_payload
    collection["updated_at"] = _current_timestamp()
    collections[normalized_slug] = collection
    _assign_route_checkpoint_collections(user_state, collections)

    if changed:
        user_state["updated_at"] = _current_timestamp()
        _write_payload(payload)

    current_collection = get_user_route_checkpoint_collection(
        normalized_user_id,
        normalized_slug,
        checkpoint_total=normalized_total,
    )
    return {
        "ok": True,
        "changed": changed,
        "collection": current_collection,
        "badge_unlocked": badge_unlocked,
        "badge": current_collection.get("badge") or {},
    }


def get_user_route_collections(user_id: str | None) -> dict[str, dict[str, Any]]:
    normalized_user_id = normalize_user_id(user_id)
    if not normalized_user_id:
        return {}

    user_state = _read_user_state(normalized_user_id)
    collections = _normalized_route_checkpoint_collections(user_state)
    result: dict[str, dict[str, Any]] = {}
    for slug in sorted(collections.keys()):
        result[slug] = get_user_route_checkpoint_collection(normalized_user_id, slug)
    return result


def get_route_collection_community_stats() -> dict[str, Any]:
    payload = _read_payload()
    users = payload.get("users") if isinstance(payload.get("users"), dict) else {}
    now = datetime.now()
    week_ago = now - timedelta(days=7)

    weekly_checkpoint_total = 0
    weekly_completed_routes = 0
    by_route: dict[str, dict[str, Any]] = {}

    for raw_user_state in users.values():
        if not isinstance(raw_user_state, dict):
            continue

        collections = _normalized_route_checkpoint_collections(_ensure_user_state(raw_user_state))
        for slug, collection in collections.items():
            total = int(collection.get("checkpoint_total") or 0)
            checked_count = int(collection.get("checked_count") or len(collection.get("checked_indexes", [])) or 0)
            completion_percent = int(round((checked_count / total) * 100)) if total > 0 else 0
            is_completed = bool(total > 0 and checked_count >= total)
            updated_at = str(collection.get("updated_at") or "").strip()

            route_item = by_route.setdefault(
                slug,
                {
                    "members": 0,
                    "completed_members": 0,
                    "completion_percent_sum": 0,
                },
            )
            route_item["members"] += 1
            route_item["completion_percent_sum"] += completion_percent
            if is_completed:
                route_item["completed_members"] += 1

            is_recent = False
            if updated_at:
                try:
                    is_recent = datetime.fromisoformat(updated_at) >= week_ago
                except ValueError:
                    is_recent = False

            if is_recent:
                weekly_checkpoint_total += checked_count
                if is_completed:
                    weekly_completed_routes += 1

    for item in by_route.values():
        members = int(item.get("members") or 0)
        completion_sum = int(item.get("completion_percent_sum") or 0)
        item["avg_completion_percent"] = int(round(completion_sum / members)) if members > 0 else 0

    return {
        "weekly_checkpoint_total": max(0, weekly_checkpoint_total),
        "weekly_completed_routes": max(0, weekly_completed_routes),
        "route_stats": by_route,
    }


def get_user_club_activity_signup_slugs(user_id: str | None) -> set[str]:
    normalized_user_id = normalize_user_id(user_id)
    if not normalized_user_id:
        return set()

    user_state = _read_user_state(normalized_user_id)
    raw_signups = user_state.get("club_activity_signups")
    if not isinstance(raw_signups, dict):
        return set()

    return {
        str(slug).strip()
        for slug in raw_signups.keys()
        if str(slug).strip()
    }


def get_club_activity_signup_counts(activity_slugs: list[str] | None = None) -> dict[str, int]:
    payload = _read_payload()
    users = payload.get("users") if isinstance(payload.get("users"), dict) else {}
    scoped_slugs = {
        str(slug).strip()
        for slug in (activity_slugs or [])
        if str(slug).strip()
    }

    counts: dict[str, int] = {}
    for raw_user_state in users.values():
        if not isinstance(raw_user_state, dict):
            continue

        user_state = _ensure_user_state(raw_user_state)
        raw_signups = user_state.get("club_activity_signups")
        if not isinstance(raw_signups, dict):
            continue

        for slug in raw_signups.keys():
            normalized_slug = str(slug).strip()
            if not normalized_slug:
                continue
            if scoped_slugs and normalized_slug not in scoped_slugs:
                continue
            counts[normalized_slug] = int(counts.get(normalized_slug) or 0) + 1

    return counts


def signup_user_club_activity(
    user_id: str | None,
    activity_slug: str,
    *,
    activity_title: str | None = None,
) -> dict[str, Any]:
    normalized_user_id = normalize_user_id(user_id)
    normalized_slug = str(activity_slug or "").strip()
    normalized_title = str(activity_title or "").strip()
    if not normalized_user_id or not normalized_slug:
        return {"ok": False, "activity_slug": normalized_slug, "is_signed_up": False, "signup_count": 0}

    payload = _read_payload()
    users = payload.setdefault("users", {})
    user_state = _ensure_user_state(users.setdefault(normalized_user_id, _new_user_state()))
    raw_signups = user_state.setdefault("club_activity_signups", {})
    if not isinstance(raw_signups, dict):
        raw_signups = {}
        user_state["club_activity_signups"] = raw_signups

    already_signed = normalized_slug in raw_signups
    if not already_signed:
        raw_signups[normalized_slug] = {
            "activity_title": normalized_title,
            "signed_up_at": _current_timestamp(),
        }
        user_state["updated_at"] = _current_timestamp()
        _write_payload(payload)

    signup_count = int(get_club_activity_signup_counts([normalized_slug]).get(normalized_slug) or 0)
    return {
        "ok": True,
        "activity_slug": normalized_slug,
        "is_signed_up": True,
        "already_signed_up": already_signed,
        "signup_count": signup_count,
    }


def get_user_vehicles(user_id: str | None) -> list[dict[str, Any]]:
    normalized_user_id = normalize_user_id(user_id)
    if not normalized_user_id:
        return []

    user_state = _read_user_state(normalized_user_id)
    return _normalized_vehicles(user_state)


def create_user_vehicle(user_id: str | None, vehicle_payload: dict[str, Any] | None) -> dict[str, Any]:
    normalized_user_id = normalize_user_id(user_id)
    if not normalized_user_id:
        return {"ok": False, "error": "Missing user id"}

    normalized_vehicle = _normalize_vehicle_payload(vehicle_payload, existing=None)
    if not normalized_vehicle.get("brand") and not normalized_vehicle.get("model") and not normalized_vehicle.get("nickname"):
        normalized_vehicle["nickname"] = "我的爱车"

    payload = _read_payload()
    users = payload.setdefault("users", {})
    user_state = _ensure_user_state(users.setdefault(normalized_user_id, _new_user_state()))
    vehicles = _normalized_vehicles(user_state)

    vehicle_id = _new_id("veh")
    now = _current_timestamp()
    new_vehicle = {
        "id": vehicle_id,
        "nickname": normalized_vehicle["nickname"],
        "brand": normalized_vehicle["brand"],
        "model": normalized_vehicle["model"],
        "year": normalized_vehicle["year"],
        "plate_no": normalized_vehicle["plate_no"],
        "purchase_date": normalized_vehicle["purchase_date"],
        "note": normalized_vehicle["note"],
        "maintenance": normalized_vehicle["maintenance"],
        "maintenance_records": normalized_vehicle["maintenance_records"],
        "created_at": now,
        "updated_at": now,
    }
    vehicles.append(new_vehicle)
    user_state["vehicles"] = vehicles
    user_state["updated_at"] = now
    _write_payload(payload)

    return {
        "ok": True,
        "vehicle": new_vehicle,
        "vehicles": vehicles,
    }


def update_user_vehicle(user_id: str | None, vehicle_id: str, vehicle_payload: dict[str, Any] | None) -> dict[str, Any]:
    normalized_user_id = normalize_user_id(user_id)
    normalized_vehicle_id = str(vehicle_id or "").strip()
    if not normalized_user_id or not normalized_vehicle_id:
        return {"ok": False, "error": "Invalid vehicle id"}

    payload = _read_payload()
    users = payload.setdefault("users", {})
    user_state = _ensure_user_state(users.setdefault(normalized_user_id, _new_user_state()))
    vehicles = _normalized_vehicles(user_state)

    target_index = -1
    for index, vehicle in enumerate(vehicles):
        if str(vehicle.get("id") or "").strip() == normalized_vehicle_id:
            target_index = index
            break
    if target_index < 0:
        return {"ok": False, "error": "Vehicle not found"}

    existing = vehicles[target_index]
    normalized_vehicle = _normalize_vehicle_payload(vehicle_payload, existing=existing)
    if not normalized_vehicle.get("brand") and not normalized_vehicle.get("model") and not normalized_vehicle.get("nickname"):
        normalized_vehicle["nickname"] = str(existing.get("nickname") or "我的爱车").strip() or "我的爱车"

    now = _current_timestamp()
    updated_vehicle = {
        **existing,
        "nickname": normalized_vehicle["nickname"],
        "brand": normalized_vehicle["brand"],
        "model": normalized_vehicle["model"],
        "year": normalized_vehicle["year"],
        "plate_no": normalized_vehicle["plate_no"],
        "purchase_date": normalized_vehicle["purchase_date"],
        "note": normalized_vehicle["note"],
        "maintenance": normalized_vehicle["maintenance"],
        "updated_at": now,
    }
    updated_vehicle["maintenance_records"] = normalized_vehicle["maintenance_records"]

    vehicles[target_index] = updated_vehicle
    user_state["vehicles"] = vehicles
    user_state["updated_at"] = now
    _write_payload(payload)

    return {
        "ok": True,
        "vehicle": updated_vehicle,
        "vehicles": vehicles,
    }


def delete_user_vehicle(user_id: str | None, vehicle_id: str) -> dict[str, Any]:
    normalized_user_id = normalize_user_id(user_id)
    normalized_vehicle_id = str(vehicle_id or "").strip()
    if not normalized_user_id or not normalized_vehicle_id:
        return {"ok": False, "error": "Invalid vehicle id"}

    payload = _read_payload()
    users = payload.setdefault("users", {})
    user_state = _ensure_user_state(users.setdefault(normalized_user_id, _new_user_state()))
    vehicles = _normalized_vehicles(user_state)
    next_vehicles = [
        vehicle
        for vehicle in vehicles
        if str(vehicle.get("id") or "").strip() != normalized_vehicle_id
    ]
    if len(next_vehicles) == len(vehicles):
        return {"ok": False, "error": "Vehicle not found"}

    user_state["vehicles"] = next_vehicles
    user_state["updated_at"] = _current_timestamp()
    _write_payload(payload)
    return {
        "ok": True,
        "vehicle_id": normalized_vehicle_id,
        "vehicles": next_vehicles,
    }


def add_user_vehicle_maintenance_record(
    user_id: str | None,
    vehicle_id: str,
    record_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    normalized_user_id = normalize_user_id(user_id)
    normalized_vehicle_id = str(vehicle_id or "").strip()
    if not normalized_user_id or not normalized_vehicle_id:
        return {"ok": False, "error": "Invalid vehicle id"}

    payload = _read_payload()
    users = payload.setdefault("users", {})
    user_state = _ensure_user_state(users.setdefault(normalized_user_id, _new_user_state()))
    vehicles = _normalized_vehicles(user_state)
    vehicle = _find_vehicle(vehicles, normalized_vehicle_id)
    if not vehicle:
        return {"ok": False, "error": "Vehicle not found"}

    normalized_record = _normalize_maintenance_record(record_payload, existing=None)
    if not normalized_record.get("item"):
        return {"ok": False, "error": "保养项目不能为空"}

    now = _current_timestamp()
    record = {
        "id": _new_id("mt"),
        "date": normalized_record["date"],
        "item": normalized_record["item"],
        "location": normalized_record["location"],
        "mileage_km": normalized_record["mileage_km"],
        "cost": normalized_record["cost"],
        "note": normalized_record["note"],
        "created_at": now,
        "updated_at": now,
    }
    existing_records = _normalize_maintenance_records(vehicle.get("maintenance_records"))
    next_records = [record, *existing_records]
    vehicle["maintenance"] = next_records[0]
    vehicle["maintenance_records"] = next_records
    vehicle["updated_at"] = now
    user_state["vehicles"] = vehicles
    user_state["updated_at"] = now
    _write_payload(payload)

    return {
        "ok": True,
        "vehicle": vehicle,
        "record": record,
    }


def update_user_vehicle_maintenance_record(
    user_id: str | None,
    vehicle_id: str,
    record_id: str,
    record_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    normalized_user_id = normalize_user_id(user_id)
    normalized_vehicle_id = str(vehicle_id or "").strip()
    normalized_record_id = str(record_id or "").strip()
    if not normalized_user_id or not normalized_vehicle_id or not normalized_record_id:
        return {"ok": False, "error": "Invalid record id"}

    payload = _read_payload()
    users = payload.setdefault("users", {})
    user_state = _ensure_user_state(users.setdefault(normalized_user_id, _new_user_state()))
    vehicles = _normalized_vehicles(user_state)
    vehicle = _find_vehicle(vehicles, normalized_vehicle_id)
    if not vehicle:
        return {"ok": False, "error": "Vehicle not found"}

    existing_records = _normalize_maintenance_records(vehicle.get("maintenance_records"))
    existing_index = -1
    for index, record in enumerate(existing_records):
        if str(record.get("id") or "").strip() == normalized_record_id:
            existing_index = index
            break
    if existing_index < 0:
        return {"ok": False, "error": "Maintenance record not found"}
    existing = existing_records[existing_index]

    normalized_record = _normalize_maintenance_record(record_payload, existing=existing)
    if not normalized_record.get("item"):
        return {"ok": False, "error": "保养项目不能为空"}

    now = _current_timestamp()
    updated_record = {
        **(existing if isinstance(existing, dict) else {}),
        "id": str(existing.get("id") or normalized_record_id or _new_id("mt")).strip(),
        "date": normalized_record["date"],
        "item": normalized_record["item"],
        "location": normalized_record["location"],
        "mileage_km": normalized_record["mileage_km"],
        "cost": normalized_record["cost"],
        "note": normalized_record["note"],
        "updated_at": now,
    }
    updated_record.setdefault("created_at", str(existing.get("created_at") or now).strip())
    existing_records[existing_index] = updated_record
    existing_records.sort(key=lambda item: (str(item.get("updated_at") or ""), str(item.get("created_at") or "")), reverse=True)
    vehicle["maintenance"] = existing_records[0] if existing_records else {}
    vehicle["maintenance_records"] = existing_records
    vehicle["updated_at"] = now
    user_state["vehicles"] = vehicles
    user_state["updated_at"] = now
    _write_payload(payload)

    return {
        "ok": True,
        "vehicle": vehicle,
        "record": updated_record,
    }


def delete_user_vehicle_maintenance_record(
    user_id: str | None,
    vehicle_id: str,
    record_id: str,
) -> dict[str, Any]:
    normalized_user_id = normalize_user_id(user_id)
    normalized_vehicle_id = str(vehicle_id or "").strip()
    normalized_record_id = str(record_id or "").strip()
    if not normalized_user_id or not normalized_vehicle_id or not normalized_record_id:
        return {"ok": False, "error": "Invalid record id"}

    payload = _read_payload()
    users = payload.setdefault("users", {})
    user_state = _ensure_user_state(users.setdefault(normalized_user_id, _new_user_state()))
    vehicles = _normalized_vehicles(user_state)
    vehicle = _find_vehicle(vehicles, normalized_vehicle_id)
    if not vehicle:
        return {"ok": False, "error": "Vehicle not found"}

    existing_records = _normalize_maintenance_records(vehicle.get("maintenance_records"))
    next_records = [
        record
        for record in existing_records
        if str(record.get("id") or "").strip() != normalized_record_id
    ]
    if len(next_records) == len(existing_records):
        return {"ok": False, "error": "Maintenance record not found"}

    now = _current_timestamp()
    vehicle["maintenance"] = next_records[0] if next_records else {}
    vehicle["maintenance_records"] = next_records
    vehicle["updated_at"] = now
    user_state["vehicles"] = vehicles
    user_state["updated_at"] = now
    _write_payload(payload)

    return {
        "ok": True,
        "vehicle": vehicle,
        "record_id": normalized_record_id,
    }


def get_route_checkpoint_checkin_counts(slug: str | None, checkpoint_total: int | None = None) -> dict[int, int]:
    normalized_slug = str(slug or "").strip()
    normalized_total = _normalize_checkpoint_total(checkpoint_total)
    if not normalized_slug or normalized_total <= 0:
        return {}

    payload = _read_payload()
    users = payload.get("users") if isinstance(payload.get("users"), dict) else {}
    counts = {index: 0 for index in range(1, normalized_total + 1)}

    for raw_user_state in users.values():
        if not isinstance(raw_user_state, dict):
            continue

        collections = _normalized_route_checkpoint_collections(_ensure_user_state(raw_user_state))
        collection = collections.get(normalized_slug)
        if not isinstance(collection, dict):
            continue

        checked_indexes = {
            int(index)
            for index in collection.get("checked_indexes", [])
            if isinstance(index, int) and 1 <= int(index) <= normalized_total
        }
        for index in checked_indexes:
            counts[index] += 1

    return counts


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
    user_state = _ensure_user_state(users.setdefault(normalized_user_id, _new_user_state()))
    navigation_preferences = user_state.setdefault("navigation_preferences", {})
    if not isinstance(navigation_preferences, dict):
        navigation_preferences = {}
        user_state["navigation_preferences"] = navigation_preferences

    navigation_preferences["preferred_map_app"] = normalized_map_app
    user_state["updated_at"] = _current_timestamp()
    _write_payload(payload)

    return {
        "ok": True,
        "preferred_map_app": normalized_map_app,
    }


def _new_user_state() -> dict[str, Any]:
    now = _current_timestamp()
    return {
        "favorite_route_slugs": [],
        "checked_route_slugs": [],
        "want_go_plans": {},
        "want_go_records": [],
        "route_checkpoint_collections": {},
        "club_activity_signups": {},
        "vehicles": [],
        "profile": {},
        "navigation_preferences": {
            "preferred_map_app": "",
        },
        "created_at": now,
        "updated_at": now,
    }


def _normalize_want_go_plan_bucket(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in WANT_GO_PLAN_BUCKETS:
        return normalized
    return ""


def _normalized_want_go_plans(user_state: dict[str, Any]) -> dict[str, str]:
    details = _normalized_want_go_plan_details(user_state)
    return {slug: detail["bucket"] for slug, detail in details.items()}


def _normalized_want_go_plan_details(user_state: dict[str, Any]) -> dict[str, dict[str, str]]:
    raw = user_state.get("want_go_plans")
    if not isinstance(raw, dict):
        return {}

    plans: dict[str, dict[str, str]] = {}
    for slug, value in raw.items():
        normalized_slug = str(slug or "").strip()
        if not normalized_slug:
            continue

        bucket_value = value.get("bucket") if isinstance(value, dict) else value
        normalized_bucket = _normalize_want_go_plan_bucket(bucket_value)
        if not normalized_bucket:
            continue
        updated_at = str(value.get("updated_at") or "").strip() if isinstance(value, dict) else ""
        plans[normalized_slug] = {
            "bucket": normalized_bucket,
            "updated_at": updated_at,
        }
    return plans


def _normalized_want_go_records(user_state: dict[str, Any]) -> list[dict[str, str]]:
    raw_records = user_state.get("want_go_records")
    if not isinstance(raw_records, list):
        return []

    normalized: list[dict[str, str]] = []
    for raw_record in raw_records:
        if not isinstance(raw_record, dict):
            continue
        slug = str(raw_record.get("slug") or "").strip()
        bucket = _normalize_want_go_plan_bucket(raw_record.get("bucket"))
        if not slug or not bucket:
            continue
        selected_at = str(raw_record.get("selected_at") or raw_record.get("updated_at") or "").strip()
        archived_at = str(raw_record.get("archived_at") or "").strip()
        normalized.append(
            {
                "id": str(raw_record.get("id") or uuid.uuid4()).strip(),
                "slug": slug,
                "bucket": bucket,
                "selected_at": selected_at,
                "updated_at": selected_at,
                "archived_at": archived_at,
                "status": str(raw_record.get("status") or "archived").strip() or "archived",
            }
        )

    normalized.sort(
        key=lambda item: (
            str(item.get("selected_at") or item.get("updated_at") or ""),
            str(item.get("slug") or ""),
            str(item.get("id") or ""),
        ),
        reverse=True,
    )
    return normalized


def _assign_want_go_plans(user_state: dict[str, Any], plans: dict[str, str]) -> None:
    details = {
        slug: {
            "bucket": bucket,
            "updated_at": _current_timestamp(),
        }
        for slug, bucket in sorted(plans.items())
    }
    _assign_want_go_plan_details(user_state, details)


def _assign_want_go_plan_details(user_state: dict[str, Any], details: dict[str, dict[str, str]]) -> None:
    user_state["want_go_plans"] = {
        slug: {
            "bucket": str(detail.get("bucket") or "").strip(),
            "updated_at": str(detail.get("updated_at") or _current_timestamp()).strip() or _current_timestamp(),
        }
        for slug, detail in sorted(details.items())
        if str(slug or "").strip() and str(detail.get("bucket") or "").strip()
    }


def _read_user_state(user_id: str) -> dict[str, Any]:
    payload = _read_payload()
    users = payload.get("users") if isinstance(payload.get("users"), dict) else {}
    user_state = users.get(user_id)
    if not isinstance(user_state, dict):
        return _new_user_state()
    return _ensure_user_state(user_state)


def _ensure_user_state(user_state: dict[str, Any]) -> dict[str, Any]:
    created_at = str(user_state.get("created_at") or user_state.get("updated_at") or "").strip() or _current_timestamp()
    updated_at = str(user_state.get("updated_at") or created_at).strip() or created_at
    profile = user_state.get("profile") if isinstance(user_state.get("profile"), dict) else {}
    navigation_preferences = user_state.get("navigation_preferences") if isinstance(user_state.get("navigation_preferences"), dict) else {}
    user_state.setdefault("favorite_route_slugs", [])
    user_state.setdefault("checked_route_slugs", [])
    user_state.setdefault("want_go_plans", {})
    user_state.setdefault("want_go_records", [])
    user_state.setdefault("route_checkpoint_collections", {})
    user_state.setdefault("club_activity_signups", {})
    user_state.setdefault("vehicles", [])
    user_state["profile"] = _normalize_user_profile(profile) or {}
    user_state["want_go_records"] = _normalized_want_go_records(user_state)
    user_state["vehicles"] = _normalized_vehicles(user_state)
    user_state["navigation_preferences"] = {
        "preferred_map_app": str(navigation_preferences.get("preferred_map_app") or "").strip(),
    }
    user_state["created_at"] = created_at
    user_state["updated_at"] = updated_at
    return user_state


def _build_want_go_locked_message(bucket: str, updated_at: str) -> str:
    label_map = {
        "this_month": "这个月",
        "next_month": "下个月",
    }
    label = label_map.get(str(bucket or "").strip(), "当前周期")
    expiry_label = _format_want_go_expiry_label(bucket, updated_at)
    if expiry_label:
        return f"你已选择{label}，{expiry_label}后可重新选择"
    return f"你已选择{label}，当前周期内不可重复选择"


def _format_want_go_expiry_label(bucket: str, updated_at: str) -> str:
    expiry = _want_go_plan_expiry_start(bucket, updated_at)
    if expiry is None:
        return ""
    return expiry.strftime("%Y-%m-01")


def _want_go_plan_expiry_start(bucket: str, updated_at: str) -> datetime | None:
    selected_at = _parse_timestamp(updated_at)
    if selected_at is None:
        return None

    month_start = selected_at.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    normalized_bucket = str(bucket or "").strip()
    if normalized_bucket == "this_month":
        return _add_months(month_start, 1)
    if normalized_bucket == "next_month":
        return _add_months(month_start, 2)
    return None


def _is_want_go_plan_expired(bucket: str, updated_at: str, now: datetime | None = None) -> bool:
    expiry = _want_go_plan_expiry_start(bucket, updated_at)
    if expiry is None:
        return False
    return (now or datetime.now()) >= expiry


def _expire_user_state_want_go_plans(user_state: dict[str, Any]) -> bool:
    details = _normalized_want_go_plan_details(user_state)
    if not details:
        return False

    now = datetime.now()
    changed = False
    next_details: dict[str, dict[str, str]] = {}
    records = _normalized_want_go_records(user_state)
    for slug, detail in details.items():
        bucket = str(detail.get("bucket") or "").strip()
        updated_at = str(detail.get("updated_at") or "").strip()
        if bucket in ACTIVE_WANT_GO_PLAN_BUCKETS and _is_want_go_plan_expired(bucket, updated_at, now):
            record_id = f"archived:{slug}:{bucket}:{updated_at}"
            if not any(str(item.get("id") or "") == record_id for item in records):
                records.append(
                    {
                        "id": record_id,
                        "slug": slug,
                        "bucket": bucket,
                        "selected_at": updated_at,
                        "updated_at": updated_at,
                        "archived_at": now.isoformat(timespec="seconds"),
                        "status": "archived",
                    }
                )
            changed = True
            continue
        next_details[slug] = detail

    if not changed:
        return False

    _assign_want_go_plan_details(user_state, next_details)
    user_state["want_go_records"] = sorted(
        records,
        key=lambda item: (
            str(item.get("selected_at") or item.get("updated_at") or ""),
            str(item.get("slug") or ""),
            str(item.get("id") or ""),
        ),
        reverse=True,
    )
    user_state["updated_at"] = _current_timestamp()
    return True


def _parse_timestamp(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _add_months(value: datetime, month_count: int) -> datetime:
    year = value.year + ((value.month - 1 + month_count) // 12)
    month = ((value.month - 1 + month_count) % 12) + 1
    return value.replace(year=year, month=month)


def _empty_route_checkpoint_collection(slug: str, checkpoint_total: int) -> dict[str, Any]:
    total = _normalize_checkpoint_total(checkpoint_total)
    return {
        "slug": str(slug or "").strip(),
        "route_title": "",
        "checkpoint_total": total,
        "checked_indexes": [],
        "checked_count": 0,
        "completion_percent": 0,
        "is_completed": False,
        "badge": {},
        "has_badge": False,
        "updated_at": "",
    }


def _normalize_checkpoint_total(value: Any) -> int:
    try:
        normalized = int(value or 0)
    except (TypeError, ValueError):
        normalized = 0
    return max(0, normalized)


def _normalize_checkpoint_index(value: Any, checkpoint_total: int) -> int:
    try:
        normalized = int(value or 0)
    except (TypeError, ValueError):
        return 0
    if checkpoint_total > 0 and normalized > checkpoint_total:
        return 0
    return normalized if normalized > 0 else 0


def _normalized_route_checkpoint_collections(user_state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw = user_state.get("route_checkpoint_collections")
    if not isinstance(raw, dict):
        return {}

    collections: dict[str, dict[str, Any]] = {}
    for slug, raw_collection in raw.items():
        normalized_slug = str(slug or "").strip()
        if not normalized_slug or not isinstance(raw_collection, dict):
            continue

        total = _normalize_checkpoint_total(raw_collection.get("checkpoint_total"))
        checked_indexes = sorted({
            int(index)
            for index in raw_collection.get("checked_indexes", [])
            if isinstance(index, int) and int(index) > 0
        })
        if total > 0:
            checked_indexes = [index for index in checked_indexes if index <= total]

        badge = raw_collection.get("badge") if isinstance(raw_collection.get("badge"), dict) else {}
        collections[normalized_slug] = {
            "route_title": str(raw_collection.get("route_title") or "").strip(),
            "checkpoint_total": total,
            "checked_indexes": checked_indexes,
            "checked_count": len(checked_indexes),
            "badge": badge,
            "updated_at": str(raw_collection.get("updated_at") or "").strip(),
        }

    return collections


def _assign_route_checkpoint_collections(user_state: dict[str, Any], collections: dict[str, dict[str, Any]]) -> None:
    normalized: dict[str, dict[str, Any]] = {}
    for slug in sorted(collections.keys()):
        collection = collections.get(slug)
        if not isinstance(collection, dict):
            continue
        total = _normalize_checkpoint_total(collection.get("checkpoint_total"))
        checked_indexes = sorted({
            int(index)
            for index in collection.get("checked_indexes", [])
            if isinstance(index, int) and int(index) > 0
        })
        if total > 0:
            checked_indexes = [index for index in checked_indexes if index <= total]
        normalized[slug] = {
            "route_title": str(collection.get("route_title") or "").strip(),
            "checkpoint_total": total,
            "checked_indexes": checked_indexes,
            "badge": collection.get("badge") if isinstance(collection.get("badge"), dict) else {},
            "updated_at": str(collection.get("updated_at") or _current_timestamp()).strip() or _current_timestamp(),
        }
    user_state["route_checkpoint_collections"] = normalized


def _normalize_user_profile(profile: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(profile, dict):
        return {}

    nick_name = str(profile.get("nickName") or profile.get("nickname") or profile.get("name") or "").strip()
    avatar_url = str(profile.get("avatarUrl") or profile.get("avatar") or profile.get("headImgUrl") or "").strip()
    city = str(profile.get("city") or "").strip()
    province = str(profile.get("province") or "").strip()
    country = str(profile.get("country") or "").strip()
    gender = int(profile.get("gender") or 0)

    if not any([nick_name, avatar_url, city, province, country, gender]):
        return {}

    return {
        "nickName": nick_name,
        "avatarUrl": avatar_url,
        "city": city,
        "province": province,
        "country": country,
        "gender": gender,
    }


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _find_vehicle(vehicles: list[dict[str, Any]], vehicle_id: str) -> dict[str, Any] | None:
    for vehicle in vehicles:
        if str(vehicle.get("id") or "").strip() == vehicle_id:
            return vehicle
    return None


def _normalize_vehicle_payload(vehicle_payload: dict[str, Any] | None, *, existing: dict[str, Any] | None) -> dict[str, Any]:
    source = vehicle_payload if isinstance(vehicle_payload, dict) else {}
    fallback = existing if isinstance(existing, dict) else {}
    fallback_records = _normalize_maintenance_records(fallback.get("maintenance_records"))
    source_records = _normalize_maintenance_records(source.get("maintenance_records")) if isinstance(source.get("maintenance_records"), list) else []
    has_flat_maintenance_input = any(
        source.get(key) is not None
        for key in [
            "maintenance_id",
            "maintenance_date",
            "maintenance_item",
            "maintenance_location",
            "maintenance_mileage_km",
            "maintenance_cost",
            "maintenance_note",
        ]
    )
    fallback_maintenance = fallback.get("maintenance") if isinstance(fallback.get("maintenance"), dict) else {}
    maintenance_source = {
        "id": source.get("maintenance_id") or source.get("id") or fallback_maintenance.get("id") or "",
        "date": source.get("maintenance_date") if source.get("maintenance_date") is not None else source.get("date"),
        "item": source.get("maintenance_item") if source.get("maintenance_item") is not None else source.get("item"),
        "location": source.get("maintenance_location") if source.get("maintenance_location") is not None else source.get("location"),
        "mileage_km": source.get("maintenance_mileage_km") if source.get("maintenance_mileage_km") is not None else source.get("mileage_km"),
        "cost": source.get("maintenance_cost") if source.get("maintenance_cost") is not None else source.get("cost"),
        "note": source.get("maintenance_note") if source.get("maintenance_note") is not None else source.get("note"),
    }
    if source_records:
        maintenance_records = source_records
    elif has_flat_maintenance_input or isinstance(source.get("maintenance"), dict):
        normalized_maintenance = _normalize_vehicle_maintenance(maintenance_source, source.get("maintenance"))
        maintenance_records = [normalized_maintenance] if normalized_maintenance else []
    else:
        maintenance_records = fallback_records

    maintenance = _normalize_vehicle_maintenance(source.get("maintenance"), maintenance_records, fallback.get("maintenance"), fallback_records)
    if maintenance and not maintenance_records:
        maintenance_records = [maintenance]
    return {
        "nickname": str(source.get("nickname") if source.get("nickname") is not None else fallback.get("nickname") or "").strip(),
        "brand": str(source.get("brand") if source.get("brand") is not None else fallback.get("brand") or "").strip(),
        "model": str(source.get("model") if source.get("model") is not None else fallback.get("model") or "").strip(),
        "year": str(source.get("year") if source.get("year") is not None else fallback.get("year") or "").strip()[:8],
        "plate_no": str(source.get("plate_no") if source.get("plate_no") is not None else fallback.get("plate_no") or "").strip()[:32],
        "purchase_date": str(source.get("purchase_date") if source.get("purchase_date") is not None else fallback.get("purchase_date") or "").strip()[:20],
        "note": str(source.get("note") if source.get("note") is not None else fallback.get("note") or "").strip()[:500],
        "maintenance": maintenance,
        "maintenance_records": maintenance_records,
    }


def _normalize_maintenance_record(record_payload: dict[str, Any] | None, *, existing: dict[str, Any] | None) -> dict[str, Any]:
    source = record_payload if isinstance(record_payload, dict) else {}
    fallback = existing if isinstance(existing, dict) else {}
    return {
        "date": str(source.get("date") if source.get("date") is not None else fallback.get("date") or "").strip()[:20],
        "item": str(source.get("item") if source.get("item") is not None else fallback.get("item") or "").strip()[:120],
        "location": str(source.get("location") if source.get("location") is not None else fallback.get("location") or "").strip()[:160],
        "mileage_km": str(source.get("mileage_km") if source.get("mileage_km") is not None else fallback.get("mileage_km") or "").strip()[:16],
        "cost": str(source.get("cost") if source.get("cost") is not None else fallback.get("cost") or "").strip()[:32],
        "note": str(source.get("note") if source.get("note") is not None else fallback.get("note") or "").strip()[:500],
    }


def _normalize_maintenance_records(records: Any) -> list[dict[str, Any]]:
    source = records if isinstance(records, list) else []
    normalized: list[dict[str, Any]] = []
    for raw_item in source:
        if not isinstance(raw_item, dict):
            continue
        normalized_item = _normalize_maintenance_record(raw_item, existing=None)
        record_id = str(raw_item.get("id") or "").strip() or _new_id("mt")
        if not normalized_item.get("item"):
            continue
        normalized.append(
            {
                "id": record_id,
                "date": normalized_item["date"],
                "item": normalized_item["item"],
                "location": normalized_item["location"],
                "mileage_km": normalized_item["mileage_km"],
                "cost": normalized_item["cost"],
                "note": normalized_item["note"],
                "created_at": str(raw_item.get("created_at") or raw_item.get("updated_at") or "").strip(),
                "updated_at": str(raw_item.get("updated_at") or raw_item.get("created_at") or "").strip(),
            }
        )
    normalized.sort(key=lambda item: (str(item.get("date") or ""), str(item.get("created_at") or "")), reverse=True)
    return normalized


def _normalize_vehicle_maintenance(*candidates: Any) -> dict[str, Any]:
    for candidate in candidates:
        if isinstance(candidate, dict):
            normalized = _normalize_maintenance_record(candidate, existing=None)
            if normalized.get("item") or normalized.get("date") or normalized.get("mileage_km") or normalized.get("note"):
                return {
                    "id": str(candidate.get("id") or "").strip(),
                    "date": normalized["date"],
                    "item": normalized["item"],
                    "location": normalized["location"],
                    "mileage_km": normalized["mileage_km"],
                    "cost": normalized["cost"],
                    "note": normalized["note"],
                    "created_at": str(candidate.get("created_at") or candidate.get("updated_at") or "").strip(),
                    "updated_at": str(candidate.get("updated_at") or candidate.get("created_at") or "").strip(),
                }
        if isinstance(candidate, list) and candidate:
            first_record = _normalize_maintenance_records(candidate)[:1]
            if first_record:
                record = first_record[0]
                return {**record}
    return {}


def _normalized_vehicles(user_state: dict[str, Any]) -> list[dict[str, Any]]:
    raw = user_state.get("vehicles")
    source = raw if isinstance(raw, list) else []
    normalized: list[dict[str, Any]] = []
    for raw_vehicle in source:
        if not isinstance(raw_vehicle, dict):
            continue
        normalized_vehicle = _normalize_vehicle_payload(raw_vehicle, existing=None)
        vehicle_id = str(raw_vehicle.get("id") or "").strip() or _new_id("veh")
        maintenance_records = _normalize_maintenance_records(raw_vehicle.get("maintenance_records"))
        maintenance = _normalize_vehicle_maintenance(raw_vehicle.get("maintenance"), maintenance_records)
        if maintenance and not maintenance_records:
            maintenance_records = [maintenance]
        normalized.append(
            {
                "id": vehicle_id,
                "nickname": normalized_vehicle["nickname"],
                "brand": normalized_vehicle["brand"],
                "model": normalized_vehicle["model"],
                "year": normalized_vehicle["year"],
                "plate_no": normalized_vehicle["plate_no"],
                "purchase_date": normalized_vehicle["purchase_date"],
                "note": normalized_vehicle["note"],
                "maintenance": maintenance,
                "maintenance_records": maintenance_records,
                "created_at": str(raw_vehicle.get("created_at") or raw_vehicle.get("updated_at") or "").strip(),
                "updated_at": str(raw_vehicle.get("updated_at") or raw_vehicle.get("created_at") or "").strip(),
            }
        )

    normalized.sort(
        key=lambda item: (
            str(item.get("updated_at") or ""),
            str(item.get("created_at") or ""),
            str(item.get("id") or ""),
        ),
        reverse=True,
    )
    return normalized


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
