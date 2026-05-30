"use strict";

const fs = require("node:fs/promises");
const path = require("node:path");

const PROJECT_ROOT = process.env.OPENCLAW_PROJECT_ROOT || process.cwd();
const ROUTE_TEMPLATE_PATH = process.env.OPENCLAW_ROUTE_TEMPLATE_PATH || path.resolve(PROJECT_ROOT, "app/services/route_templates.json");
const OUTPUT_PATH = process.env.OPENCLAW_ROUTE_WAYPOINT_OUTPUT_PATH || path.resolve(PROJECT_ROOT, "data/raw/openclaw_route_waypoints.json");
const MAX_ITEMS_PER_KEYWORD = Number(process.env.OPENCLAW_ROUTE_MAX_ITEMS_PER_KEYWORD || 8);
const MAX_KEYWORDS_PER_ROUTE = Number(process.env.OPENCLAW_ROUTE_MAX_KEYWORDS_PER_ROUTE || 6);

const TASK_SPEC = {
  name: "douyin-route-waypoint-collector",
  platform: "douyin",
  province: "辽宁省",
  schedule: {
    cron: "15 */6 * * *",
    timezone: "Asia/Shanghai",
    note: "免费方案建议每 6 小时跑一次增量视频分析，夜间可再补一轮全量。"
  },
  outputPath: OUTPUT_PATH,
  routeTemplatePath: ROUTE_TEMPLATE_PATH,
  outputShape: "data/raw/openclaw_route_waypoints.json",
  notes: [
    "优先从抖音视频标题、简介、OCR、转写和关键帧说明中抽取途径点。",
    "不依赖付费地图 API；没有坐标时也保留名称，仍可生成名称导航版高德路线。",
    "输出按 route_slug 聚合，便于后续人工审核后回写 app/services/route_templates.json。"
  ]
};

const EXTRA_ROUTE_SUFFIXES = ["摩旅", "机车", "骑行", "路书", "路线", "高德", "途径点"];
const ROUTE_CONNECTOR_PATTERN = /(->|→|➡|⟶|－|—|至|到|经|途经|路过)/;
const POI_SUFFIX_PATTERN = /[\u4e00-\u9fa5A-Za-z0-9]{2,24}(服务区|服务站|古镇|景区|风景区|观景台|观景点|村|镇|县城|城区|公路|大道|大桥|驿站|营地|加油站|停车区|停车场|湖|山|岛|口岸|码头|隧道|广场|海岸|滨海路|检查站)/g;

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

function slugify(value) {
  return String(value || "candidate")
    .trim()
    .toLowerCase()
    .replace(/\s+/g, "-")
    .replace(/[^a-z0-9\u4e00-\u9fa5-]/g, "")
    .replace(/-+/g, "-") || "candidate";
}

function normalizeName(value) {
  return String(value || "")
    .trim()
    .replace(/[()（）\[\]【】]/g, "")
    .replace(/\s+/g, "")
    .toLowerCase();
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

function normalizeCoordinate(rawValue) {
  if (rawValue === undefined || rawValue === null || rawValue === "") {
    return null;
  }
  const number = Number(rawValue);
  return Number.isFinite(number) ? number : null;
}

function normalizeWaypoint(rawPoint) {
  if (!rawPoint) {
    return null;
  }
  if (typeof rawPoint === "string") {
    const name = rawPoint.trim();
    if (!name) {
      return null;
    }
    return { name, lng: null, lat: null, has_coordinates: false, source: "openclaw-video-analysis" };
  }
  if (typeof rawPoint !== "object") {
    return null;
  }

  const name = extractText(rawPoint, ["name", "title", "poiName", "place", "location"]);
  if (!name) {
    return null;
  }

  const lng = normalizeCoordinate(rawPoint.lng ?? rawPoint.longitude ?? rawPoint?.coordinates?.lng ?? rawPoint?.coordinates?.longitude);
  const lat = normalizeCoordinate(rawPoint.lat ?? rawPoint.latitude ?? rawPoint?.coordinates?.lat ?? rawPoint?.coordinates?.latitude);
  return {
    name,
    lng,
    lat,
    has_coordinates: lng !== null && lat !== null,
    source: extractText(rawPoint, ["source", "provider", "channel"]) || "openclaw-video-analysis"
  };
}

async function loadRouteTemplates() {
  const payload = JSON.parse(await fs.readFile(TASK_SPEC.routeTemplatePath, "utf-8"));
  return Array.isArray(payload) ? payload.filter((route) => route && typeof route === "object" && !route.is_navigation_state_demo) : [];
}

function extractRouteHintNames(route) {
  const names = [];
  const navigation = route?.navigation && typeof route.navigation === "object" ? route.navigation : {};
  const navigationWaypoints = Array.isArray(navigation.waypoints)
    ? navigation.waypoints
    : Array.isArray(route?.navigation_waypoints)
      ? route.navigation_waypoints
      : Array.isArray(route?.waypoints)
        ? route.waypoints
        : [];

  for (const point of navigationWaypoints) {
    const normalized = normalizeWaypoint(point);
    if (normalized) {
      names.push(normalized.name);
    }
  }

  for (const day of Array.isArray(route?.days_plan) ? route.days_plan : []) {
    const title = extractText(day, ["title"]);
    if (!title) {
      continue;
    }
    for (const part of title.split(/->|→|➡|⟶|－|—/)) {
      const text = String(part || "").trim();
      if (text) {
        names.push(text);
      }
    }
  }

  return dedupe(names);
}

function buildRouteKeywords(route) {
  const baseTerms = dedupe([
    extractText(route, ["title"]),
    ...extractRouteHintNames(route).slice(0, 4),
    ...(Array.isArray(route?.tags) ? route.tags.map((item) => String(item || "").trim()) : [])
  ]).slice(0, MAX_KEYWORDS_PER_ROUTE);

  const result = [];
  for (const term of baseTerms) {
    result.push(term);
    for (const suffix of EXTRA_ROUTE_SUFFIXES.slice(0, 3)) {
      result.push(`${term} ${suffix}`);
    }
  }
  return dedupe(result).slice(0, MAX_KEYWORDS_PER_ROUTE * 2);
}

function buildSearchTasks(routes) {
  const tasks = [];
  for (const route of routes) {
    for (const keyword of buildRouteKeywords(route)) {
      tasks.push({
        platform: TASK_SPEC.platform,
        province: TASK_SPEC.province,
        routeSlug: route.slug,
        routeTitle: route.title,
        keyword,
        limit: MAX_ITEMS_PER_KEYWORD,
        expectedWaypoints: extractRouteHintNames(route)
      });
    }
  }
  return tasks;
}

function getCollector(runtime) {
  return runtime.collect || runtime.runSearch || runtime.search || null;
}

function flattenVideoAnalysisText(videoAnalysis) {
  if (!videoAnalysis || typeof videoAnalysis !== "object") {
    return [];
  }
  return dedupe([
    extractText(videoAnalysis, ["transcript", "text", "subtitle", "subtitles"]),
    extractText(videoAnalysis, ["ocrText", "ocr", "ocr_text"]),
    extractText(videoAnalysis, ["summary", "description"]),
    extractText(videoAnalysis, ["sceneSummary", "scene_summary", "sceneDescription"]),
    ...(Array.isArray(videoAnalysis.keywords) ? videoAnalysis.keywords : []).map((item) => String(item || "").trim()),
    ...(Array.isArray(videoAnalysis.placeHints) ? videoAnalysis.placeHints : []).map((item) => String(item || "").trim()),
    ...(Array.isArray(videoAnalysis.routeHints) ? videoAnalysis.routeHints : []).map((item) => String(item || "").trim()),
    ...(Array.isArray(videoAnalysis.captions) ? videoAnalysis.captions : []).map((item) => String(item || "").trim())
  ]).filter(Boolean);
}

async function analyzeRouteVideo(runtime, task, rawItem) {
  const analyzer = runtime.analyzeVideo || runtime.inspectVideo || runtime.describeVideo || runtime.transcribeVideo || runtime.analyzeMedia;
  if (typeof analyzer !== "function") {
    return {};
  }

  try {
    const result = await analyzer({
      platform: task.platform,
      keyword: task.keyword,
      province: task.province,
      routeSlug: task.routeSlug,
      routeTitle: task.routeTitle,
      mode: "route-waypoints",
      expectedWaypoints: task.expectedWaypoints,
      sourceUrl: extractText(rawItem, ["sourceUrl", "url", "link", "permalink", "videoUrl"]),
      videoUrl: extractText(rawItem, ["videoUrl", "playUrl", "downloadUrl"]),
      title: extractText(rawItem, ["title", "name", "poiName"]),
      prompt: "提取视频里出现的摩旅路线起点、终点和中间途径点，按实际顺序返回；如果只有名称就不要编造坐标。"
    });
    return result && typeof result === "object" ? result : {};
  } catch (_error) {
    return {};
  }
}

function collectText(rawItem, videoAnalysis) {
  const values = [
    extractText(rawItem, ["title", "name", "poiName"]),
    extractText(rawItem, ["summary", "description", "excerpt", "content"]),
    extractText(rawItem, ["owner", "author", "creator", "nickname"]),
    ...flattenVideoAnalysisText(videoAnalysis)
  ];
  return values.filter(Boolean).join("\n");
}

function extractSequenceWaypoints(text) {
  const candidates = [];
  for (const line of String(text || "").split(/[\n；;。]/)) {
    const sourceLine = line.trim();
    if (!sourceLine || !ROUTE_CONNECTOR_PATTERN.test(sourceLine)) {
      continue;
    }
    const pieces = sourceLine
      .split(/->|→|➡|⟶|－|—|至|到|经|途经|路过/g)
      .map((item) => item.replace(/^[^\u4e00-\u9fa5A-Za-z0-9]+|[^\u4e00-\u9fa5A-Za-z0-9]+$/g, "").trim())
      .filter((item) => item.length >= 2 && item.length <= 24);
    if (pieces.length >= 2) {
      candidates.push(...pieces);
    }
  }
  return dedupe(candidates);
}

function extractPoiLikeWaypoints(text) {
  const matches = [];
  const content = String(text || "");
  for (const match of content.matchAll(POI_SUFFIX_PATTERN)) {
    const name = String(match[0] || "").trim();
    if (name) {
      matches.push(name);
    }
  }
  return dedupe(matches);
}

function extractExpectedWaypointHits(expectedWaypoints, text) {
  const haystack = normalizeName(text);
  const hits = [];
  for (const name of expectedWaypoints || []) {
    const normalized = normalizeName(name);
    if (!normalized) {
      continue;
    }
    const index = haystack.indexOf(normalized);
    if (index >= 0) {
      hits.push({ name, index });
    }
  }
  return hits.sort((left, right) => left.index - right.index).map((item) => item.name);
}

function extractWaypointsFromAnalysis(rawItem, videoAnalysis, task) {
  const analysisWaypoints = [];
  const structuredWaypoints = Array.isArray(videoAnalysis?.waypoints)
    ? videoAnalysis.waypoints
    : Array.isArray(videoAnalysis?.routeWaypoints)
      ? videoAnalysis.routeWaypoints
      : Array.isArray(videoAnalysis?.path)
        ? videoAnalysis.path
        : [];
  for (const rawPoint of structuredWaypoints) {
    const normalized = normalizeWaypoint(rawPoint);
    if (normalized) {
      analysisWaypoints.push(normalized);
    }
  }

  if (analysisWaypoints.length > 0) {
    return analysisWaypoints;
  }

  const text = collectText(rawItem, videoAnalysis);
  const fallbackNames = dedupe([
    ...extractExpectedWaypointHits(task.expectedWaypoints, text),
    ...extractSequenceWaypoints(text),
    ...extractPoiLikeWaypoints(text)
  ]);
  return fallbackNames.map((name) => normalizeWaypoint(name)).filter(Boolean);
}

function mergeWaypointIntoMap(waypointMap, orderedNames, waypoint, sourceUrl) {
  const normalized = normalizeWaypoint(waypoint);
  if (!normalized) {
    return;
  }
  const key = normalizeName(normalized.name);
  if (!key) {
    return;
  }

  if (!waypointMap.has(key)) {
    waypointMap.set(key, {
      name: normalized.name,
      lng: normalized.lng,
      lat: normalized.lat,
      has_coordinates: normalized.has_coordinates,
      source: normalized.source,
      evidence_urls: sourceUrl ? [sourceUrl] : [],
      mention_count: 1
    });
    orderedNames.push(key);
    return;
  }

  const current = waypointMap.get(key);
  current.mention_count += 1;
  if (sourceUrl && !current.evidence_urls.includes(sourceUrl)) {
    current.evidence_urls.push(sourceUrl);
  }
  if (!current.has_coordinates && normalized.has_coordinates) {
    current.lng = normalized.lng;
    current.lat = normalized.lat;
    current.has_coordinates = true;
  }
}

function routeNavigationMode(waypoints) {
  if (!waypoints.length) {
    return "none";
  }
  const coordinateWaypointCount = waypoints.filter((point) => point.has_coordinates).length;
  if (coordinateWaypointCount === 0) {
    return "names";
  }
  if (coordinateWaypointCount === waypoints.length) {
    return "coordinates";
  }
  return "mixed";
}

function routeNavigationStatusVariant(mode) {
  if (mode === "coordinates") {
    return "complete";
  }
  if (mode === "mixed") {
    return "partial";
  }
  return "names";
}

function routeNavigationStatusBadge(variant) {
  if (variant === "complete") {
    return "坐标完整";
  }
  if (variant === "partial") {
    return "部分坐标";
  }
  return "名称导航";
}

function routeNavigationStatusText(waypoints, mode) {
  const waypointCount = waypoints.length;
  const coordinateWaypointCount = waypoints.filter((point) => point.has_coordinates).length;
  if (waypointCount === 0) {
    return "";
  }
  if (mode === "coordinates") {
    return `${coordinateWaypointCount}/${waypointCount} 个点已带坐标，可直接高德逐点导航`;
  }
  if (mode === "mixed") {
    return `${coordinateWaypointCount}/${waypointCount} 个点已带坐标，将混合坐标和地点名称导航`;
  }
  return `0/${waypointCount} 个点带坐标，将按地点名称导航`;
}

function routeAmapPointValue(point) {
  if (point.has_coordinates && point.lng !== null && point.lat !== null) {
    return `${point.lng},${point.lat},${point.name}`;
  }
  return String(point.name || "");
}

function buildAmapExportHref(waypoints) {
  if (waypoints.length < 2) {
    return "";
  }
  const start = waypoints[0];
  const destination = waypoints[waypoints.length - 1];
  const viaPoints = waypoints.slice(1, -1);
  const params = [
    "jm=1",
    "sort=tfc",
    `saddr=${encodeURIComponent(routeAmapPointValue(start))}`,
    `daddr=${encodeURIComponent(routeAmapPointValue(destination))}`
  ];
  if (viaPoints.length > 0) {
    params.push(`maddr=${encodeURIComponent(viaPoints.map((point) => routeAmapPointValue(point)).join("|"))}`);
  }
  params.push("src=mypage", "callnative=0", "innersrc=uriapi");
  return `https://m.amap.com/navigation/carmap/${params.join("&")}`;
}

function buildCollectedRoute(route, waypointMap, orderedNames, evidenceItems) {
  const waypoints = orderedNames.map((key) => waypointMap.get(key)).filter(Boolean);
  const navigationMode = routeNavigationMode(waypoints);
  const statusVariant = routeNavigationStatusVariant(navigationMode);
  return {
    route_slug: route.slug,
    route_title: route.title,
    collection_status: statusVariant,
    collection_notes: `OpenClaw 从 ${evidenceItems.length} 条抖音内容抽取并合并，建议人工核对后再回写 route_templates.json。`,
    source: {
      channel: "openclaw-douyin-video-analysis",
      reference_url: evidenceItems[0]?.source_url || "",
      operator: "openclaw-scheduled-task"
    },
    navigation: {
      provider: "amap",
      waypoints
    },
    missing_coordinate_waypoints: waypoints.filter((point) => !point.has_coordinates).map((point) => point.name),
    amap_export: {
      href: buildAmapExportHref(waypoints),
      is_available: waypoints.length >= 2,
      navigation_mode: navigationMode,
      status_variant: statusVariant,
      status_badge: routeNavigationStatusBadge(statusVariant),
      status_text: routeNavigationStatusText(waypoints, navigationMode),
      waypoint_text: waypoints.map((point) => point.name).join(" -> ")
    },
    evidence_items: evidenceItems
  };
}

async function run(runtime = {}) {
  const routes = await loadRouteTemplates();
  const collector = getCollector(runtime);
  if (typeof collector !== "function") {
    throw new Error("OpenClaw runtime must provide collect(task), runSearch(task), or search(task). ");
  }

  const routeMap = new Map(routes.map((route) => [route.slug, route]));
  const aggregated = new Map();

  for (const task of buildSearchTasks(routes)) {
    const route = routeMap.get(task.routeSlug);
    if (!route) {
      continue;
    }
    const payload = await collector(task);
    const rawItems = Array.isArray(payload) ? payload : Array.isArray(payload?.items) ? payload.items : [];

    for (const rawItem of rawItems) {
      const sourceUrl = extractText(rawItem, ["sourceUrl", "url", "link", "permalink", "videoUrl"]);
      if (!sourceUrl || !/douyin\.com|iesdouyin\.com/i.test(sourceUrl)) {
        continue;
      }

      const videoAnalysis = await analyzeRouteVideo(runtime, task, rawItem);
      const extractedWaypoints = extractWaypointsFromAnalysis(rawItem, videoAnalysis, task);
      if (extractedWaypoints.length < 2) {
        continue;
      }

      if (!aggregated.has(route.slug)) {
        aggregated.set(route.slug, {
          waypointMap: new Map(),
          orderedNames: [],
          evidenceItems: [],
          sourceUrls: new Set()
        });
      }

      const bucket = aggregated.get(route.slug);
      for (const waypoint of extractedWaypoints) {
        mergeWaypointIntoMap(bucket.waypointMap, bucket.orderedNames, waypoint, sourceUrl);
      }

      if (!bucket.sourceUrls.has(sourceUrl)) {
        bucket.sourceUrls.add(sourceUrl);
        bucket.evidenceItems.push({
          keyword: task.keyword,
          source_url: sourceUrl,
          owner: extractText(rawItem, ["owner", "author", "creator", "nickname"]),
          title: extractText(rawItem, ["title", "name", "poiName"]),
          summary: extractText(rawItem, ["summary", "description", "excerpt", "content"]),
          extracted_waypoints: extractedWaypoints.map((item) => item.name),
          transcript_excerpt: flattenVideoAnalysisText(videoAnalysis).slice(0, 4)
        });
      }
    }
  }

  const items = [];
  for (const route of routes) {
    const bucket = aggregated.get(route.slug);
    if (!bucket || bucket.orderedNames.length < 2) {
      continue;
    }
    items.push(buildCollectedRoute(route, bucket.waypointMap, bucket.orderedNames, bucket.evidenceItems));
  }

  const payload = {
    source: "openclaw-route-waypoints",
    exported_at: new Date().toISOString(),
    schedule: TASK_SPEC.schedule,
    items
  };

  await fs.mkdir(path.dirname(TASK_SPEC.outputPath), { recursive: true });
  await fs.writeFile(TASK_SPEC.outputPath, JSON.stringify(payload, null, 2) + "\n", "utf-8");
  return payload;
}

if (require.main === module) {
  run(globalThis.openclaw || {})
    .then((payload) => {
      console.log(`exported ${payload.items.length} route waypoint items -> ${TASK_SPEC.outputPath}`);
    })
    .catch((error) => {
      console.error(error instanceof Error ? error.message : String(error));
      process.exitCode = 1;
    });
}

module.exports = {
  TASK_SPEC,
  buildSearchTasks,
  run
};