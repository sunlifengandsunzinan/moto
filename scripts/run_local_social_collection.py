from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.run_candidate_pipeline import main as run_candidate_pipeline_main
from scripts.adapt_openclaw_candidates import adapt_openclaw_candidate
from scripts.normalize_candidate_spots import NORMALIZED_PATH as CANDIDATE_QUEUE_PATH
from scripts.normalize_candidate_spots import normalize_raw_candidate

DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "data" / "raw" / "openclaw_export.json"
DEFAULT_STATUS_PATH = PROJECT_ROOT / "data" / "raw" / "local_collection_status.json"
DEFAULT_RAW_CANDIDATES_PATH = PROJECT_ROOT / "data" / "raw" / "local_collector_candidates.json"
DEFAULT_SOURCE_PATHS = [PROJECT_ROOT / "data" / "raw" / "openclaw_export.example.json"]

TASK_SPEC = {
    "name": "liaoning-local-social-collector",
    "province": "辽宁省",
    "platforms": ["douyin", "xiaohongshu"],
    "platform_priority": ["xiaohongshu", "douyin"],
    "keywords": [
        "辽宁 摩旅",
        "辽宁 摩托 驿站",
        "沈阳 骑士 驿站",
        "本溪 本桓公路 摩旅",
        "桓仁 摩旅 补给",
        "丹东 绿江村 摩旅",
        "丹东 鸭绿江 摩旅",
        "宽甸 青山沟 摩旅",
        "大连 滨海路 摩旅",
        "旅顺 沿海 摩旅",
        "盘锦 红海滩 摩旅",
        "兴城 海滨 摩旅",
    ],
    "social_keywords": ["机车合影", "骑行照片", "实拍", "路书", "打卡", "骑士驿站", "补给", "观景", "夜景"],
    "max_items_per_keyword": 20,
}

AI_IMAGE_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"(^|[^a-z])ai([^a-z]|$)",
        r"aigc",
        r"midjourney",
        r"stable[\s-]?diffusion",
        r"flux",
        r"comfyui",
        r"generated",
        r"synthetic",
        r"dreamina",
        r"即梦",
        r"豆包ai",
        r"文生图",
        r"图生图",
    ]
]

SOCIAL_SOURCE_PATTERNS = {
    "douyin": [re.compile(r"douyin\.com", re.IGNORECASE), re.compile(r"iesdouyin\.com", re.IGNORECASE)],
    "xiaohongshu": [re.compile(r"xiaohongshu\.com", re.IGNORECASE), re.compile(r"xhslink\.com", re.IGNORECASE)],
}

REGION_MAP = {
    "沈阳": "辽中",
    "辽阳": "辽中",
    "铁岭": "辽中",
    "抚顺": "辽中",
    "盘锦": "辽南",
    "营口": "辽南",
    "大连": "辽南",
    "葫芦岛": "辽南",
    "锦州": "辽南",
    "朝阳": "辽南",
    "本溪": "辽东",
    "丹东": "辽东",
    "宽甸": "辽东",
    "桓仁": "辽东",
}

PLACE_GENERIC_TOKENS = [
    "辽宁",
    "摩旅",
    "摩托",
    "机车",
    "骑士",
    "驿站",
    "集合点",
    "集合",
    "打卡点",
    "打卡",
    "停靠点",
    "停靠位",
    "停靠",
    "观景台",
    "观景点",
    "观景",
    "咖啡站",
    "咖啡",
    "加油站",
    "油站",
    "补给点",
    "补给",
    "服务点",
    "服务站",
    "骑行",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Liaoning social collector locally without OpenClaw runtime.")
    parser.add_argument("--source", action="append", dest="sources", help="Wrapped JSON source file(s) used as local collection feed.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="Wrapped export output path.")
    parser.add_argument("--status", default=str(DEFAULT_STATUS_PATH), help="Collector heartbeat/status file path.")
    parser.add_argument("--raw-candidates-output", default=str(DEFAULT_RAW_CANDIDATES_PATH), help="Raw candidate output path used to feed the pending-review queue.")
    parser.add_argument("--continuous", action="store_true", help="Keep collecting continuously until the process is stopped.")
    parser.add_argument("--max-items", type=int, default=TASK_SPEC["max_items_per_keyword"], help="Per-task result cap.")
    parser.add_argument("--skip-pipeline", action="store_true", help="Skip adapt + normalize pipeline after each collection cycle.")
    return parser.parse_args()


def read_json_file(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def unwrap_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("items"), list):
        source = payload["items"]
    elif isinstance(payload, list):
        source = payload
    else:
        source = []
    return [item for item in source if isinstance(item, dict)]


def dedupe_strings(values: Iterable[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def dedupe_mixed(values: Iterable[Any]) -> list[Any]:
    seen: set[str] = set()
    result: list[Any] = []
    for value in values:
        if value in (None, ""):
            continue
        key = value.strip() if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def extract_text(item: Any, keys: list[str]) -> str:
    if not isinstance(item, dict):
        return ""
    for key in keys:
        value = item.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def normalize_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return dedupe_strings(value)
    if value in (None, ""):
        return []
    return dedupe_strings([value])


def normalize_comment_entry(comment: Any) -> str | dict[str, Any] | None:
    if isinstance(comment, str):
        text = comment.strip()
        return text or None
    if not isinstance(comment, dict):
        return None
    text = extract_text(comment, ["text", "content", "comment", "body", "desc"])
    author = extract_text(comment, ["author", "userName", "nickname", "user", "name"])
    location = extract_text(comment, ["location", "place", "poiName", "city", "region"])
    if not text and not location:
        return None
    normalized = dict(comment)
    if text:
        normalized["text"] = text
    if author:
        normalized["author"] = author
    if location:
        normalized["location"] = location
    return normalized


def append_comment_value(value: Any, result: list[Any]) -> None:
    if value in (None, ""):
        return
    if isinstance(value, list):
        for item in value:
            append_comment_value(item, result)
        return
    normalized = normalize_comment_entry(value)
    if normalized is not None:
        result.append(normalized)


def extract_comments(item: dict[str, Any]) -> list[Any]:
    result: list[Any] = []
    comment_keys = [
        "comments",
        "commentList",
        "comment_list",
        "topComments",
        "top_comments",
        "hotComments",
        "hot_comments",
        "replies",
        "replyList",
        "reply_list",
    ]
    for key in comment_keys:
        append_comment_value(item.get(key), result)
    for container_key in ["content", "detail", "detailInfo", "detail_info", "note", "post", "aweme", "data", "metadata"]:
        container = item.get(container_key)
        if not isinstance(container, dict):
            continue
        for key in comment_keys:
            append_comment_value(container.get(key), result)
    return dedupe_mixed(result)


def extract_comment_text(comment: Any) -> str:
    if isinstance(comment, str):
        return comment.strip()
    if not isinstance(comment, dict):
        return ""
    return extract_text(comment, ["text", "content", "comment", "body", "desc"])


def infer_locations_from_comments(comments: list[Any]) -> list[str]:
    hints: list[str] = []
    for comment in comments:
        location_text = extract_text(comment, ["location", "place", "poiName", "city", "region"]) if isinstance(comment, dict) else ""
        text = f"{extract_comment_text(comment)} {location_text}".strip()
        if not text:
            continue
        for city in REGION_MAP:
            if city in text and city not in hints:
                hints.append(city)
    return hints


def flatten_video_analysis_text(video_analysis: Any) -> list[str]:
    if not isinstance(video_analysis, dict):
        return []
    values: list[str] = []
    for key in ["transcript", "ocrText", "summary", "sceneSummary"]:
        text = str(video_analysis.get(key) or "").strip()
        if text:
            values.append(text)
    for key in ["keywords", "sceneLabels", "placeHints", "supportHints", "routeHints", "spotMarkers", "captions"]:
        values.extend(normalize_string_list(video_analysis.get(key)))
    return dedupe_strings(values)


def collect_text(item: dict[str, Any]) -> str:
    values = [
        extract_text(item, ["title", "name", "poiName", "note_title"]),
        extract_text(item, ["summary", "description", "excerpt", "content"]),
        extract_text(item, ["author", "creator", "owner", "userName", "nickname"]),
        extract_text(item, ["city", "cityName"]),
        extract_text(item, ["region", "regionName"]),
        extract_text(item, ["routeType", "route_type"]),
        extract_text(item, ["poiType", "poi_type", "category"]),
    ]
    for key in ["tags", "labels", "keywords", "contentTags", "photoTags", "supportTags", "spotMarkers", "commentLocationHints"]:
        values.extend(normalize_string_list(item.get(key)))
    for comment in extract_comments(item):
        values.append(extract_comment_text(comment))
        if isinstance(comment, dict):
            values.append(extract_text(comment, ["location", "place", "poiName", "city", "region"]))
    values.extend(flatten_video_analysis_text(item.get("videoAnalysis") or item.get("video_analysis") or {}))
    fixed_info = item.get("fixedSpotInfo") or item.get("fixed_spot_info") or {}
    if isinstance(fixed_info, dict):
        for key in ["city", "region", "poiType", "routeType", "summary"]:
            values.append(str(fixed_info.get(key) or ""))
        for key in ["supportTags", "spotMarkers", "photoTags"]:
            values.extend(normalize_string_list(fixed_info.get(key)))
    return re.sub(r"\s+", " ", " ".join(value for value in values if value).strip())


def tokenize_keyword(keyword: str) -> list[str]:
    return [token.strip().lower() for token in re.split(r"\s+", keyword) if token.strip()]


def collect_image_urls(item: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ["imageUrls", "image_urls", "images", "photos", "covers", "thumbnails"]:
        values.extend(normalize_string_list(item.get(key)))
    return dedupe_strings(values)


def is_likely_real_image_url(url: str) -> bool:
    text = str(url or "").strip()
    if not text or text.startswith("data:"):
        return False
    if any(pattern.search(text) for pattern in AI_IMAGE_PATTERNS):
        return False
    return bool(re.search(r"\.(jpg|jpeg|png|webp|gif)(\?|#|$)", text, re.IGNORECASE) or re.search(r"[?&](format|image|img|photo|cover|x-oss-process)=", text, re.IGNORECASE))


def validate_real_image_urls(item: dict[str, Any]) -> list[str]:
    return [url for url in collect_image_urls(item) if is_likely_real_image_url(url)]


def is_preferred_social_source(platform: str, item: dict[str, Any]) -> bool:
    source_url = extract_text(item, ["sourceUrl", "source_url", "url", "link", "permalink", "noteUrl", "videoUrl"])
    patterns = SOCIAL_SOURCE_PATTERNS.get(platform, [])
    return bool(source_url) and any(pattern.search(source_url) for pattern in patterns)


def is_ai_generated_item(item: dict[str, Any]) -> bool:
    if item.get("aiGenerated") is True or item.get("generatedByAI") is True or item.get("aigc") is True:
        return True
    text = collect_text(item)
    return any(pattern.search(text) for pattern in AI_IMAGE_PATTERNS)


def canonical_place_name(value: str) -> str:
    text = re.sub(r"\s+", "", str(value or "").strip().lower())
    for token in PLACE_GENERIC_TOKENS:
        text = text.replace(token.lower(), "")
    return re.sub(r"[^a-z0-9\u4e00-\u9fa5]", "", text)


def place_name_similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    left_set = set(left)
    right_set = set(right)
    shared = len(left_set & right_set)
    union = len(left_set | right_set) or 1
    return shared / union


def is_same_collected_place(left: dict[str, Any], right: dict[str, Any]) -> bool:
    if left.get("sourceUrl") and left.get("sourceUrl") == right.get("sourceUrl"):
        return True
    if (left.get("location") or {}).get("city", "") != (right.get("location") or {}).get("city", ""):
        return False
    left_name = canonical_place_name(left.get("name", ""))
    right_name = canonical_place_name(right.get("name", ""))
    if left_name and right_name and left_name == right_name:
        return True
    return left_name and right_name and place_name_similarity(left_name, right_name) >= 0.6


def merge_string_lists(primary: Any, incoming: Any) -> list[str]:
    return dedupe_strings([*normalize_string_list(primary), *normalize_string_list(incoming)])


def merge_items(primary: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged_location = {
        "city": (primary.get("location") or {}).get("city") or (incoming.get("location") or {}).get("city") or "",
        "region": (primary.get("location") or {}).get("region") or (incoming.get("location") or {}).get("region") or "",
        "latitude": (primary.get("location") or {}).get("latitude") if (primary.get("location") or {}).get("latitude") is not None else (incoming.get("location") or {}).get("latitude"),
        "longitude": (primary.get("location") or {}).get("longitude") if (primary.get("location") or {}).get("longitude") is not None else (incoming.get("location") or {}).get("longitude"),
    }
    return {
        **primary,
        "name": incoming.get("name") if len(str(incoming.get("name") or "")) > len(str(primary.get("name") or "")) else primary.get("name", ""),
        "excerpt": incoming.get("excerpt") if len(str(incoming.get("excerpt") or "")) > len(str(primary.get("excerpt") or "")) else primary.get("excerpt", ""),
        "location": merged_location,
        "keywords": merge_string_lists(primary.get("keywords"), incoming.get("keywords")),
        "imageUrls": merge_string_lists(primary.get("imageUrls"), incoming.get("imageUrls")),
        "supportTags": merge_string_lists(primary.get("supportTags"), incoming.get("supportTags")),
        "photoTags": merge_string_lists(primary.get("photoTags"), incoming.get("photoTags")),
        "commentLocationHints": merge_string_lists(primary.get("commentLocationHints"), incoming.get("commentLocationHints")),
        "comments": dedupe_mixed([*(primary.get("comments") or []), *(incoming.get("comments") or [])]),
    }


def normalize_location(item: dict[str, Any], comments: list[Any]) -> dict[str, Any]:
    comment_hints = infer_locations_from_comments(comments)
    city = extract_text(item, ["city", "cityName"]) or (item.get("location") or {}).get("city", "") or (comment_hints[0] if comment_hints else "")
    city = str(city or "").strip()
    region = extract_text(item, ["region", "regionName"]) or (item.get("location") or {}).get("region", "") or REGION_MAP.get(city, "")
    latitude = (item.get("location") or {}).get("latitude")
    if latitude is None:
        latitude = (item.get("geo") or {}).get("lat") or item.get("lat")
    longitude = (item.get("location") or {}).get("longitude")
    if longitude is None:
        longitude = (item.get("geo") or {}).get("lon") or item.get("lng") or item.get("lon")
    return {
        "city": city,
        "region": str(region or "").strip(),
        "latitude": latitude,
        "longitude": longitude,
    }


def infer_poi_type(item: dict[str, Any]) -> str:
    return extract_text(item, ["poiType", "poi_type", "category", "spot_type"]) or "scenic-spot"


def infer_route_type(item: dict[str, Any]) -> str:
    return extract_text(item, ["routeType", "route_type"]) or ""


def normalize_item(platform: str, raw_item: dict[str, Any]) -> dict[str, Any]:
    comments = extract_comments(raw_item)
    comment_hints = infer_locations_from_comments(comments)
    location = normalize_location(raw_item, comments)
    title = extract_text(raw_item, ["name", "title", "poiName", "note_title"]) or f"{location['city'] or 'liaoning'}-candidate"
    excerpt = extract_text(raw_item, ["excerpt", "summary", "description", "content"])
    keywords = dedupe_strings([
        *normalize_string_list(raw_item.get("keywords")),
        *normalize_string_list(raw_item.get("tags")),
        *normalize_string_list(raw_item.get("labels")),
        *comment_hints,
    ])
    item = {
        "platform": platform,
        "poiId": extract_text(raw_item, ["poiId", "poi_id", "id", "noteId", "awemeId"]) or re.sub(r"[^a-z0-9\u4e00-\u9fa5-]", "", title.lower().replace(" ", "-")) or "candidate",
        "name": title,
        "sourceUrl": extract_text(raw_item, ["sourceUrl", "source_url", "url", "link", "permalink", "noteUrl", "videoUrl"]),
        "owner": extract_text(raw_item, ["owner", "author", "creator", "userName", "nickname"]),
        "provider": "local-collector",
        "location": location,
        "poiType": infer_poi_type(raw_item),
        "keywords": keywords,
        "excerpt": excerpt or f"来自 {platform} 的辽宁摩旅候选点：{title}",
        "imageUrls": validate_real_image_urls(raw_item),
        "videoUrl": extract_text(raw_item, ["videoUrl", "video_url", "playUrl", "downloadUrl"]),
        "keyframePaths": normalize_string_list(raw_item.get("keyframePaths") or raw_item.get("keyframe_paths")),
        "videoAnalysis": raw_item.get("videoAnalysis") or raw_item.get("video_analysis") or {},
        "fixedSpotInfo": raw_item.get("fixedSpotInfo") or raw_item.get("fixed_spot_info") or {},
        "commentLocationHints": comment_hints,
        "comments": comments,
        "photoTags": dedupe_strings([
            *normalize_string_list(raw_item.get("photoTags")),
            *normalize_string_list(raw_item.get("contentTags")),
        ]),
        "publishedAt": extract_text(raw_item, ["publishedAt", "published_at", "capturedAt", "captured_at", "createTime"]),
        "supportTags": normalize_string_list(raw_item.get("supportTags") or (raw_item.get("fixedSpotInfo") or {}).get("supportTags")),
        "routeType": infer_route_type(raw_item),
        "spotMarkers": normalize_string_list(raw_item.get("spotMarkers") or (raw_item.get("fixedSpotInfo") or {}).get("spotMarkers")),
    }
    if not item["routeType"] and isinstance(item["fixedSpotInfo"], dict):
        item["routeType"] = str(item["fixedSpotInfo"].get("routeType") or "")
    return item


def build_search_tasks(max_items: int) -> list[dict[str, Any]]:
    ordered_platforms = [*TASK_SPEC["platform_priority"], *[platform for platform in TASK_SPEC["platforms"] if platform not in TASK_SPEC["platform_priority"]]]
    tasks: list[dict[str, Any]] = []
    for platform in ordered_platforms:
        for keyword in TASK_SPEC["keywords"]:
            base = {
                "platform": platform,
                "keyword": keyword,
                "province": TASK_SPEC["province"],
                "limit": max_items,
            }
            for hint in TASK_SPEC["social_keywords"]:
                tasks.append({**base, "keyword": f"{keyword} {hint}", "content_hint": hint, "priority": 0})
            tasks.append({**base, "priority": 1})
    return tasks


def score_task_match(task: dict[str, Any], item: dict[str, Any]) -> int:
    haystack = collect_text(item).lower()
    if item.get("platform") and str(item.get("platform")).strip().lower() != task["platform"]:
        return 0
    score = 0
    for token in tokenize_keyword(task["keyword"]):
        if token and token in haystack:
            score += 1
    source_url = extract_text(item, ["sourceUrl", "source_url", "url", "link", "permalink", "noteUrl", "videoUrl"])
    if source_url and any(pattern.search(source_url) for pattern in SOCIAL_SOURCE_PATTERNS.get(task["platform"], [])):
        score += 2
    if extract_comments(item):
        score += 1
    return score


def search_local_items(task: dict[str, Any], items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    scored: list[tuple[int, dict[str, Any]]] = []
    for item in items:
        score = score_task_match(task, item)
        if score <= 0:
            continue
        scored.append((score, item))
    scored.sort(key=lambda entry: entry[0], reverse=True)
    return [item for _, item in scored[: task["limit"]]]


def load_source_items(source_paths: list[Path]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for path in source_paths:
        if not path.exists():
            continue
        items.extend(unwrap_items(read_json_file(path)))
    return items


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_json_list(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    data = read_json_file(path)
    return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []


def write_json_list(path: Path, items: list[dict[str, Any]]) -> None:
    write_json(path, items)


def normalize_collected_candidates(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        normalized.append(adapt_openclaw_candidate(item))
    return normalized


def pending_candidates_match(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_slug = str(left.get("slug") or "").strip()
    right_slug = str(right.get("slug") or "").strip()
    if left_slug and right_slug and left_slug == right_slug:
        return True

    left_city = str(left.get("city") or "").strip()
    right_city = str(right.get("city") or "").strip()
    if left_city and right_city and left_city == right_city:
        left_name = canonical_place_name(left.get("name") or left.get("raw_name") or "")
        right_name = canonical_place_name(right.get("name") or right.get("raw_name") or "")
        if left_name and right_name and left_name == right_name:
            return True
    return False


def prefer_richer_text(left: Any, right: Any) -> str:
    left_text = str(left or "").strip()
    right_text = str(right or "").strip()
    return right_text if len(right_text) > len(left_text) else left_text


def merge_unique_dicts(primary: Any, incoming: Any) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for value in [*(primary or []), *(incoming or [])]:
        if not isinstance(value, dict):
            continue
        key = json.dumps(value, ensure_ascii=False, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        merged.append(value)
    return merged


def merge_candidate_mappings(primary: Any, incoming: Any) -> dict[str, Any]:
    left = primary if isinstance(primary, dict) else {}
    right = incoming if isinstance(incoming, dict) else {}
    merged = {**left}
    for key, value in right.items():
        if isinstance(value, list):
            merged[key] = dedupe_strings([*(left.get(key) or []), *value])
            continue
        if value not in (None, "") and merged.get(key) in (None, ""):
            merged[key] = value
            continue
        if key in {"summary", "transcript", "ocrText", "sceneSummary"}:
            merged[key] = prefer_richer_text(merged.get(key), value)
    return merged


def merge_pending_candidate(primary: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = {
        key: value.copy() if isinstance(value, dict | list) else value
        for key, value in primary.items()
    }

    for key in [
        "spot_type",
        "city",
        "region",
        "route_type",
        "access_level",
        "ride_level",
        "recommended_stay",
        "video_url",
        "image_key",
        "fuel_support",
        "repair_support",
        "lodging_support",
        "food_support",
        "confidence_score",
        "last_verified_at",
    ]:
        if merged.get(key) in (None, "") and incoming.get(key) not in (None, ""):
            merged[key] = incoming[key]

    for key in ["name", "summary"]:
        merged[key] = prefer_richer_text(merged.get(key), incoming.get(key))

    for key in [
        "spot_markers",
        "best_seasons",
        "best_time_of_day",
        "road_features",
        "risk_notes",
        "photo_focus",
        "image_urls",
        "keyframe_paths",
        "route_tags",
        "nearby_spot_slugs",
        "support_role",
        "moto_station_features",
    ]:
        merged[key] = dedupe_strings([*(merged.get(key) or []), *(incoming.get(key) or [])])

    if merged.get("parking_friendly") is None and incoming.get("parking_friendly") is not None:
        merged["parking_friendly"] = incoming["parking_friendly"]

    primary_coordinates = merged.get("coordinates") if isinstance(merged.get("coordinates"), dict) else {}
    incoming_coordinates = incoming.get("coordinates") if isinstance(incoming.get("coordinates"), dict) else {}
    merged["coordinates"] = {
        "lat": primary_coordinates.get("lat") if primary_coordinates.get("lat") is not None else incoming_coordinates.get("lat"),
        "lng": primary_coordinates.get("lng") if primary_coordinates.get("lng") is not None else incoming_coordinates.get("lng"),
    }
    merged["sources"] = merge_unique_dicts(merged.get("sources"), incoming.get("sources"))
    merged["video_analysis"] = merge_candidate_mappings(merged.get("video_analysis"), incoming.get("video_analysis"))
    merged["fixed_spot_info"] = merge_candidate_mappings(merged.get("fixed_spot_info"), incoming.get("fixed_spot_info"))
    return merged


def find_matching_pending_candidate(candidates: list[dict[str, Any]], target: dict[str, Any]) -> dict[str, Any] | None:
    return next((item for item in candidates if pending_candidates_match(item, target)), None)


def summarize_pending_queue_delta(before: list[dict[str, Any]], after: list[dict[str, Any]], normalized_candidates: list[dict[str, Any]]) -> dict[str, int]:
    added = 0
    updated = 0
    for candidate in normalized_candidates:
        before_match = find_matching_pending_candidate(before, candidate)
        after_match = find_matching_pending_candidate(after, candidate)
        if before_match is None and after_match is not None:
            added += 1
            continue
        if before_match is not None and after_match is not None:
            before_snapshot = json.dumps(before_match, ensure_ascii=False, sort_keys=True)
            after_snapshot = json.dumps(after_match, ensure_ascii=False, sort_keys=True)
            if before_snapshot != after_snapshot:
                updated += 1
    return {
        "processed": len(normalized_candidates),
        "added": added,
        "updated": updated,
        "total": len(after),
    }


def sync_pending_candidate_queue(raw_candidates: list[dict[str, Any]]) -> dict[str, int]:
    existing = read_json_list(CANDIDATE_QUEUE_PATH)
    normalized_candidates = [normalize_raw_candidate(item) for item in raw_candidates if isinstance(item, dict)]
    added = 0
    updated = 0

    for incoming in normalized_candidates:
        match_index = next((index for index, item in enumerate(existing) if pending_candidates_match(item, incoming)), None)
        if match_index is None:
            existing.insert(0, incoming)
            added += 1
            continue
        existing[match_index] = merge_pending_candidate(existing[match_index], incoming)
        updated += 1

    write_json_list(CANDIDATE_QUEUE_PATH, existing)
    return {
        "processed": len(normalized_candidates),
        "added": added,
        "updated": updated,
        "total": len(existing),
    }


def update_status(status_path: Path, **changes: Any) -> None:
    current: dict[str, Any] = {}
    if status_path.exists():
        try:
            loaded = read_json_file(status_path)
            if isinstance(loaded, dict):
                current = loaded
        except json.JSONDecodeError:
            current = {}
    current.update(changes)
    current.setdefault("collector_name", TASK_SPEC["name"])
    current.setdefault("events", [])
    if "event_message" in changes:
        event_level = str(changes.get("event_level") or "info")
        current["events"] = [
            {
                "at": now_iso(),
                "level": event_level,
                "message": str(changes["event_message"]),
            },
            *[entry for entry in current.get("events", []) if isinstance(entry, dict)],
        ][:20]
        current.pop("event_message", None)
        current.pop("event_level", None)
    if "cycle_entry" in changes:
        cycle_entry = changes.pop("cycle_entry")
        if isinstance(cycle_entry, dict):
            current["recent_cycles"] = [
                cycle_entry,
                *[entry for entry in current.get("recent_cycles", []) if isinstance(entry, dict)],
            ][:8]
    write_json(status_path, current)


def run_once(
    source_paths: list[Path],
    output_path: Path,
    raw_candidates_path: Path,
    status_path: Path,
    max_items: int,
    cycle_index: int,
    run_pipeline: bool,
    run_mode: str,
) -> dict[str, Any]:
    source_items = load_source_items(source_paths)
    tasks = build_search_tasks(max_items)
    start = time.time()
    update_status(
        status_path,
        state="running",
        health="running",
        current_stage="collecting",
        started_at=now_iso(),
        last_heartbeat=now_iso(),
        source_paths=[str(path) for path in source_paths],
        output_path=str(output_path),
        raw_candidates_path=str(raw_candidates_path),
        tasks_total=len(tasks),
        tasks_completed=0,
        items_collected=0,
        cycle_count=cycle_index,
        run_mode=run_mode,
        pipeline_enabled=run_pipeline,
        pipeline_status="idle" if run_pipeline else "skipped",
        current_task_index=0,
        pid=os.getpid(),
        event_message=f"本地采集任务已启动，第 {cycle_index} 轮。",
    )

    collected: list[dict[str, Any]] = []
    for index, task in enumerate(tasks, start=1):
        matched_items = search_local_items(task, source_items)
        for raw_item in matched_items:
            platform = str(raw_item.get("platform") or task["platform"]).strip().lower() or task["platform"]
            normalized = normalize_item(platform, raw_item)
            if not is_preferred_social_source(platform, normalized) or is_ai_generated_item(normalized) or not normalized["imageUrls"]:
                continue
            if not normalized["location"]["city"] or not normalized["location"]["region"]:
                continue
            collected.append(normalized)
        update_status(
            status_path,
            state="running",
            health="running",
            current_stage="collecting",
            last_heartbeat=now_iso(),
            current_task=f"{task['platform']} / {task['keyword']}",
            current_task_index=index,
            tasks_completed=index,
            tasks_total=len(tasks),
            items_collected=len(collected),
        )

    deduped: list[dict[str, Any]] = []
    for item in collected:
        existing_index = next((idx for idx, existing in enumerate(deduped) if is_same_collected_place(existing, item)), -1)
        if existing_index >= 0:
            deduped[existing_index] = merge_items(deduped[existing_index], item)
        else:
            deduped.append(item)

    payload = {
        "source": "local-collector",
        "exported_at": now_iso(),
        "items": deduped,
    }
    write_json(output_path, payload)
    raw_candidates = normalize_collected_candidates(deduped)
    write_json(raw_candidates_path, raw_candidates)
    normalized_candidates = [normalize_raw_candidate(item) for item in raw_candidates if isinstance(item, dict)]

    pipeline_summary = "skipped"
    queue_sync = {"processed": 0, "added": 0, "updated": 0, "total": len(read_json_list(CANDIDATE_QUEUE_PATH))}
    if run_pipeline:
        queue_before = read_json_list(CANDIDATE_QUEUE_PATH)
        update_status(
            status_path,
            state="running",
            health="running",
            current_stage="running-pipeline",
            pipeline_status="running",
            last_heartbeat=now_iso(),
            current_task="adapt_openclaw_candidates -> normalize_candidate_spots",
            event_message="采集完成，开始执行 adapt + normalize 流水线。",
        )
        run_candidate_pipeline_main()
        pipeline_summary = "adapted openclaw export -> normalized raw candidates"
        queue_after = read_json_list(CANDIDATE_QUEUE_PATH)
        queue_sync = summarize_pending_queue_delta(queue_before, queue_after, normalized_candidates)
        update_status(
            status_path,
            pipeline_status="success",
            last_pipeline_at=now_iso(),
            pipeline_summary=pipeline_summary,
            last_heartbeat=now_iso(),
            pending_candidates_processed=queue_sync["processed"],
            pending_candidates_added=queue_sync["added"],
            pending_candidates_updated=queue_sync["updated"],
            pending_candidates_total=queue_sync["total"],
            event_message="adapt + normalize 流水线执行完成。",
        )
    else:
        queue_sync = sync_pending_candidate_queue(raw_candidates)
        update_status(
            status_path,
            last_heartbeat=now_iso(),
            pipeline_status="skipped",
            pipeline_summary="skipped pipeline; synced pending review queue directly",
            pending_candidates_processed=queue_sync["processed"],
            pending_candidates_added=queue_sync["added"],
            pending_candidates_updated=queue_sync["updated"],
            pending_candidates_total=queue_sync["total"],
            event_message=f"待审批队列已直接同步 {queue_sync['processed']} 条候选数据。",
        )

    duration_seconds = round(time.time() - start, 2)
    update_status(
        status_path,
        state="success",
        health="ok",
        current_stage="idle",
        last_heartbeat=now_iso(),
        last_success_at=now_iso(),
        last_duration_seconds=duration_seconds,
        items_collected=len(deduped),
        tasks_completed=len(tasks),
        tasks_total=len(tasks),
        output_path=str(output_path),
        current_task="",
        current_task_index=len(tasks),
        last_error="",
        pipeline_summary=pipeline_summary,
        pending_candidates_processed=queue_sync["processed"],
        pending_candidates_added=queue_sync["added"],
        pending_candidates_updated=queue_sync["updated"],
        pending_candidates_total=queue_sync["total"],
        cycle_entry={
            "cycle": cycle_index,
            "finished_at": now_iso(),
            "state": "success",
            "items_collected": len(deduped),
            "tasks_completed": len(tasks),
            "tasks_total": len(tasks),
            "duration_seconds": duration_seconds,
            "pipeline_status": "success" if run_pipeline else "skipped",
            "pending_candidates_processed": queue_sync["processed"],
            "pending_candidates_added": queue_sync["added"],
            "pending_candidates_updated": queue_sync["updated"],
            "pending_candidates_total": queue_sync["total"],
        },
        event_message=f"本地采集完成，共输出 {len(deduped)} 条候选数据。",
    )
    return payload


def main() -> None:
    args = parse_args()
    source_paths = [Path(value).resolve() for value in args.sources] if args.sources else DEFAULT_SOURCE_PATHS
    output_path = Path(args.output).resolve()
    raw_candidates_path = Path(args.raw_candidates_output).resolve()
    status_path = Path(args.status).resolve()
    cycle_index = 0
    run_pipeline = not args.skip_pipeline
    run_mode = "manual" if args.continuous else "once"

    while True:
        cycle_index += 1
        try:
            payload = run_once(source_paths, output_path, raw_candidates_path, status_path, args.max_items, cycle_index, run_pipeline, run_mode)
            print(f"local collection completed: {len(payload['items'])} items -> {output_path}")
        except Exception as error:  # pragma: no cover - defensive status handling
            update_status(
                status_path,
                state="error",
                health="error",
                current_stage="error",
                last_heartbeat=now_iso(),
                last_error=str(error),
                last_error_at=now_iso(),
                pipeline_status="error",
                cycle_entry={
                    "cycle": cycle_index,
                    "finished_at": now_iso(),
                    "state": "error",
                    "items_collected": 0,
                    "tasks_completed": 0,
                    "tasks_total": 0,
                    "duration_seconds": None,
                    "pipeline_status": "error",
                },
                event_level="error",
                event_message=f"本地采集失败：{error}",
            )
            raise
        if not args.continuous:
            return
        update_status(
            status_path,
            state="running",
            health="running",
            current_stage="collecting",
            next_run_at="",
            current_task="准备继续采集下一轮",
            event_message="上一轮采集完成，继续执行下一轮。",
        )


if __name__ == "__main__":
    main()