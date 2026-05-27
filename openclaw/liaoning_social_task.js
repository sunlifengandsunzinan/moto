"use strict";

const fs = require("node:fs/promises");
const path = require("node:path");

const OUTPUT_PATH = process.env.OPENCLAW_OUTPUT_PATH || path.resolve(process.cwd(), "data/raw/openclaw_export.json");

const TASK_SPEC = {
  name: "liaoning-douyin-xiaohongshu-collector",
  province: "辽宁省",
  platforms: ["douyin", "xiaohongshu"],
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
  maxItemsPerKeyword: 20,
  outputPath: OUTPUT_PATH,
  outputShape: "data/raw/openclaw_export.json",
  requiredFields: ["platform", "name", "sourceUrl", "owner", "location.city", "location.region", "poiType", "excerpt"],
  notes: [
    "只采集辽宁省内内容，优先保留带城市、路线或驿站线索的帖子。",
    "来源先限抖音和小红书。",
    "输出统一为 wrapped JSON: { source, exported_at, items }."
  ]
};

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

function inferCity(item) {
  const direct = extractText(item, ["city", "cityName", "poi_city"]);
  if (direct) {
    return direct;
  }

  const haystack = [
    extractText(item, ["title", "name"]),
    extractText(item, ["summary", "description", "excerpt"]),
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
    keywords: tags,
    excerpt: summary || `来自 ${platform} 的辽宁摩旅候选点：${title}`,
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

function buildSearchTasks() {
  return TASK_SPEC.platforms.flatMap((platform) =>
    TASK_SPEC.keywords.map((keyword) => ({
      platform,
      keyword,
      province: TASK_SPEC.province,
      limit: TASK_SPEC.maxItemsPerKeyword
    }))
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
      const normalized = normalizeItem(task.platform, rawItem);
      if (!normalized.location.city || !normalized.location.region) {
        continue;
      }
      collected.push(normalized);
    }
  }

  const deduped = [];
  const seen = new Set();
  for (const item of collected) {
    const key = `${item.platform}:${slugify(item.poiId || item.name)}`;
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
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