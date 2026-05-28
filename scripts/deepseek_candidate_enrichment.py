from __future__ import annotations

import json
import os
import re
from typing import Any
from urllib.request import Request, urlopen


DEFAULT_BASE_URL = "https://api.deepseek.com/chat/completions"
DEFAULT_MODEL = "deepseek-chat"


def is_deepseek_configured() -> bool:
    return bool(os.getenv("DEEPSEEK_API_KEY", "").strip())


def enrich_items_with_deepseek(items: list[dict[str, Any]], timeout_seconds: int = 45) -> list[dict[str, Any]]:
    if not is_deepseek_configured():
        return items
    enriched: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            result = request_deepseek_enrichment(item, timeout_seconds=timeout_seconds)
        except Exception:
            enriched.append(item)
            continue
        enriched.append(merge_item_enrichment(item, result))
    return enriched


def request_deepseek_enrichment(item: dict[str, Any], timeout_seconds: int = 45) -> dict[str, Any]:
    api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        return {}
    payload = {
        "model": os.getenv("DEEPSEEK_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是辽宁摩旅点位结构化助手。"
                    "根据输入的短视频元数据、文案、OCR 文本和截图线索，"
                    "只输出一个 JSON 对象，不要输出额外说明。"
                    "JSON 必须包含 fixedSpotInfo、videoAnalysis、supportTags、photoTags、spotMarkers、routeType、poiType、confidenceScore。"
                    "fixedSpotInfo 内字段必须包含 city、region、poiType、routeType、supportTags、spotMarkers、photoTags、summary。"
                    "videoAnalysis 内字段必须包含 transcript、ocrText、summary、sceneSummary、keywords、sceneLabels、placeHints、supportHints、routeHints、spotMarkers、captions。"
                    "如果无法判断，使用空字符串或空数组。只推断辽宁省内摩旅打卡点、驿站、咖啡停靠、补给点相关语义。"
                ),
            },
            {
                "role": "user",
                "content": json.dumps(build_candidate_payload(item), ensure_ascii=False),
            },
        ],
        "temperature": 0.2,
    }
    request = Request(
        os.getenv("DEEPSEEK_BASE_URL", DEFAULT_BASE_URL).strip() or DEFAULT_BASE_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urlopen(request, timeout=timeout_seconds) as response:
        body = json.loads(response.read().decode("utf-8"))
    content = (((body.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
    return parse_json_object(content)


def build_candidate_payload(item: dict[str, Any]) -> dict[str, Any]:
    fixed_info = item.get("fixedSpotInfo") or item.get("fixed_spot_info") or {}
    video_analysis = item.get("videoAnalysis") or item.get("video_analysis") or {}
    return {
        "platform": str(item.get("platform") or "").strip(),
        "title": first_text(item, ["name", "title", "poiName", "note_title"]),
        "excerpt": first_text(item, ["excerpt", "summary", "description", "content"]),
        "sourceUrl": first_text(item, ["sourceUrl", "source_url", "url", "link", "permalink"]),
        "owner": first_text(item, ["owner", "author", "creator", "userName", "nickname"]),
        "publishedAt": first_text(item, ["publishedAt", "published_at", "capturedAt", "captured_at"]),
        "keywords": normalize_string_list(item.get("keywords") or item.get("tags") or item.get("labels")),
        "contentTags": normalize_string_list(item.get("contentTags") or item.get("photoTags") or item.get("photo_tags")),
        "supportTags": normalize_string_list(item.get("supportTags") or fixed_info.get("supportTags")),
        "spotMarkers": normalize_string_list(item.get("spotMarkers") or fixed_info.get("spotMarkers")),
        "commentLocationHints": normalize_string_list(item.get("commentLocationHints") or item.get("comment_location_hints")),
        "location": item.get("location") if isinstance(item.get("location"), dict) else {},
        "videoUrl": first_text(item, ["videoUrl", "video_url", "playUrl", "downloadUrl"]),
        "keyframePaths": normalize_string_list(item.get("keyframePaths") or item.get("keyframe_paths")),
        "imageUrls": normalize_string_list(item.get("imageUrls") or item.get("image_urls")),
        "videoAnalysis": normalize_video_analysis(video_analysis),
        "fixedSpotInfo": normalize_fixed_spot_info(fixed_info),
        "comments": normalize_comments(item.get("comments")),
    }


def merge_item_enrichment(item: dict[str, Any], enrichment: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(enrichment, dict) or not enrichment:
        return item
    merged = {
        key: value.copy() if isinstance(value, list | dict) else value
        for key, value in item.items()
    }
    fixed_info = normalize_fixed_spot_info(merged.get("fixedSpotInfo") or merged.get("fixed_spot_info"))
    incoming_fixed = normalize_fixed_spot_info(enrichment.get("fixedSpotInfo") or enrichment.get("fixed_spot_info"))
    video_analysis = normalize_video_analysis(merged.get("videoAnalysis") or merged.get("video_analysis"))
    incoming_video = normalize_video_analysis(enrichment.get("videoAnalysis") or enrichment.get("video_analysis"))

    merged_fixed = {
        "city": fixed_info.get("city") or incoming_fixed.get("city") or "",
        "region": fixed_info.get("region") or incoming_fixed.get("region") or "",
        "poiType": fixed_info.get("poiType") or incoming_fixed.get("poiType") or str(enrichment.get("poiType") or "").strip(),
        "routeType": fixed_info.get("routeType") or incoming_fixed.get("routeType") or str(enrichment.get("routeType") or "").strip(),
        "supportTags": merge_string_lists(fixed_info.get("supportTags"), incoming_fixed.get("supportTags") or enrichment.get("supportTags")),
        "spotMarkers": merge_string_lists(fixed_info.get("spotMarkers"), incoming_fixed.get("spotMarkers") or enrichment.get("spotMarkers")),
        "photoTags": merge_string_lists(fixed_info.get("photoTags"), incoming_fixed.get("photoTags") or enrichment.get("photoTags")),
        "summary": richer_text(fixed_info.get("summary"), incoming_fixed.get("summary")),
    }
    merged_video = {
        "transcript": richer_text(video_analysis.get("transcript"), incoming_video.get("transcript")),
        "ocrText": richer_text(video_analysis.get("ocrText"), incoming_video.get("ocrText")),
        "summary": richer_text(video_analysis.get("summary"), incoming_video.get("summary")),
        "sceneSummary": richer_text(video_analysis.get("sceneSummary"), incoming_video.get("sceneSummary")),
        "keywords": merge_string_lists(video_analysis.get("keywords"), incoming_video.get("keywords")),
        "sceneLabels": merge_string_lists(video_analysis.get("sceneLabels"), incoming_video.get("sceneLabels")),
        "placeHints": merge_string_lists(video_analysis.get("placeHints"), incoming_video.get("placeHints")),
        "supportHints": merge_string_lists(video_analysis.get("supportHints"), incoming_video.get("supportHints")),
        "routeHints": merge_string_lists(video_analysis.get("routeHints"), incoming_video.get("routeHints")),
        "spotMarkers": merge_string_lists(video_analysis.get("spotMarkers"), incoming_video.get("spotMarkers")),
        "captions": merge_string_lists(video_analysis.get("captions"), incoming_video.get("captions")),
    }
    merged["fixedSpotInfo"] = merged_fixed
    merged["videoAnalysis"] = merged_video
    merged["supportTags"] = merge_string_lists(merged.get("supportTags"), enrichment.get("supportTags") or merged_fixed.get("supportTags"))
    merged["photoTags"] = merge_string_lists(merged.get("photoTags"), enrichment.get("photoTags") or merged_fixed.get("photoTags"))
    merged["spotMarkers"] = merge_string_lists(merged.get("spotMarkers"), enrichment.get("spotMarkers") or merged_fixed.get("spotMarkers"))
    if not str(merged.get("routeType") or "").strip():
        merged["routeType"] = merged_fixed.get("routeType", "")
    if not str(merged.get("poiType") or "").strip():
        merged["poiType"] = merged_fixed.get("poiType", "")
    if not str(merged.get("confidenceScore") or "").strip() and str(enrichment.get("confidenceScore") or "").strip():
        merged["confidenceScore"] = str(enrichment.get("confidenceScore") or "").strip()
    return merged


def parse_json_object(value: str) -> dict[str, Any]:
    text = value.strip()
    if not text:
        return {}
    if text.startswith("```"):
        match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, flags=re.DOTALL)
        if match:
            text = match.group(1)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"(\{.*\})", text, flags=re.DOTALL)
        if not match:
            return {}
        try:
            parsed = json.loads(match.group(1))
        except json.JSONDecodeError:
            return {}
    return parsed if isinstance(parsed, dict) else {}


def first_text(item: dict[str, Any], keys: list[str]) -> str:
    for key in keys:
        value = item.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def richer_text(left: Any, right: Any) -> str:
    left_text = str(left or "").strip()
    right_text = str(right or "").strip()
    return right_text if len(right_text) > len(left_text) else left_text


def normalize_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if value in (None, ""):
        return []
    text = str(value).replace("，", ",").replace("\n", ",")
    return [part.strip() for part in text.split(",") if part.strip()]


def merge_string_lists(left: Any, right: Any) -> list[str]:
    merged: list[str] = []
    for value in [*normalize_string_list(left), *normalize_string_list(right)]:
        if value not in merged:
            merged.append(value)
    return merged


def normalize_video_analysis(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        value = {}
    return {
        "transcript": str(value.get("transcript") or "").strip(),
        "ocrText": str(value.get("ocrText") or value.get("ocr_text") or "").strip(),
        "summary": str(value.get("summary") or "").strip(),
        "sceneSummary": str(value.get("sceneSummary") or value.get("scene_summary") or "").strip(),
        "keywords": normalize_string_list(value.get("keywords")),
        "sceneLabels": normalize_string_list(value.get("sceneLabels") or value.get("scene_labels")),
        "placeHints": normalize_string_list(value.get("placeHints") or value.get("place_hints")),
        "supportHints": normalize_string_list(value.get("supportHints") or value.get("support_hints")),
        "routeHints": normalize_string_list(value.get("routeHints") or value.get("route_hints")),
        "spotMarkers": normalize_string_list(value.get("spotMarkers") or value.get("spot_markers")),
        "captions": normalize_string_list(value.get("captions")),
    }


def normalize_fixed_spot_info(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        value = {}
    return {
        "city": str(value.get("city") or "").strip(),
        "region": str(value.get("region") or "").strip(),
        "poiType": str(value.get("poiType") or value.get("poi_type") or "").strip(),
        "routeType": str(value.get("routeType") or value.get("route_type") or "").strip(),
        "supportTags": normalize_string_list(value.get("supportTags") or value.get("support_tags")),
        "spotMarkers": normalize_string_list(value.get("spotMarkers") or value.get("spot_markers")),
        "photoTags": normalize_string_list(value.get("photoTags") or value.get("photo_tags")),
        "summary": str(value.get("summary") or "").strip(),
    }


def normalize_comments(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for comment in value:
        if isinstance(comment, dict):
            text = str(comment.get("text") or comment.get("content") or "").strip()
            if text:
                result.append(text)
            continue
        text = str(comment or "").strip()
        if text:
            result.append(text)
    return result