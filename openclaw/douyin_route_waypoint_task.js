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
const DAY_PATTERN = /(?:(\d{1,2}(?:\.\d+)?)|([一二三四五六七八九十两]{1,3}))\s*(天|日)(?!气)/g;
const DISTANCE_PATTERN = /(?:(全程|总里程|里程|骑行|路线|往返|单程)?\s*)?(\d{2,4}(?:\.\d+)?)\s*(公里|km|KM|千米)/g;
const ROUTE_INFO_POSITIVE_HINTS = ["摩旅", "骑行", "路线", "路书", "高德", "全程", "总里程", "里程", "Day", "DAY", "第", "天路线", "天行程", "日路线"];
const DISTANCE_NEGATIVE_HINTS = ["时速", "海拔", "门票", "温度", "分钟", "秒", "油耗", "续航", "海里", "米", "码", "点赞", "评论"];
const DAY_NEGATIVE_HINTS = ["今天", "明天", "后天", "天气", "日期", "生日", "第1天之后", "第2天之后"];

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

function parseChineseNumber(value) {
  const text = String(value || "").trim();
  if (!text) {
    return null;
  }
  const direct = Number(text);
  if (Number.isFinite(direct)) {
    return direct;
  }

  const digits = { "零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9 };
  if (text === "十") {
    return 10;
  }
  if (text.endsWith("十")) {
    return (digits[text[0]] || 1) * 10;
  }
  if (text.includes("十")) {
    const [left, right] = text.split("十");
    return ((digits[left] || 1) * 10) + (digits[right] || 0);
  }
  return digits[text] ?? null;
}

function collectEvidenceEntries(route, evidenceItems) {
  const entries = [];
  const pushEntry = (text, source, baseScore) => {
    const normalized = String(text || "").trim();
    if (!normalized) {
      return;
    }
    entries.push({ text: normalized, source, baseScore });
  };

  pushEntry(extractText(route, ["title"]), "route-title", 6);
  pushEntry(extractText(route, ["summary"]), "route-summary", 5);

  for (const item of evidenceItems) {
    pushEntry(extractText(item, ["title"]), "evidence-title", 5);
    pushEntry(extractText(item, ["summary"]), "evidence-summary", 4);
    for (const excerpt of Array.isArray(item.transcript_excerpt) ? item.transcript_excerpt : []) {
      pushEntry(excerpt, "transcript", 2);
    }
  }

  const deduped = [];
  const seen = new Set();
  for (const entry of entries) {
    const key = `${entry.source}::${entry.text}`;
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    deduped.push(entry);
  }
  return deduped;
}

function scoreContext(text, index, positiveHints, negativeHints) {
  const start = Math.max(0, index - 12);
  const end = Math.min(text.length, index + 20);
  const window = text.slice(start, end);
  let score = 0;
  for (const hint of positiveHints) {
    if (window.includes(hint)) {
      score += 2;
    }
  }
  for (const hint of negativeHints) {
    if (window.includes(hint)) {
      score -= 3;
    }
  }
  return score;
}

function rankCandidates(candidates) {
  const grouped = new Map();
  for (const candidate of candidates) {
    const key = String(candidate.value);
    if (!grouped.has(key)) {
      grouped.set(key, { value: candidate.value, score: 0, hits: 0, evidence: [], sourceKinds: new Set() });
    }
    const bucket = grouped.get(key);
    bucket.score += candidate.score;
    bucket.hits += 1;
    bucket.evidence.push(candidate.evidence);
    bucket.sourceKinds.add(candidate.evidence.kind || candidate.evidence.source || "unknown");
  }

  const ranked = Array.from(grouped.values()).map((item) => ({
    ...item,
    totalScore: item.score + Math.max(0, item.hits - 1) * 2,
    sourceKindCount: item.sourceKinds.size,
    sourceKinds: Array.from(item.sourceKinds),
  }));
  ranked.sort((left, right) => right.totalScore - left.totalScore || right.hits - left.hits || right.value - left.value);
  return ranked;
}

function evidenceKindFromSource(source) {
  if (String(source || "").includes("title")) {
    return "title";
  }
  if (String(source || "").includes("summary")) {
    return "summary";
  }
  if (String(source || "").includes("transcript")) {
    return "transcript";
  }
  return "other";
}

function selectTopCandidate(candidates, minScore, fieldLabel) {
  const ranked = rankCandidates(candidates).filter((item) => item.totalScore >= minScore);
  if (!ranked.length) {
    return { value: null, confidence: 0, evidence: [], source_kinds: [], consistency_status: "missing", reason: `缺少明确${fieldLabel}` };
  }

  const top = ranked[0];
  const runnerUp = ranked[1] || null;
  const hasStrongConflict = Boolean(
    runnerUp
    && runnerUp.value !== top.value
    && runnerUp.totalScore >= Math.max(minScore, top.totalScore - 2)
  );
  const lacksCrossSourceSupport = top.sourceKindCount < 2;

  if (hasStrongConflict && lacksCrossSourceSupport) {
    return {
      value: null,
      confidence: 0,
      evidence: top.evidence.slice(0, 3),
      source_kinds: top.sourceKinds,
      consistency_status: "conflict",
      reason: `${fieldLabel}多来源冲突`
    };
  }

  return {
    value: top.value,
    confidence: top.totalScore,
    evidence: top.evidence.slice(0, 3),
    source_kinds: top.sourceKinds,
    consistency_status: top.sourceKindCount >= 2 ? "confirmed" : "single-source",
    reason: top.sourceKindCount >= 2 ? "" : `${fieldLabel}仅单来源命中`
  };
}

function deriveRouteDays(route, evidenceItems) {
  const evidenceEntries = collectEvidenceEntries(route, evidenceItems);
  const candidates = [];
  for (const entry of evidenceEntries) {
    for (const match of entry.text.matchAll(DAY_PATTERN)) {
      const number = Number(match[1]) || parseChineseNumber(match[2]);
      if (Number.isFinite(number) && number >= 1 && number <= 15) {
        const score = entry.baseScore + scoreContext(entry.text, match.index || 0, ROUTE_INFO_POSITIVE_HINTS, DAY_NEGATIVE_HINTS);
        candidates.push({
          value: number,
          score,
          evidence: { source: entry.source, kind: evidenceKindFromSource(entry.source), text: entry.text.slice(0, 80) }
        });
      }
    }
  }
  return selectTopCandidate(candidates, 4, "骑行天数");
}

function deriveRouteDistanceKm(route, evidenceItems) {
  const evidenceEntries = collectEvidenceEntries(route, evidenceItems);
  const candidates = [];
  for (const entry of evidenceEntries) {
    for (const match of entry.text.matchAll(DISTANCE_PATTERN)) {
      const value = Number(match[2]);
      if (!Number.isFinite(value) || value < 20 || value > 5000) {
        continue;
      }
      const prefixBonus = match[1] ? 3 : 0;
      const score = entry.baseScore + prefixBonus + scoreContext(entry.text, match.index || 0, ROUTE_INFO_POSITIVE_HINTS, DISTANCE_NEGATIVE_HINTS);
      candidates.push({
        value,
        score,
        evidence: { source: entry.source, kind: evidenceKindFromSource(entry.source), text: entry.text.slice(0, 80) }
      });
    }
  }
  return selectTopCandidate(candidates, 5, "骑行公里数");
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
  const amapHref = buildAmapExportHref(waypoints);
  const routeDays = deriveRouteDays(route, evidenceItems);
  const routeDistanceKm = deriveRouteDistanceKm(route, evidenceItems);
  const coordinateWaypointCount = waypoints.filter((point) => point.has_coordinates).length;
  const resolvableWaypointCount = waypoints.filter((point) => point.has_coordinates || point.name).length;
  const qualificationReasons = [];
  if (resolvableWaypointCount < 2) {
    qualificationReasons.push("可用于高德路线反推的位置点不足 2 个");
  }
  if (!amapHref) {
    qualificationReasons.push("无法生成高德路线");
  }
  const isQualified = qualificationReasons.length === 0;
  return {
    route_slug: route.slug,
    route_title: route.title,
    route_days: routeDays.value,
    route_days_confidence: routeDays.confidence,
    route_days_evidence: routeDays.evidence,
    route_days_source_kinds: routeDays.source_kinds,
    route_days_consistency_status: routeDays.consistency_status,
    route_distance_km: routeDistanceKm.value,
    route_distance_confidence: routeDistanceKm.confidence,
    route_distance_evidence: routeDistanceKm.evidence,
    route_distance_source_kinds: routeDistanceKm.source_kinds,
    route_distance_consistency_status: routeDistanceKm.consistency_status,
    waypoint_count: waypoints.length,
    coordinate_waypoint_count: coordinateWaypointCount,
    qualification_status: isQualified ? "qualified" : "rejected",
    qualification_reason: qualificationReasons.join("；"),
    is_qualified: isQualified,
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
      href: amapHref,
      is_available: Boolean(amapHref),
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
  let rejectedCount = 0;
  for (const route of routes) {
    const bucket = aggregated.get(route.slug);
    if (!bucket || bucket.orderedNames.length < 2) {
      continue;
    }
    const collectedRoute = buildCollectedRoute(route, bucket.waypointMap, bucket.orderedNames, bucket.evidenceItems);
    if (collectedRoute.is_qualified) {
      items.push(collectedRoute);
    } else {
      rejectedCount += 1;
    }
  }

  const payload = {
    source: "openclaw-route-waypoints",
    exported_at: new Date().toISOString(),
    schedule: TASK_SPEC.schedule,
    qualified_count: items.length,
    rejected_count: rejectedCount,
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