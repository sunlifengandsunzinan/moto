"use strict";

const fs = require("node:fs/promises");
const path = require("node:path");

const OUTPUT_PATH = process.env.OPENCLAW_OUTPUT_PATH || path.resolve(process.cwd(), "data/raw/openclaw_export.json");

const TASK_SPEC = {
  name: "liaoning-douyin-xiaohongshu-collector",
  province: "辽宁省",
  platforms: ["douyin", "xiaohongshu"],
  platformPriority: ["xiaohongshu", "douyin"],
  keywords: [
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
    "兴城 海滨 摩旅"
  ],
  socialKeywords: [
    "机车合影",
    "骑行照片",
    "实拍",
    "路书",
    "打卡",
    "骑士驿站",
    "补给",
    "观景",
    "夜景"
  ],
  maxItemsPerKeyword: 20,
  outputPath: OUTPUT_PATH,
  outputShape: "data/raw/openclaw_export.json",
  requiredFields: ["platform", "name", "sourceUrl", "owner", "location.city", "location.region", "poiType", "excerpt", "imageUrls"],
  notes: [
    "只采集辽宁省内内容，优先保留带城市、路线或驿站线索的帖子。",
    "来源仅限抖音和小红书，并按小红书、抖音的顺序优先搜索。",
    "必须保留真实社交媒体图片地址，过滤 AI 生成或 data URI 图片。",
    "如果运行时支持评论抓取，则追加评论区地点搜索并把地点线索并入识别。",
    "输出统一为 wrapped JSON: { source, exported_at, items }."
  ]
};

const AI_IMAGE_PATTERNS = [
  /(^|[^a-z])ai([^a-z]|$)/i,
  /aigc/i,
  /midjourney/i,
  /stable[\s-]?diffusion/i,
  /flux/i,
  /comfyui/i,
  /generated/i,
  /synthetic/i,
  /dreamina/i,
  /即梦/,
  /豆包ai/,
  /文生图/,
  /图生图/
];

const SOCIAL_SOURCE_PATTERNS = {
  douyin: [/douyin\.com/i, /iesdouyin\.com/i],
  xiaohongshu: [/xiaohongshu\.com/i, /xhslink\.com/i]
};

const PLACE_GENERIC_TOKENS = [
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
  "骑行"
];

const REGION_MAP = {
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
  "桓仁": "辽东"
};

function slugify(value) {
  return String(value || "candidate")
    .trim()
    .toLowerCase()
    .replace(/\s+/g, "-")
    .replace(/[^a-z0-9\u4e00-\u9fa5-]/g, "")
    .replace(/-+/g, "-") || "candidate";
}

function dedupe(values) {
  const seen = new Set();
  const result = [];
  for (const value of values) {
    const text = String(value || "").trim();
    if (!text || seen.has(text)) {
      continue;
    }
    seen.add(text);
    result.push(text);
  }
  return result;
}

function dedupeMixed(values) {
  const seen = new Set();
  const result = [];
  for (const value of values) {
    if (value === undefined || value === null || value === "") {
      continue;
    }
    const key = typeof value === "string" ? value.trim() : JSON.stringify(value);
    if (!key || seen.has(key)) {
      continue;
    }
    seen.add(key);
    result.push(value);
  }
  return result;
}

function extractText(item, keys) {
  for (const key of keys) {
    const value = item?.[key];
    if (value !== undefined && value !== null && String(value).trim() !== "") {
      return String(value).trim();
    }
  }
  return "";
}

function extractNumber(item, keys) {
  for (const key of keys) {
    const value = item?.[key];
    if (value !== undefined && value !== null && String(value).trim() !== "") {
      const number = Number(value);
      if (!Number.isNaN(number)) {
        return number;
      }
    }
  }
  return null;
}

function canonicalPlaceName(value) {
  let text = String(value || "").trim().toLowerCase().replace(/\s+/g, "");
  for (const token of PLACE_GENERIC_TOKENS) {
    text = text.replaceAll(token, "");
  }
  return text.replace(/[^a-z0-9\u4e00-\u9fa5]/g, "");
}

function placeNameSimilarity(left, right) {
  if (!left || !right) {
    return 0;
  }
  const leftSet = new Set(left.split(""));
  const rightSet = new Set(right.split(""));
  let shared = 0;
  for (const character of leftSet) {
    if (rightSet.has(character)) {
      shared += 1;
    }
  }
  return shared / Math.max(new Set([...leftSet, ...rightSet]).size, 1);
}

function haversineKm(lat1, lng1, lat2, lng2) {
  const radiusKm = 6371;
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLng = ((lng2 - lng1) * Math.PI) / 180;
  const lat1Rad = (lat1 * Math.PI) / 180;
  const lat2Rad = (lat2 * Math.PI) / 180;
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(lat1Rad) * Math.cos(lat2Rad) * Math.sin(dLng / 2) ** 2;
  return 2 * radiusKm * Math.asin(Math.sqrt(a));
}

function coordinatesClose(left, right, maxDistanceKm) {
  const leftLat = Number(left?.location?.latitude);
  const leftLng = Number(left?.location?.longitude);
  const rightLat = Number(right?.location?.latitude);
  const rightLng = Number(right?.location?.longitude);
  if ([leftLat, leftLng, rightLat, rightLng].some((value) => Number.isNaN(value))) {
    return false;
  }
  return haversineKm(leftLat, leftLng, rightLat, rightLng) <= maxDistanceKm;
}

function isSameCollectedPlace(left, right) {
  if ((left?.sourceUrl || "") && left.sourceUrl === right?.sourceUrl) {
    return true;
  }
  if ((left?.location?.city || "") !== (right?.location?.city || "")) {
    return false;
  }
  const leftName = canonicalPlaceName(left?.name || "");
  const rightName = canonicalPlaceName(right?.name || "");
  if (leftName && rightName && leftName === rightName) {
    return true;
  }
  if (coordinatesClose(left, right, 0.25)) {
    return true;
  }
  if (leftName && rightName && coordinatesClose(left, right, 1.2)) {
    return placeNameSimilarity(leftName, rightName) >= 0.55;
  }
  return false;
}

function mergeCollectedPlace(primary, incoming) {
  return {
    ...primary,
    name: String(incoming?.name || "").trim().length > String(primary?.name || "").trim().length ? incoming.name : primary.name,
    excerpt: String(incoming?.excerpt || "").trim().length > String(primary?.excerpt || "").trim().length ? incoming.excerpt : primary.excerpt,
    location: {
      city: primary?.location?.city || incoming?.location?.city || "",
      region: primary?.location?.region || incoming?.location?.region || "",
      latitude: primary?.location?.latitude ?? incoming?.location?.latitude ?? null,
      longitude: primary?.location?.longitude ?? incoming?.location?.longitude ?? null
    },
    keywords: dedupe([...(Array.isArray(primary?.keywords) ? primary.keywords : []), ...(Array.isArray(incoming?.keywords) ? incoming.keywords : [])]),
    imageUrls: dedupe([...(Array.isArray(primary?.imageUrls) ? primary.imageUrls : []), ...(Array.isArray(incoming?.imageUrls) ? incoming.imageUrls : [])]),
    photoTags: dedupe([...(Array.isArray(primary?.photoTags) ? primary.photoTags : []), ...(Array.isArray(incoming?.photoTags) ? incoming.photoTags : [])]),
    supportTags: dedupe([...(Array.isArray(primary?.supportTags) ? primary.supportTags : []), ...(Array.isArray(incoming?.supportTags) ? incoming.supportTags : [])]),
    spotMarkers: dedupe([...(Array.isArray(primary?.spotMarkers) ? primary.spotMarkers : []), ...(Array.isArray(incoming?.spotMarkers) ? incoming.spotMarkers : [])]),
    commentLocationHints: dedupe([...(Array.isArray(primary?.commentLocationHints) ? primary.commentLocationHints : []), ...(Array.isArray(incoming?.commentLocationHints) ? incoming.commentLocationHints : [])]),
    comments: dedupeMixed([...(Array.isArray(primary?.comments) ? primary.comments : []), ...(Array.isArray(incoming?.comments) ? incoming.comments : [])])
  };
}

function appendImageValue(value, result, seen) {
  if (!value) {
    return;
  }
  if (Array.isArray(value)) {
    for (const item of value) {
      appendImageValue(item, result, seen);
    }
    return;
  }
  if (typeof value === "string") {
    const text = value.trim();
    if (!text) {
      return;
    }
    if (/^data:image\//i.test(text)) {
      return;
    }
    if (isLikelyRealImageUrl(text)) {
      if (!seen.has(text)) {
        seen.add(text);
        result.push(text);
      }
    }
    return;
  }
  if (typeof value !== "object") {
    return;
  }

  for (const key of ["url", "src", "href", "origin", "original", "originalUrl", "downloadUrl", "imageUrl", "imageURL", "coverUrl", "thumbnail", "thumb"]) {
    appendImageValue(value[key], result, seen);
  }
  for (const key of ["urls", "list", "images", "items", "sources", "media"]) {
    appendImageValue(value[key], result, seen);
  }
}

function isLikelyRealImageUrl(value) {
  const text = String(value || "").trim();
  if (!text || !/^(https?:)?\/\//i.test(text)) {
    return false;
  }
  if (AI_IMAGE_PATTERNS.some((pattern) => pattern.test(text))) {
    return false;
  }
  return /\.(jpg|jpeg|png|webp|gif)(\?|#|$)/i.test(text) || /[?&](format|image|img|photo|cover|x-oss-process)=/i.test(text);
}

function validateRealImageUrls(item) {
  const imageUrls = collectImageUrls(item);
  return imageUrls.filter((url) => isLikelyRealImageUrl(url));
}

function collectImageUrls(item) {
  const result = [];
  const seen = new Set();
  for (const key of ["imageUrls", "images", "photos", "media", "gallery", "album", "covers", "thumbnails", "image", "imageUrl", "cover", "coverUrl", "thumbnail", "thumb"]) {
    appendImageValue(item?.[key], result, seen);
  }
  for (const key of ["content", "metadata", "post", "note"]) {
    appendImageValue(item?.[key], result, seen);
  }
  return result;
}

function collectText(item) {
  const values = [
    extractText(item, ["title", "name", "poiName", "note_title"]),
    extractText(item, ["summary", "description", "excerpt", "content"]),
    extractText(item, ["author", "creator", "owner", "userName", "nickname"])
  ];
  for (const key of ["tags", "labels", "keywords", "contentTags", "photoTags"]) {
    if (Array.isArray(item?.[key])) {
      values.push(...item[key].map((entry) => String(entry || "")));
    }
  }
  if (Array.isArray(item?.commentLocationHints)) {
    values.push(...item.commentLocationHints.map((entry) => String(entry || "")));
  }
  if (Array.isArray(item?.comments)) {
    for (const comment of item.comments) {
      if (typeof comment === "string") {
        values.push(comment);
        continue;
      }
      if (comment && typeof comment === "object") {
        values.push(
          extractText(comment, ["text", "content", "comment", "body", "location", "place", "poiName", "city", "region"])
        );
      }
    }
  }
  return values.join(" ").trim();
}

function isAiGeneratedItem(item) {
  if (item?.aiGenerated === true || item?.generatedByAI === true || item?.aigc === true) {
    return true;
  }
  const text = collectText(item);
  return AI_IMAGE_PATTERNS.some((pattern) => pattern.test(text));
}

function hasRealImages(item) {
  return validateRealImageUrls(item).length > 0;
}

function isPreferredSocialSource(platform, item) {
  const sourceUrl = extractText(item, ["url", "link", "permalink", "noteUrl", "videoUrl", "sourceUrl"]);
  if (!sourceUrl) {
    return false;
  }
  const patterns = SOCIAL_SOURCE_PATTERNS[platform] || [];
  return patterns.some((pattern) => pattern.test(sourceUrl));
}

function inferCity(item) {
  const direct = extractText(item, ["city", "cityName", "poi_city"]);
  if (direct) {
    return direct;
  }

  const haystack = [
    extractText(item, ["title", "name"]),
    extractText(item, ["summary", "description", "excerpt"]),
    collectText(item),
    ...(Array.isArray(item?.tags) ? item.tags.map(String) : [])
  ].join(" ");

  for (const city of Object.keys(REGION_MAP)) {
    if (haystack.includes(city)) {
      return city;
    }
  }
  return "";
}

function inferRegion(city) {
  return REGION_MAP[city] || "";
}

function inferCategory(item) {
  const joined = [
    extractText(item, ["type", "category", "poiType"]),
    extractText(item, ["title", "name"]),
    extractText(item, ["summary", "description", "excerpt"]),
    ...(Array.isArray(item?.tags) ? item.tags.map(String) : [])
  ].join(" ").toLowerCase();

  if (/驿站|骑士站|rider station|moto station/.test(joined)) {
    return "moto-station";
  }
  if (/加油|补给|fuel|service/.test(joined)) {
    return "support-stop";
  }
  return "scenic-spot";
}

function inferRouteType(category, item) {
  const joined = [
    extractText(item, ["title", "name"]),
    extractText(item, ["summary", "description", "excerpt"]),
    collectText(item),
    ...(Array.isArray(item?.tags) ? item.tags.map(String) : [])
  ].join(" ").toLowerCase();

  if (/沿江|鸭绿江|river/.test(joined)) {
    return "city-riverside";
  }
  if (/海|滨海|coast|sea/.test(joined)) {
    return "coast";
  }
  if (/山|本桓|mountain/.test(joined)) {
    return "mountain";
  }
  if (category === "moto-station" || category === "support-stop") {
    return "supply-stop";
  }
  return "scenic-water";
}

function inferSupportTags(category, item) {
  const joined = [
    extractText(item, ["title", "name"]),
    extractText(item, ["summary", "description", "excerpt"]),
    collectText(item),
    ...(Array.isArray(item?.tags) ? item.tags.map(String) : [])
  ].join(" ").toLowerCase();

  const tags = new Set();
  if (category === "moto-station") {
    tags.add("fuel");
    tags.add("lodging");
  }
  if (/加油|fuel/.test(joined) || category === "support-stop") {
    tags.add("fuel");
  }
  if (/维修|repair/.test(joined)) {
    tags.add("repair");
  }
  if (/住宿|hotel|lodging|民宿/.test(joined)) {
    tags.add("lodging");
  }
  if (/观景|拍照|view|夜景|出片/.test(joined) || category === "scenic-spot") {
    tags.add("viewpoint");
  }
  return Array.from(tags).sort();
}

function inferSpotMarkers(category, item) {
  const joined = [
    extractText(item, ["type", "category", "poiType"]),
    extractText(item, ["title", "name"]),
    extractText(item, ["summary", "description", "excerpt"]),
    collectText(item),
    ...(Array.isArray(item?.tags) ? item.tags.map(String) : []),
    ...(Array.isArray(item?.keywords) ? item.keywords.map(String) : [])
  ].join(" ").toLowerCase();

  const markers = [];
  if (category === "moto-station" || /驿站|骑士站|rider station|moto station/.test(joined)) {
    markers.push("moto-station");
  }
  if (/加油|油站|fuel|gas station|petrol/.test(joined)) {
    markers.push("fuel-station");
  }
  if (/咖啡|coffee|cafe/.test(joined)) {
    markers.push("coffee-stop");
  }
  if (/打卡|观景|拍照|出片|checkpoint|check in|check-in|viewpoint/.test(joined) || category === "scenic-spot") {
    markers.push("checkin-point");
  }
  if (category === "support-stop") {
    markers.push("support-stop");
  }
  return dedupe(markers);
}

function normalizeItem(platform, rawItem) {
  const city = inferCity(rawItem);
  const region = extractText(rawItem, ["region", "regionName", "district"]) || inferRegion(city);
  const category = inferCategory(rawItem);
  const tags = dedupe([
    ...(Array.isArray(rawItem?.tags) ? rawItem.tags : []),
    ...(Array.isArray(rawItem?.labels) ? rawItem.labels : []),
    ...(Array.isArray(rawItem?.keywords) ? rawItem.keywords : [])
  ]);
  const title = extractText(rawItem, ["title", "name", "poiName", "note_title"]);
  const summary = extractText(rawItem, ["summary", "description", "excerpt", "content"]);
  const lat = extractNumber(rawItem.coordinates || rawItem.location || rawItem.geo || rawItem, ["lat", "latitude"]);
  const lng = extractNumber(rawItem.coordinates || rawItem.location || rawItem.geo || rawItem, ["lng", "lon", "longitude"]);
  const url = extractText(rawItem, ["url", "link", "permalink", "noteUrl", "videoUrl"]);
  const author = extractText(rawItem, ["author", "creator", "owner", "userName", "nickname"]);
  const slugBase = `${city || "liaoning"}-${title || rawItem.id || "candidate"}`;

  const imageUrls = validateRealImageUrls(rawItem);
  const spotMarkers = inferSpotMarkers(category, rawItem);

  return {
    platform,
    poiId: extractText(rawItem, ["id", "poiId", "noteId", "awemeId"]) || slugify(slugBase),
    name: title,
    sourceUrl: url,
    owner: author,
    provider: "openclaw",
    location: {
      city,
      region,
      latitude: lat,
      longitude: lng
    },
    poiType: category,
    spotMarkers,
    keywords: tags,
    excerpt: summary || `来自 ${platform} 的辽宁摩旅候选点：${title}`,
    imageUrls,
    commentLocationHints: Array.isArray(rawItem?.commentLocationHints) ? dedupe(rawItem.commentLocationHints) : [],
    comments: Array.isArray(rawItem?.comments) ? rawItem.comments : [],
    photoTags: dedupe([
      ...(Array.isArray(rawItem?.contentTags) ? rawItem.contentTags : []),
      ...(Array.isArray(rawItem?.photoTags) ? rawItem.photoTags : []),
      ...tags
    ]),
    publishedAt: extractText(rawItem, ["capturedAt", "captured_at", "publishedAt", "publishTime", "createTime"]),
    supportTags: inferSupportTags(category, rawItem),
    routeType: inferRouteType(category, rawItem)
  };
}

function extractCommentText(comment) {
  if (typeof comment === "string") {
    return comment.trim();
  }
  if (!comment || typeof comment !== "object") {
    return "";
  }
  return extractText(comment, ["text", "content", "comment", "body"]).trim();
}

function inferLocationsFromComments(comments) {
  const hints = [];
  const source = Array.isArray(comments) ? comments : [];
  for (const comment of source) {
    const text = `${extractCommentText(comment)} ${extractText(comment, ["location", "place", "poiName", "city", "region"])}`.trim();
    if (!text) {
      continue;
    }
    for (const city of Object.keys(REGION_MAP)) {
      if (text.includes(city) && !hints.includes(city)) {
        hints.push(city);
      }
    }
  }
  return hints;
}

function mergeCommentSignals(rawItem, comments) {
  const mergedComments = Array.isArray(comments) ? comments : [];
  const commentLocationHints = inferLocationsFromComments(mergedComments);
  const commentCity = commentLocationHints[0] || "";
  const commentRegion = commentCity ? REGION_MAP[commentCity] || "" : "";
  const mergedTags = dedupe([
    ...(Array.isArray(rawItem?.tags) ? rawItem.tags : []),
    ...commentLocationHints
  ]);
  return {
    ...rawItem,
    comments: mergedComments,
    commentLocationHints,
    tags: mergedTags,
    region: rawItem?.region || rawItem?.regionName || commentRegion,
    regionName: rawItem?.regionName || rawItem?.region || commentRegion,
    city: rawItem?.city || rawItem?.cityName || commentCity,
    cityName: rawItem?.cityName || rawItem?.city || commentCity
  };
}

function getCommentSearcher(runtime) {
  const searcher = runtime.searchComments || runtime.fetchComments || runtime.collectComments || runtime.getComments;
  return typeof searcher === "function" ? searcher : null;
}

async function searchLocationInComments(runtime, task, rawItem) {
  const commentSearcher = getCommentSearcher(runtime);
  if (!commentSearcher) {
    return [];
  }
  const request = {
    platform: task.platform,
    keyword: task.keyword,
    province: task.province,
    sourceUrl: extractText(rawItem, ["url", "link", "permalink", "noteUrl", "videoUrl", "sourceUrl"]),
    itemId: extractText(rawItem, ["id", "poiId", "noteId", "awemeId"]),
    title: extractText(rawItem, ["title", "name", "poiName", "note_title"]),
    mode: "location-in-comments",
    limit: 50
  };
  let result;
  try {
    result = await commentSearcher(request);
  } catch (_error) {
    return [];
  }
  if (Array.isArray(result)) {
    return result;
  }
  if (Array.isArray(result?.comments)) {
    return result.comments;
  }
  if (Array.isArray(result?.items)) {
    return result.items;
  }
  return [];
}

function buildSearchTasks() {
  const orderedPlatforms = [
    ...TASK_SPEC.platformPriority,
    ...TASK_SPEC.platforms.filter((platform) => !TASK_SPEC.platformPriority.includes(platform))
  ].filter((platform, index, values) => TASK_SPEC.platforms.includes(platform) && values.indexOf(platform) === index);

  return orderedPlatforms.flatMap((platform) =>
    TASK_SPEC.keywords.flatMap((keyword) => {
      const baseTask = {
        platform,
        keyword,
        province: TASK_SPEC.province,
        limit: TASK_SPEC.maxItemsPerKeyword,
        searchMode: "social-first",
        requireRealImages: true
      };
      const focusedTasks = TASK_SPEC.socialKeywords.map((hint) => ({
        ...baseTask,
        keyword: `${keyword} ${hint}`,
        contentHint: hint,
        priority: 0
      }));
      return [
        ...focusedTasks,
        { ...baseTask, priority: 1 }
      ];
    })
  );
}

async function run(runtime = {}) {
  const collector = runtime.collect || runtime.runSearch || runtime.search;
  if (typeof collector !== "function") {
    throw new Error("OpenClaw runtime must provide collect(task), runSearch(task), or search(task).");
  }

  const collected = [];
  for (const task of buildSearchTasks()) {
    const items = await collector(task);
    const rawItems = Array.isArray(items) ? items : Array.isArray(items?.items) ? items.items : [];
    for (const rawItem of rawItems) {
      const comments = await searchLocationInComments(runtime, task, rawItem);
      const enrichedRawItem = mergeCommentSignals(rawItem, comments);
      if (!isPreferredSocialSource(task.platform, enrichedRawItem) || isAiGeneratedItem(enrichedRawItem) || !hasRealImages(enrichedRawItem)) {
        continue;
      }
      const normalized = normalizeItem(task.platform, enrichedRawItem);
      if (!normalized.location.city || !normalized.location.region || normalized.imageUrls.length === 0) {
        continue;
      }
      collected.push(normalized);
    }
  }

  const deduped = [];
  for (const item of collected) {
    const existingIndex = deduped.findIndex((existing) => isSameCollectedPlace(existing, item));
    if (existingIndex >= 0) {
      deduped[existingIndex] = mergeCollectedPlace(deduped[existingIndex], item);
      continue;
    }
    deduped.push(item);
  }

  const payload = {
    source: "openclaw",
    exported_at: new Date().toISOString(),
    items: deduped
  };

  await fs.mkdir(path.dirname(TASK_SPEC.outputPath), { recursive: true });
  await fs.writeFile(TASK_SPEC.outputPath, JSON.stringify(payload, null, 2) + "\n", "utf-8");
  return payload;
}

if (require.main === module) {
  run(globalThis.openclaw || {})
    .then((payload) => {
      console.log(`exported ${payload.items.length} OpenClaw items -> ${TASK_SPEC.outputPath}`);
    })
    .catch((error) => {
      console.error(error instanceof Error ? error.message : String(error));
      process.exitCode = 1;
    });
}

module.exports = {
  TASK_SPEC,
  buildSearchTasks,
  normalizeItem,
  run
};