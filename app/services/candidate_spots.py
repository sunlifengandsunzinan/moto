from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from .liaoning_spots import get_empty_moto_spot_record


CandidateDict = dict[str, Any]
PROJECT_ROOT = Path(__file__).resolve().parents[2]
CANDIDATE_SPOTS_PATH = PROJECT_ROOT / "data" / "normalized" / "candidate_spots.json"
APPROVED_SPOTS_PATH = PROJECT_ROOT / "data" / "reviewed" / "approved_spots.json"
REJECTED_SPOTS_PATH = PROJECT_ROOT / "data" / "reviewed" / "rejected_spots.json"


def get_candidate_spots() -> list[CandidateDict]:
    if not CANDIDATE_SPOTS_PATH.exists():
        return []
    data = json.loads(CANDIDATE_SPOTS_PATH.read_text(encoding="utf-8"))
    candidates = data if isinstance(data, list) else []
    return [_decorate_candidate(candidate) for candidate in candidates]


def get_candidate_spot_by_slug(slug: str) -> CandidateDict | None:
    candidate = next((item for item in get_candidate_spots() if item.get("slug") == slug), None)
    return candidate.copy() if candidate is not None else None


def review_candidate_spot(slug: str, decision: str) -> dict[str, str] | None:
    candidates = _read_json_list(CANDIDATE_SPOTS_PATH)
    candidate = next((item for item in candidates if item.get("slug") == slug), None)
    if candidate is None or decision not in {"approve", "reject"}:
        return None

    remaining = [item for item in candidates if item.get("slug") != slug]
    _write_json_list(CANDIDATE_SPOTS_PATH, remaining)

    reviewed_record = {
        **candidate,
        "review_status": "approved" if decision == "approve" else "rejected",
        "reviewed_at": date.today().isoformat(),
    }
    target_path = APPROVED_SPOTS_PATH if decision == "approve" else REJECTED_SPOTS_PATH
    reviewed_items = _read_json_list(target_path)
    reviewed_items.append(reviewed_record)
    _write_json_list(target_path, reviewed_items)

    next_slug = remaining[0].get("slug", "") if remaining else ""
    return {
        "slug": slug,
        "decision": decision,
        "next_slug": next_slug,
        "name": str(candidate.get("name", slug)),
    }


def candidate_to_collection_record(candidate: CandidateDict) -> CandidateDict:
    template = get_empty_moto_spot_record()
    record = {
        key: value.copy() if isinstance(value, dict | list) else value
        for key, value in template.items()
    }
    for key, value in candidate.items():
        if key in record:
            record[key] = value.copy() if isinstance(value, dict | list) else value
    return record


def _decorate_candidate(candidate: CandidateDict) -> CandidateDict:
    decorated = {
        key: value.copy() if isinstance(value, dict | list) else value
        for key, value in candidate.items()
    }
    decorated["review_href"] = f"/moto/spots/collect?candidate={decorated['slug']}"
    decorated["source_count"] = len(decorated.get("sources", []))
    return decorated


def _read_json_list(path: Path) -> list[CandidateDict]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else []


def _write_json_list(path: Path, items: list[CandidateDict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
