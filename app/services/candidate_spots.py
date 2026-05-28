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
LOCAL_VIDEO_ROOT = PROJECT_ROOT / "data" / "raw" / "douyin_videos"


def get_candidate_spots() -> list[CandidateDict]:
    if not CANDIDATE_SPOTS_PATH.exists():
        return []
    data = json.loads(CANDIDATE_SPOTS_PATH.read_text(encoding="utf-8"))
    candidates = data if isinstance(data, list) else []
    return [_decorate_candidate(candidate) for candidate in candidates]


def get_reviewed_spots() -> dict[str, list[CandidateDict]]:
    return {
        "approved": _decorate_reviewed_items(_read_json_list(APPROVED_SPOTS_PATH), "approved"),
        "rejected": _decorate_reviewed_items(_read_json_list(REJECTED_SPOTS_PATH), "rejected"),
    }


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


def delete_reviewed_spots(selected_keys: list[str]) -> dict[str, int]:
    approved_items = _read_json_list(APPROVED_SPOTS_PATH)
    rejected_items = _read_json_list(REJECTED_SPOTS_PATH)

    approved_key_set = {
        _reviewed_item_key("approved", index, item)
        for index, item in enumerate(approved_items)
        if _reviewed_item_key("approved", index, item) in selected_keys
    }
    rejected_key_set = {
        _reviewed_item_key("rejected", index, item)
        for index, item in enumerate(rejected_items)
        if _reviewed_item_key("rejected", index, item) in selected_keys
    }

    remaining_approved = [
        item
        for index, item in enumerate(approved_items)
        if _reviewed_item_key("approved", index, item) not in approved_key_set
    ]
    remaining_rejected = [
        item
        for index, item in enumerate(rejected_items)
        if _reviewed_item_key("rejected", index, item) not in rejected_key_set
    ]

    _write_json_list(APPROVED_SPOTS_PATH, remaining_approved)
    _write_json_list(REJECTED_SPOTS_PATH, remaining_rejected)
    return {
        "deleted": len(approved_key_set) + len(rejected_key_set),
        "approved_deleted": len(approved_key_set),
        "rejected_deleted": len(rejected_key_set),
    }


def clear_spot_review_data() -> dict[str, int]:
    candidate_count = len(_read_json_list(CANDIDATE_SPOTS_PATH))
    approved_count = len(_read_json_list(APPROVED_SPOTS_PATH))
    rejected_count = len(_read_json_list(REJECTED_SPOTS_PATH))

    _write_json_list(CANDIDATE_SPOTS_PATH, [])
    _write_json_list(APPROVED_SPOTS_PATH, [])
    _write_json_list(REJECTED_SPOTS_PATH, [])

    return {
        "candidates": candidate_count,
        "approved": approved_count,
        "rejected": rejected_count,
        "total": candidate_count + approved_count + rejected_count,
    }


def candidate_to_collection_record(candidate: CandidateDict, apply_video_analysis: bool = False) -> CandidateDict:
    template = get_empty_moto_spot_record()
    record = {
        key: value.copy() if isinstance(value, dict | list) else value
        for key, value in template.items()
    }
    for key, value in candidate.items():
        if key in record:
            record[key] = value.copy() if isinstance(value, dict | list) else value
    if apply_video_analysis:
        return _apply_candidate_fixed_spot_info(record, candidate)
    return record


def build_candidate_review_media(candidate: CandidateDict | None) -> dict[str, Any]:
    source = candidate if isinstance(candidate, dict) else {}
    video_analysis = _normalize_video_analysis(source.get("video_analysis") or source.get("videoAnalysis") or {})
    fixed_spot_info = _normalize_fixed_spot_info(source.get("fixed_spot_info") or source.get("fixedSpotInfo") or {})
    keyframe_paths = _normalize_string_list(source.get("keyframe_paths") or source.get("keyframePaths"))
    candidate_slug = str(source.get("slug") or "candidate")
    keyframes = [
        {
            "path": item,
            "label": f"关键帧 {index + 1}",
            "href": f"/moto/spots/collect/keyframes/{item.replace('data/raw/openclaw_keyframes/', '', 1)}",
        }
        for index, item in enumerate(keyframe_paths)
    ]
    return {
        "video_url": str(source.get("video_url") or source.get("videoUrl") or "").strip(),
        "local_video_path": str(source.get("local_video_path") or source.get("localVideoPath") or "").strip(),
        "local_video_href": _local_video_href(str(source.get("local_video_path") or source.get("localVideoPath") or "").strip()),
        "keyframes": keyframes,
        "video_analysis": video_analysis,
        "fixed_spot_info": fixed_spot_info,
        "review_hints": _candidate_review_hints(candidate_slug, fixed_spot_info, video_analysis),
    }


def _local_video_href(value: str) -> str:
    path = str(value or "").strip()
    if not path:
        return ""
    try:
        relative = (PROJECT_ROOT / path).resolve().relative_to(LOCAL_VIDEO_ROOT.resolve())
    except ValueError:
        normalized = path.replace("data/raw/douyin_videos/", "", 1).lstrip("/")
        return f"/moto/spots/collect/videos/{normalized}" if normalized else ""
    return f"/moto/spots/collect/videos/{relative.as_posix()}"


def _decorate_candidate(candidate: CandidateDict) -> CandidateDict:
    decorated = {
        key: value.copy() if isinstance(value, dict | list) else value
        for key, value in candidate.items()
    }
    decorated["review_href"] = f"/moto/spots/collect?candidate={decorated['slug']}"
    decorated["source_count"] = len(decorated.get("sources", []))
    return decorated


def _apply_candidate_fixed_spot_info(record: CandidateDict, candidate: CandidateDict) -> CandidateDict:
    fixed_spot_info = _normalize_fixed_spot_info(candidate.get("fixed_spot_info") or candidate.get("fixedSpotInfo") or {})
    video_analysis = _normalize_video_analysis(candidate.get("video_analysis") or candidate.get("videoAnalysis") or {})

    if fixed_spot_info["city"]:
        record["city"] = fixed_spot_info["city"]
    if fixed_spot_info["region"]:
        record["region"] = fixed_spot_info["region"]
    if fixed_spot_info["poiType"]:
        record["spot_type"] = fixed_spot_info["poiType"]
    if fixed_spot_info["routeType"]:
        record["route_type"] = fixed_spot_info["routeType"]
    if fixed_spot_info["summary"]:
        record["summary"] = fixed_spot_info["summary"]
    if not record.get("support_role"):
        record["support_role"] = fixed_spot_info["supportTags"].copy()
    else:
        record["support_role"] = _merge_unique(record.get("support_role"), fixed_spot_info["supportTags"])
    if not record.get("spot_markers"):
        record["spot_markers"] = fixed_spot_info["spotMarkers"].copy()
    else:
        record["spot_markers"] = _merge_unique(record.get("spot_markers"), fixed_spot_info["spotMarkers"])
    if not record.get("photo_focus"):
        record["photo_focus"] = fixed_spot_info["photoTags"].copy()
    record["photo_focus"] = _merge_unique(record.get("photo_focus"), video_analysis.get("sceneLabels"))
    record["photo_focus"] = _merge_unique(record.get("photo_focus"), video_analysis.get("captions"))
    record["route_tags"] = _merge_unique(record.get("route_tags"), video_analysis.get("routeHints"))
    return record


def _normalize_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if value in (None, ""):
        return []
    return [str(value).strip()]


def _normalize_video_analysis(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {
            "transcript": "",
            "ocrText": "",
            "summary": "",
            "sceneSummary": "",
            "keywords": [],
            "sceneLabels": [],
            "placeHints": [],
            "supportHints": [],
            "routeHints": [],
            "spotMarkers": [],
            "captions": [],
        }
    return {
        "transcript": str(value.get("transcript") or "").strip(),
        "ocrText": str(value.get("ocrText") or value.get("ocr_text") or "").strip(),
        "summary": str(value.get("summary") or "").strip(),
        "sceneSummary": str(value.get("sceneSummary") or value.get("scene_summary") or "").strip(),
        "keywords": _normalize_string_list(value.get("keywords")),
        "sceneLabels": _normalize_string_list(value.get("sceneLabels") or value.get("scene_labels")),
        "placeHints": _normalize_string_list(value.get("placeHints") or value.get("place_hints")),
        "supportHints": _normalize_string_list(value.get("supportHints") or value.get("support_hints")),
        "routeHints": _normalize_string_list(value.get("routeHints") or value.get("route_hints")),
        "spotMarkers": _normalize_string_list(value.get("spotMarkers") or value.get("spot_markers")),
        "captions": _normalize_string_list(value.get("captions")),
    }


def _normalize_fixed_spot_info(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {
            "city": "",
            "region": "",
            "poiType": "",
            "routeType": "",
            "supportTags": [],
            "spotMarkers": [],
            "photoTags": [],
            "summary": "",
        }
    return {
        "city": str(value.get("city") or "").strip(),
        "region": str(value.get("region") or "").strip(),
        "poiType": str(value.get("poiType") or value.get("poi_type") or "").strip(),
        "routeType": str(value.get("routeType") or value.get("route_type") or "").strip(),
        "supportTags": _normalize_string_list(value.get("supportTags") or value.get("support_tags")),
        "spotMarkers": _normalize_string_list(value.get("spotMarkers") or value.get("spot_markers")),
        "photoTags": _normalize_string_list(value.get("photoTags") or value.get("photo_tags")),
        "summary": str(value.get("summary") or "").strip(),
    }


def _merge_unique(left: Any, right: Any) -> list[str]:
    merged: list[str] = []
    for value in [*_normalize_string_list(left), *_normalize_string_list(right)]:
        if value and value not in merged:
            merged.append(value)
    return merged


def _candidate_review_hints(slug: str, fixed_spot_info: dict[str, Any], video_analysis: dict[str, Any]) -> list[str]:
    hints: list[str] = []
    if fixed_spot_info["city"] and fixed_spot_info["region"]:
        hints.append(f"视频推断位置：{fixed_spot_info['city']} · {fixed_spot_info['region']}")
    if fixed_spot_info["poiType"] or fixed_spot_info["routeType"]:
        hints.append(f"视频推断类型：{fixed_spot_info['poiType'] or '未识别'} / {fixed_spot_info['routeType'] or '未识别'}")
    if fixed_spot_info["supportTags"]:
        hints.append(f"视频推断支撑：{'、'.join(fixed_spot_info['supportTags'])}")
    if fixed_spot_info["spotMarkers"]:
        hints.append(f"视频推断标记：{'、'.join(fixed_spot_info['spotMarkers'])}")
    if video_analysis["placeHints"]:
        hints.append(f"地点线索：{'、'.join(video_analysis['placeHints'])}")
    if video_analysis["routeHints"]:
        hints.append(f"路线线索：{'、'.join(video_analysis['routeHints'])}")
    if video_analysis["summary"]:
        hints.append(f"视频摘要：{video_analysis['summary']}")
    if video_analysis["transcript"]:
        hints.append(f"转写片段：{video_analysis['transcript'][:80]}{'…' if len(video_analysis['transcript']) > 80 else ''}")
    if not hints:
        hints.append(f"候选 {slug} 当前没有可展示的视频分析结果。")
    return hints


def _decorate_reviewed_items(items: list[CandidateDict], status: str) -> list[CandidateDict]:
    decorated: list[CandidateDict] = []
    for index, item in enumerate(items):
        reviewed = {
            key: value.copy() if isinstance(value, dict | list) else value
            for key, value in item.items()
        }
        reviewed["status"] = status
        reviewed["status_label"] = "已批准" if status == "approved" else "已拒绝"
        reviewed["item_key"] = _reviewed_item_key(status, index, item)
        reviewed["source_count"] = len(reviewed.get("sources", []))
        decorated.append(reviewed)
    return decorated


def _reviewed_item_key(status: str, index: int, item: CandidateDict) -> str:
    return f"{status}:{index}:{item.get('slug', '')}"


def _read_json_list(path: Path) -> list[CandidateDict]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else []


def _write_json_list(path: Path, items: list[CandidateDict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
