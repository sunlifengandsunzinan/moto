const { request, buildWebUrl } = require("../../../utils/request");
const {
  API_PATHS,
  MINI_PROGRAM_PATHS,
  getMiniProgramApiPath,
  getMiniProgramDownloadUrl,
  normalizeRequestPath,
  TENCENT_MAP_SUBKEY,
} = require("../../../utils/backend-config");
const { downloadRemoteFile } = require("../../../utils/file-download");

const IMPORT_PREFERENCE_STORAGE_KEY = "routeImportPreferredMapApp";
const ROUTE_DETAIL_SEED_STORAGE_PREFIX = "routeDetailSeed:v4:";
const ROUTE_DETAIL_CACHE_STORAGE_PREFIX = "routeDetailCache:v4:";
const WANT_GO_PLAN_OPTIONS = [
  { key: "this_month", label: "这个月" },
  { key: "next_month", label: "下个月" },
];

const SHARE_MENUS = ["shareAppMessage", "shareTimeline"];

function normalizeWantGoPlanLabel(planBucket) {
  const normalized = String(planBucket || "").trim();
  const matched = WANT_GO_PLAN_OPTIONS.find((item) => item.key === normalized);
  return matched ? `想去 · ${matched.label}` : "想去";
}

function hasLoggedWechatProfile(profile) {
  if (!profile || typeof profile !== "object") {
    return false;
  }

  const nickName = String(profile.nickName || "").trim();
  const avatarUrl = String(profile.avatarUrl || "").trim();
  return Boolean(nickName && avatarUrl && nickName !== "微信用户");
}

function getRouteDetailFallback() {
  return {
    page: {
      title: "路线详情暂不可用",
      eyebrow: "路线详情",
    },
    route: {
      title: "暂无可展示路线",
      days: 0,
      amap_export: {
        screenshot_href: "",
      },
    },
    detail_sections: {
      daily_plan: [],
    },
  };
}

function getRouteDetailSeedStorageKey(slug) {
  return `${ROUTE_DETAIL_SEED_STORAGE_PREFIX}${String(slug || "").trim()}`;
}

function getRouteDetailCacheStorageKey(slug) {
  return `${ROUTE_DETAIL_CACHE_STORAGE_PREFIX}${String(slug || "").trim()}`;
}

function readStoredValue(key) {
  if (!key) {
    return null;
  }

  try {
    return wx.getStorageSync(key) || null;
  } catch (_) {
    return null;
  }
}

function writeStoredValue(key, value) {
  if (!key) {
    return;
  }

  try {
    wx.setStorageSync(key, value);
  } catch (_) {
    // Ignore storage write failures.
  }
}

function buildSeedPayload(seedRoute) {
  if (!seedRoute || typeof seedRoute !== "object") {
    return null;
  }

  return {
    page: {
      title: String(seedRoute.title || "路线详情").trim() || "路线详情",
      eyebrow: "路线详情",
    },
    route: seedRoute,
    detail_sections: {
      daily_plan: Array.isArray(seedRoute.days_plan) ? seedRoute.days_plan : [],
      checkpoints: [],
      trip_advice: { title: "行途建议", comment: "", items: [], source_line: "" },
      linked_spots: [],
      navigation_import_assistant: {},
    },
  };
}

function readCachedRoutePayload(slug) {
  const normalizedSlug = String(slug || "").trim();
  if (!normalizedSlug) {
    return null;
  }

  const cachedPayload = readStoredValue(getRouteDetailCacheStorageKey(normalizedSlug));
  if (cachedPayload && typeof cachedPayload === "object" && cachedPayload.route) {
    return cachedPayload;
  }

  const seedWrapper = readStoredValue(getRouteDetailSeedStorageKey(normalizedSlug));
  if (seedWrapper && typeof seedWrapper === "object" && seedWrapper.route) {
    return buildSeedPayload(seedWrapper.route);
  }

  return null;
}

function normalizeCoordinatePoint(point) {
  const lng = Number(point?.lng);
  const lat = Number(point?.lat);
  if (!point?.has_coordinates || !Number.isFinite(lng) || !Number.isFinite(lat)) {
    return null;
  }

  return {
    name: String(point.name || "途径点"),
    longitude: lng,
    latitude: lat,
  };
}

function getRouteNavigationTarget(route) {
  const coordinatePoints = (route?.amap_export?.waypoints || [])
    .map(normalizeCoordinatePoint)
    .filter(Boolean);
  if (!coordinatePoints.length) {
    return null;
  }

  return coordinatePoints[coordinatePoints.length - 1];
}

function buildMarkerCallout(point, index, totalCount) {
  const isStart = index === 0;
  const isEnd = index === totalCount - 1;

  if (isStart) {
    return {
      content: "起点",
      bgColor: "#7AC943",
      color: "#111111",
    };
  }

  if (isEnd) {
    return {
      content: "终点",
      bgColor: "#FFB347",
      color: "#111111",
    };
  }

  return {
    content: `${index + 1}`,
    bgColor: "#37A8E0",
    color: "#FFFFFF",
  };
}

function findNearestPolylinePoint(targetPoint, polylinePoints) {
  if (!targetPoint || !Array.isArray(polylinePoints) || !polylinePoints.length) {
    return targetPoint;
  }

  let nearest = polylinePoints[0];
  let minDistance = Number.POSITIVE_INFINITY;

  for (const candidate of polylinePoints) {
    const dx = Number(candidate.longitude) - Number(targetPoint.longitude);
    const dy = Number(candidate.latitude) - Number(targetPoint.latitude);
    const distance = dx * dx + dy * dy;
    if (distance < minDistance) {
      minDistance = distance;
      nearest = candidate;
    }
  }

  return {
    ...targetPoint,
    longitude: Number(nearest.longitude),
    latitude: Number(nearest.latitude),
  };
}

function dedupePolylinePoints(points) {
  const source = Array.isArray(points) ? points : [];
  const normalized = [];

  for (const point of source) {
    const lng = Number(point?.longitude);
    const lat = Number(point?.latitude);
    if (!Number.isFinite(lng) || !Number.isFinite(lat)) {
      continue;
    }

    const previous = normalized[normalized.length - 1];
    if (previous && previous.longitude === lng && previous.latitude === lat) {
      continue;
    }

    normalized.push({ longitude: lng, latitude: lat });
  }

  return normalized;
}

function downsamplePolylinePoints(points, maxPoints = 900) {
  const source = Array.isArray(points) ? points : [];
  if (source.length <= maxPoints) {
    return source;
  }

  const result = [];
  const lastIndex = source.length - 1;
  const step = lastIndex / (maxPoints - 1);

  for (let index = 0; index < maxPoints; index += 1) {
    const sourceIndex = Math.round(index * step);
    result.push(source[Math.min(lastIndex, sourceIndex)]);
  }

  return dedupePolylinePoints(result);
}

function buildCheckpointMapMarkers(checkpointItems, routePolylinePoints, fallbackWaypointPoints) {
  const checkpoints = Array.isArray(checkpointItems) ? checkpointItems : [];
  if (!checkpoints.length) {
    return [];
  }

  const polylinePoints = Array.isArray(routePolylinePoints) ? routePolylinePoints : [];
  const waypointPoints = Array.isArray(fallbackWaypointPoints) ? fallbackWaypointPoints : [];
  const markerAnchors = polylinePoints.length >= 2 ? polylinePoints : waypointPoints;
  if (!markerAnchors.length) {
    return [];
  }

  const safeCheckpoints = checkpoints.slice(0, 20);
  return safeCheckpoints
    .map((checkpoint, index) => {
      const ratio = safeCheckpoints.length <= 1 ? 0 : (index / (safeCheckpoints.length - 1));
      const anchorIndex = Math.round(ratio * Math.max(markerAnchors.length - 1, 0));
      const anchor = markerAnchors[Math.min(anchorIndex, markerAnchors.length - 1)] || markerAnchors[0];
      const snappedAnchor = findNearestPolylinePoint(anchor, polylinePoints);
      const name = String(checkpoint?.name || `打卡点${index + 1}`).trim() || `打卡点${index + 1}`;
      const checkpointIndex = Number(checkpoint?.index || (index + 1));

      return {
        id: 1000 + index,
        longitude: Number(snappedAnchor?.longitude),
        latitude: Number(snappedAnchor?.latitude),
        width: 26,
        height: 34,
        anchor: { x: 0.5, y: 1 },
        zIndex: 16,
        callout: {
          content: `${checkpointIndex}. ${name}`,
          display: "ALWAYS",
          padding: 6,
          borderRadius: 8,
          bgColor: "#FFE4BF",
          color: "#4A2A00",
          fontSize: 10,
          textAlign: "center",
        },
      };
    })
    .filter((item) => Number.isFinite(item.longitude) && Number.isFinite(item.latitude));
}

function buildMapPayload(amapExport, checkpointItems = []) {
  const coordinatePoints = (amapExport?.waypoints || [])
    .map(normalizeCoordinatePoint)
    .filter(Boolean);
  const routedPolylinePoints = (amapExport?.preview_polyline_points || [])
    .map((point) => {
      const lng = Number(point?.lng ?? point?.longitude);
      const lat = Number(point?.lat ?? point?.latitude);
      if (!Number.isFinite(lng) || !Number.isFinite(lat)) {
        return null;
      }
      return { longitude: lng, latitude: lat };
    })
    .filter(Boolean);
  const safePolylinePoints = downsamplePolylinePoints(dedupePolylinePoints(routedPolylinePoints), 900);
  const hasRoadPolyline = safePolylinePoints.length >= 2;
  const fallbackPolylinePoints = !hasRoadPolyline && coordinatePoints.length >= 2
    ? coordinatePoints.map((point) => ({ longitude: point.longitude, latitude: point.latitude }))
    : [];
  const visiblePolylinePoints = hasRoadPolyline ? safePolylinePoints : fallbackPolylinePoints;

  const markerPoints = coordinatePoints;

  if (!coordinatePoints.length) {
    return {
      preview_available: false,
      center: { longitude: 0, latitude: 0 },
      include_points: [],
      markers: [],
      polyline: [],
      scale: 8,
    };
  }

  const includePoints = coordinatePoints.map((point) => ({
    longitude: point.longitude,
    latitude: point.latitude,
  }));
  const usingFallbackPolyline = !hasRoadPolyline && visiblePolylinePoints.length >= 2;
  const checkpointMarkers = buildCheckpointMapMarkers(
    checkpointItems,
    visiblePolylinePoints,
    coordinatePoints,
  );
  const mapMarkers = checkpointMarkers.length
    ? checkpointMarkers
    : markerPoints.map((point, index) => {
      const callout = buildMarkerCallout(point, index, markerPoints.length);
      return {
        id: index + 1,
        longitude: point.longitude,
        latitude: point.latitude,
        width: 28,
        height: 36,
        anchor: { x: 0.5, y: 1 },
        zIndex: index === 0 || index === markerPoints.length - 1 ? 20 : 10,
        callout: {
          content: callout.content,
          display: "ALWAYS",
          padding: 6,
          borderRadius: 8,
          bgColor: callout.bgColor,
          color: callout.color,
          fontSize: 11,
          textAlign: "center",
        },
      };
    });

  return {
    // Keep the real map visible for locked routes even when road polyline is intentionally hidden.
    preview_available: markerPoints.length >= 1,
    has_road_polyline: hasRoadPolyline,
    using_fallback_polyline: usingFallbackPolyline,
    center: {
      longitude: markerPoints[0].longitude,
      latitude: markerPoints[0].latitude,
    },
    include_points: markerPoints.map((point) => ({
      longitude: point.longitude,
      latitude: point.latitude,
    })),
    markers: mapMarkers,
    polyline: visiblePolylinePoints.length >= 2
      ? [{
          points: visiblePolylinePoints,
          color: usingFallbackPolyline ? "#B98B4A" : "#1372CF",
          width: 8,
          dottedLine: usingFallbackPolyline,
          arrowLine: false,
          borderColor: "#FFFFFF",
          borderWidth: 2,
        }]
      : [],
    scale: coordinatePoints.length >= 4 ? 8 : 10,
  };
}

function buildOverviewStats(route) {
  const distance = Number(route?.distance_km || 0);
  const estimatedHours = distance > 0 ? Math.max(1, Math.round(distance / 55)) : 0;
  const engagement = route?.engagement || {};

  return [
    { key: "distance", label: "里程", value: distance > 0 ? `${distance}km` : "--" },
    { key: "duration", label: "时长", value: estimatedHours > 0 ? `${estimatedHours}H` : "--" },
    { key: "points", label: "积分", value: `${Number(engagement.total_count || 0)}` },
    { key: "reward", label: "跑完奖励积分", value: `${Number(engagement.favorite_count || 0)}` },
  ];
}

function normalizeConfiguredCheckpoints(checkpoints) {
  const sourceItems = Array.isArray(checkpoints) ? checkpoints : [];
  return sourceItems
    .map((item, index) => {
      const name = String(item?.name || item?.title || `打卡点${index + 1}`).trim();
      const timing = String(item?.timing || item?.duration_text || "").trim();
      const summary = String(item?.summary || item?.score_text || "").trim();
      const distanceText = String(item?.distance_text || item?.distance || "后台维护").trim() || "后台维护";
      const hitCount = Math.max(0, Number(item?.hit_count || 0));
      const hitCountText = `${hitCount}人打过卡`;

      return {
        index: index + 1,
        name,
        score_text: summary || "可获得打卡积分0点",
        distance_text: distanceText,
        duration_text: timing,
        hit_count: hitCount,
        hit_count_text: hitCountText,
        is_last: index === sourceItems.length - 1,
      };
    })
    .filter((item) => item.name);
}

function buildCheckpointTimeline(route, dailyPlan, configuredCheckpoints) {
  const normalizedCheckpoints = normalizeConfiguredCheckpoints(configuredCheckpoints);
  if (normalizedCheckpoints.length) {
    return normalizedCheckpoints;
  }

  const waypoints = Array.isArray(route?.amap_export?.waypoints) ? route.amap_export.waypoints : [];
  const routeDistance = Number(route?.distance_km || 0);
  if (waypoints.length) {
    const segmentDistance = waypoints.length > 1
      ? Math.max(1, Math.round(routeDistance / (waypoints.length - 1)))
      : Math.max(1, routeDistance || 1);
    return waypoints.map((waypoint, index) => ({
      index: index + 1,
      name: String(waypoint?.name || `打卡点${index + 1}`),
      score_text: "可获得打卡积分0点",
      distance_text: index === 0 ? "起点" : `${segmentDistance}km`,
      duration_text: index === 0 ? "" : `00小时${String(10 + index * 2).padStart(2, "0")}分钟`,
      hit_count: 0,
      hit_count_text: "0人打过卡",
      is_last: index === waypoints.length - 1,
    }));
  }

  const fallbackDailyPlan = Array.isArray(dailyPlan) ? dailyPlan : [];
  if (!fallbackDailyPlan.length) {
    return [];
  }

  return fallbackDailyPlan.map((day, index) => ({
    index: index + 1,
    name: String(day?.title || `打卡点${index + 1}`),
    score_text: "可获得打卡积分0点",
    distance_text: String(day?.distance || "--"),
    duration_text: String(day?.ride_time || ""),
    hit_count: 0,
    hit_count_text: "0人打过卡",
    is_last: index === fallbackDailyPlan.length - 1,
  }));
}

function normalizeLinkedSpots(linkedSpots) {
  const sourceItems = Array.isArray(linkedSpots) ? linkedSpots : [];
  return sourceItems.map((spot) => {
    const coordinates = spot && typeof spot.coordinates === "object" ? spot.coordinates : {};
    const sourceList = Array.isArray(spot?.sources) ? spot.sources : [];
    return {
      slug: String(spot?.slug || ""),
      name: String(spot?.name || "未命名点位"),
      summary: String(spot?.summary || ""),
      image_url: String(spot?.image_url || ""),
      support_tags: Array.isArray(spot?.support_tags) ? spot.support_tags.filter((item) => String(item || "").trim()) : [],
      coordinates_text: String(coordinates?.text || "未维护坐标"),
      source_items: sourceList.map((item) => ({
        type: String(item?.type || ""),
        name: String(item?.name || ""),
        note: String(item?.note || ""),
        verified: Boolean(item?.verified),
      })),
    };
  });
}

function detectPlatformKey() {
  try {
    const platform = String(wx.getSystemInfoSync()?.platform || "").toLowerCase();
    if (platform.includes("ios")) {
      return "ios";
    }
    if (platform.includes("android")) {
      return "android";
    }
  } catch (_) {
    // Fall back to general steps.
  }
  return "general";
}

function normalizeImportAssistant(assistantPayload, route) {
  const payload = assistantPayload && typeof assistantPayload === "object" ? assistantPayload : {};
  const mapApps = Array.isArray(payload.map_apps)
    ? payload.map_apps
      .map((item) => ({
        key: String(item?.key || "").trim(),
        label: String(item?.label || "").trim(),
        description: String(item?.description || "").trim(),
        platform_steps: item?.platform_steps && typeof item.platform_steps === "object"
          ? item.platform_steps
          : {},
      }))
      .filter((item) => item.key)
    : [];

  const troubleshootingPayload = payload.troubleshooting && typeof payload.troubleshooting === "object"
    ? payload.troubleshooting
    : {};

  const defaultMapApp = String(payload.default_map_app || "").trim();
  return {
    enabled: Boolean(payload.enabled && route?.gpx?.is_available),
    title: String(payload.title || "导入助手").trim(),
    subtitle: String(payload.subtitle || "已下载 GPX，按你常用地图继续导入导航。").trim(),
    primary_button_label: String(payload.primary_button_label || "下载到地图导航").trim(),
    helper_entry_label: String(payload.helper_entry_label || "不会导入？").trim(),
    default_map_app: mapApps.some((item) => item.key === defaultMapApp)
      ? defaultMapApp
      : (mapApps[0]?.key || ""),
    preferred_map_app: String(payload.preferred_map_app || "").trim(),
    troubleshooting: {
      title: String(troubleshootingPayload.title || "常见问题").trim(),
      items: Array.isArray(troubleshootingPayload.items)
        ? troubleshootingPayload.items.map((item) => String(item || "").trim()).filter(Boolean)
        : [],
    },
    map_apps: mapApps,
  };
}

function resolveMapAppSteps(mapApp, platformKey) {
  if (!mapApp || typeof mapApp !== "object") {
    return [];
  }
  const stepsByPlatform = mapApp.platform_steps && typeof mapApp.platform_steps === "object"
    ? mapApp.platform_steps
    : {};
  const directSteps = Array.isArray(stepsByPlatform[platformKey]) ? stepsByPlatform[platformKey] : [];
  if (directSteps.length) {
    return directSteps;
  }
  const fallbackSteps = Array.isArray(stepsByPlatform.general) ? stepsByPlatform.general : [];
  return fallbackSteps;
}

function resolvePreferredMapApp(mapApps, fallbackKey) {
  const preferredKey = String(wx.getStorageSync(IMPORT_PREFERENCE_STORAGE_KEY) || "").trim();
  if (preferredKey && mapApps.some((item) => item.key === preferredKey)) {
    return preferredKey;
  }
  if (fallbackKey && mapApps.some((item) => item.key === fallbackKey)) {
    return fallbackKey;
  }
  return mapApps[0]?.key || "";
}

function resolveMapAppView(importAssistant, selectedMapAppKey, platformKey) {
  const mapApps = Array.isArray(importAssistant?.map_apps) ? importAssistant.map_apps : [];
  const selectedMapApp = mapApps.find((item) => item.key === selectedMapAppKey) || mapApps[0] || null;
  return {
    selectedMapApp,
    selectedSteps: resolveMapAppSteps(selectedMapApp, platformKey),
  };
}

function resolveDirectNavigationOptions(route) {
  const amapUrl = resolveManualNavigationUrl(route, "amap");
  return [
    {
      key: "amap",
      label: "高德地图",
      url: "",
      manualUrl: amapUrl,
      isAvailable: Boolean(amapUrl),
    },
  ];
}

function buildTencentWebRouteUrlFromWaypoints(route) {
  const coordinatePoints = (route?.amap_export?.waypoints || [])
    .map(normalizeCoordinatePoint)
    .filter(Boolean);
  if (coordinatePoints.length < 2) {
    return "";
  }

  const start = coordinatePoints[0];
  const destination = coordinatePoints[coordinatePoints.length - 1];
  const viaPoints = coordinatePoints.slice(1, -1);
  const params = [
    `type=${encodeURIComponent("drive")}`,
    `from=${encodeURIComponent(start.name || "起点")}`,
    `fromcoord=${encodeURIComponent(`${start.latitude},${start.longitude}`)}`,
    `to=${encodeURIComponent(destination.name || "终点")}`,
    `tocoord=${encodeURIComponent(`${destination.latitude},${destination.longitude}`)}`,
    `policy=${encodeURIComponent("0")}`,
    `referer=${encodeURIComponent("xingtu")}`,
  ];

  if (viaPoints.length) {
    const viaNames = viaPoints
      .map((point) => String(point.name || "途径点").trim() || "途径点")
      .join(";");
    const viaCoords = viaPoints
      .map((point) => `${point.latitude},${point.longitude}`)
      .join(";");
    const encodedViaNames = encodeURIComponent(viaNames);
    const encodedViaCoords = encodeURIComponent(viaCoords);
    params.push(`via=${encodedViaNames}`);
    params.push(`viacoord=${encodedViaCoords}`);
    params.push(`waypoints=${encodedViaCoords}`);
    params.push(`waypointcoords=${encodedViaCoords}`);
  }

  return `https://apis.map.qq.com/uri/v1/routeplan?${params.join("&")}`;
}

function resolveManualNavigationUrl(route, mapKey) {
  if (mapKey === "tencent") {
    return String(
      route?.tencent_export?.app_href
      || route?.tencent_export?.href
      || buildTencentWebRouteUrlFromWaypoints(route)
      || "",
    ).trim();
  }
  return String(route?.amap_export?.app_href || route?.amap_export?.href || route?.amap_export?.browser_href || "").trim();
}

function resolveCopyableNavigationUrl(route, mapKey) {
  if (mapKey === "tencent") {
    return String(
      route?.tencent_export?.href
      || buildTencentWebRouteUrlFromWaypoints(route)
      || route?.tencent_export?.app_href
      || "",
    ).trim();
  }

  return String(route?.amap_export?.app_href || "").trim();
}

function buildWaypointSummary(route) {
  const waypoints = Array.isArray(route?.amap_export?.waypoints) ? route.amap_export.waypoints : [];
  const names = waypoints
    .map((point) => String(point?.name || "").trim())
    .filter(Boolean)
    .slice(0, 18);
  return names.join(" -> ");
}

function buildRouteSharePayload(route, fallbackSlug) {
  const title = String(route?.title || "摩旅路线").trim() || "摩旅路线";
  const slug = String(route?.slug || fallbackSlug || "").trim();
  const days = Number(route?.days || 0);
  const distanceText = String(route?.distance_text || route?.distance || "").trim();
  const titleSuffix = days > 0 ? ` · ${days}天` : distanceText ? ` · ${distanceText}` : "";
  const path = slug ? MINI_PROGRAM_PATHS.routeDetail(slug) : MINI_PROGRAM_PATHS.routesTab;
  const query = slug ? `slug=${encodeURIComponent(slug)}` : "";

  return {
    title: `${title}${titleSuffix}`,
    path,
    query,
  };
}

function normalizeRouteCollection(route, checkpointTimeline) {
  const sourceCollection = route?.collection && typeof route.collection === "object"
    ? route.collection
    : {};
  const fallbackTotal = Array.isArray(checkpointTimeline) ? checkpointTimeline.length : 0;
  const checkpointTotal = Math.max(0, Number(sourceCollection.checkpoint_total || fallbackTotal || 0));
  const checkedIndexes = Array.isArray(sourceCollection.checked_indexes)
    ? sourceCollection.checked_indexes
      .map((value) => Number(value))
      .filter((value) => Number.isFinite(value) && value > 0)
    : [];
  const checkedIndexSet = new Set(checkedIndexes);
  const checkedCount = checkedIndexSet.size;
  const completionPercent = checkpointTotal > 0
    ? Math.min(100, Math.round((checkedCount / checkpointTotal) * 100))
    : 0;
  const isCompleted = checkpointTotal > 0 && checkedCount >= checkpointTotal;
  const badge = sourceCollection.badge && typeof sourceCollection.badge === "object"
    ? sourceCollection.badge
    : {};

  return {
    ...sourceCollection,
    checkpoint_total: checkpointTotal,
    checked_indexes: [...checkedIndexSet].sort((left, right) => left - right),
    checked_count: checkedCount,
    completion_percent: completionPercent,
    is_completed: isCompleted,
    has_badge: Boolean(sourceCollection.has_badge || badge.awarded_at),
    badge,
  };
}

function applyCheckpointCollection(timeline, collection) {
  const sourceItems = Array.isArray(timeline) ? timeline : [];
  const checkedSet = new Set(Array.isArray(collection?.checked_indexes) ? collection.checked_indexes : []);
  return sourceItems.map((item) => ({
    ...item,
    is_checked: checkedSet.has(Number(item.index || 0)),
  }));
}

function normalizePayload(payload) {
  const route = payload?.route || {};
  const amapExport = route.amap_export || {};
  const slug = String(route.slug || "").trim();
  const dailyPlan = payload?.detail_sections?.daily_plan || [];
  const configuredCheckpoints = normalizeConfiguredCheckpoints(payload?.detail_sections?.checkpoints || []);
  const checkpointTimeline = buildCheckpointTimeline(route, dailyPlan, configuredCheckpoints);
  const safeCheckpointTimeline = checkpointTimeline.length
    ? checkpointTimeline
    : normalizeConfiguredCheckpoints(payload?.detail_sections?.checkpoints || []);
  const mapPayload = buildMapPayload(amapExport, safeCheckpointTimeline);
  const previewPolylineStatus = String(amapExport?.preview_polyline_status || "").trim();
  const shouldShowPolylineNotice = Boolean(
    mapPayload.preview_available
      && !mapPayload.has_road_polyline
      && mapPayload.markers.length >= 2,
  );
  const polylineHintText = shouldShowPolylineNotice
    ? (mapPayload.using_fallback_polyline
      ? `当前路线暂无道路折线，已用途经点连线做示意。`
      : `当前路线暂无道路折线，已显示地图标记。`)
    : "";

  const normalizedRoute = {
    ...route,
    tencentMapSubkey: TENCENT_MAP_SUBKEY,
    slug,
    is_favorite: Boolean(route.is_favorite),
    favorite_api_href: String(route.favorite_api_href || ""),
    navigation_api_href: String(route.navigation_api_href || ""),
    mini_program: {
      favorite: null,
      navigation: null,
      want_go: null,
      ...((route && route.mini_program) || {}),
    },
    engagement: {
      favorite_count: 0,
      navigation_count: 0,
      total_count: 0,
      want_go_count: 0,
      ...(route.engagement || {}),
    },
    want_go: {
      plan_bucket: "",
      total_count: 0,
      this_month_count: 0,
      next_month_count: 0,
      later_count: 0,
      ...(route.want_go || {}),
    },
    gpx: {
      is_available: false,
      filename: "",
      download_href: "",
      download_label: "GPX 文件下载",
      source_badge: "",
      source_title: "",
      meta_text: "",
      facts: [],
      mini_program: {
        download: null,
      },
      ...(route.gpx || {}),
    },
    amap_export: {
      ...amapExport,
      mini_program: {
        navigate: null,
        launch: null,
        browser: null,
        interactive_map: null,
        ...((amapExport && amapExport.mini_program) || {}),
      },
      map_preview_available: mapPayload.preview_available,
      map_has_road_polyline: mapPayload.has_road_polyline,
      map_center: mapPayload.center,
      map_include_points: mapPayload.include_points,
      map_markers: mapPayload.markers,
      map_polyline: mapPayload.polyline,
      map_scale: mapPayload.scale,
      map_polyline_notice: "",
      map_polyline_hint: polylineHintText,
      screenshot_url: amapExport.screenshot_href ? buildWebUrl(amapExport.screenshot_href) : "",
    },
    tencent_export: {
      is_available: false,
      href: "",
      app_href: "",
      mini_program: {
        navigate: null,
      },
      ...(route.tencent_export || {}),
    },
  };

  const normalizedCollection = normalizeRouteCollection(normalizedRoute, safeCheckpointTimeline);
  normalizedRoute.collection = normalizedCollection;

  return {
    page: payload?.page || { title: route.title || "路线详情", eyebrow: "路线详情" },
    route: normalizedRoute,
    detail_sections: {
      daily_plan: dailyPlan,
      checkpoints: configuredCheckpoints,
      trip_advice: payload?.detail_sections?.trip_advice || { title: "行途建议", comment: "", items: [], source_line: "" },
      linked_spots: normalizeLinkedSpots(payload?.detail_sections?.linked_spots || []),
      navigation_import_assistant: normalizeImportAssistant(payload?.detail_sections?.navigation_import_assistant || {}, normalizedRoute),
    },
    overview_stats: buildOverviewStats(normalizedRoute),
    checkpoint_timeline: applyCheckpointCollection(safeCheckpointTimeline, normalizedCollection),
    want_go_action_label: normalizeWantGoPlanLabel(normalizedRoute?.want_go?.plan_bucket),
  };
}

Page({
  data: {
    loading: true,
    error: "",
    page: { title: "路线详情", eyebrow: "路线详情" },
    route: {
      title: "",
      days: 0,
      tencentMapSubkey: TENCENT_MAP_SUBKEY,
      amap_export: {
        screenshot_url: "",
        map_preview_available: false,
        map_has_road_polyline: false,
        map_center: { longitude: 0, latitude: 0 },
        map_include_points: [],
        map_markers: [],
        map_polyline: [],
        map_scale: 8,
        map_polyline_notice: "",
      },
    },
    detailSections: { daily_plan: [], trip_advice: { title: "行途建议", comment: "", items: [], source_line: "" } },
    overviewStats: [],
    checkpointTimeline: [],
    routeCollection: {
      checkpoint_total: 0,
      checked_count: 0,
      completion_percent: 0,
      checked_indexes: [],
      is_completed: false,
      has_badge: false,
      badge: {},
    },
    linkedSpots: [],
    primaryMapActionLabel: "复制到浏览器",
    wantGoActionLabel: "想去",
    showImportAssistant: false,
    showImportTroubleshooting: false,
    importAssistant: {
      enabled: false,
      title: "导入助手",
      subtitle: "",
      helper_entry_label: "不会导入？",
      troubleshooting: { title: "常见问题", items: [] },
      map_apps: [],
      default_map_app: "",
    },
    selectedImportMapAppKey: "",
    selectedImportMapApp: null,
    selectedImportSteps: [],
    importDownloadStatus: "idle",
    importDownloadMessage: "",
    downloadedGpxPath: "",
    runtimePlatformKey: "general",
    preparingBadgeShare: false,
  },

  onLoad(options) {
    const slug = decodeURIComponent(options.slug || options.routeSlug || options.id || "");
    this.slug = slug;
    this.runtimePlatformKey = detectPlatformKey();
    this.enableNativeSharing();

    const cachedPayload = readCachedRoutePayload(slug);
    if (cachedPayload) {
      this.applyNormalizedData(normalizePayload(cachedPayload), true);
    }

    this.fetchData(slug);
  },

  onShow() {
    this.enableNativeSharing();
  },

  enableNativeSharing() {
    if (typeof wx.showShareMenu !== "function") {
      return;
    }

    try {
      wx.showShareMenu({
        menus: SHARE_MENUS,
      });
    } catch (_) {
      // Ignore share menu capability mismatches across client versions.
    }
  },

  onShareAppMessage() {
    const sharePayload = buildRouteSharePayload(this.data.route || {}, this.slug);
    const routeCollection = this.data.routeCollection || {};
    const badge = routeCollection.badge && typeof routeCollection.badge === "object"
      ? routeCollection.badge
      : {};
    const routeTitle = String(this.data.route?.title || "摩旅路线").trim() || "摩旅路线";
    const shareTitle = this.data.preparingBadgeShare && routeCollection.is_completed
      ? String(badge.share_text || `我已完成 ${routeTitle} 全部打卡点，解锁路线徽章！`).trim()
      : sharePayload.title;
    const imageUrl = this.data.preparingBadgeShare
      ? String(this.data.route?.amap_export?.screenshot_url || "").trim()
      : "";
    if (this.data.preparingBadgeShare) {
      this.setData({ preparingBadgeShare: false });
    }
    return {
      title: shareTitle,
      path: sharePayload.path,
      imageUrl,
    };
  },

  onShareTimeline() {
    const sharePayload = buildRouteSharePayload(this.data.route || {}, this.slug);
    const routeCollection = this.data.routeCollection || {};
    const badge = routeCollection.badge && typeof routeCollection.badge === "object"
      ? routeCollection.badge
      : {};
    const routeTitle = String(this.data.route?.title || "摩旅路线").trim() || "摩旅路线";
    const shareTitle = this.data.preparingBadgeShare && routeCollection.is_completed
      ? String(badge.share_text || `我已完成 ${routeTitle} 全部打卡点，解锁路线徽章！`).trim()
      : sharePayload.title;
    if (this.data.preparingBadgeShare) {
      this.setData({ preparingBadgeShare: false });
    }
    return {
      title: shareTitle,
      query: sharePayload.query,
    };
  },

  onPullDownRefresh() {
    this.fetchData(this.slug, true);
  },

  applyNormalizedData(normalized, keepLoading = false) {
    if (!normalized || typeof normalized !== "object") {
      return;
    }

    const importAssistant = normalized.detail_sections.navigation_import_assistant || {
      enabled: false,
      map_apps: [],
      default_map_app: "",
      preferred_map_app: "",
      helper_entry_label: "不会导入？",
      troubleshooting: { title: "常见问题", items: [] },
    };
    const selectedImportMapAppKey = resolvePreferredMapApp(
      importAssistant.map_apps || [],
      importAssistant.preferred_map_app || importAssistant.default_map_app || "",
    );
    const importView = resolveMapAppView(importAssistant, selectedImportMapAppKey, this.runtimePlatformKey || "general");

    this.setData({
      loading: keepLoading,
      page: normalized.page,
      route: normalized.route,
      detailSections: normalized.detail_sections,
      overviewStats: normalized.overview_stats,
      checkpointTimeline: normalized.checkpoint_timeline,
      routeCollection: normalized.route.collection || this.data.routeCollection,
      linkedSpots: normalized.detail_sections.linked_spots || [],
      primaryMapActionLabel: "复制到浏览器",
      wantGoActionLabel: normalized.want_go_action_label,
      importAssistant,
      selectedImportMapAppKey,
      selectedImportMapApp: importView.selectedMapApp,
      selectedImportSteps: importView.selectedSteps,
      showImportAssistant: false,
      showImportTroubleshooting: false,
      importDownloadStatus: "idle",
      importDownloadMessage: "",
      downloadedGpxPath: "",
      runtimePlatformKey: this.runtimePlatformKey || "general",
    });
  },

  fetchData(slug, stopRefresh = false) {
    if (!slug) {
      this.useFallback("", stopRefresh);
      return;
    }

    this.setData({ loading: true, error: "" });

    request({
      path: API_PATHS.routeDetail(slug),
      data: { _t: Date.now() },
    })
      .then((payload) => {
        const normalized = normalizePayload(payload);
        writeStoredValue(getRouteDetailCacheStorageKey(slug), payload);
        this.applyNormalizedData(normalized, false);
      })
      .catch((error) => {
        console.warn("[route-detail] request failed", {
          slug,
          error: error && error.message ? error.message : error,
        });
        const cachedPayload = readCachedRoutePayload(slug);
        if (cachedPayload) {
          this.applyNormalizedData(normalizePayload(cachedPayload), false);
          return;
        }

        this.useFallback(slug, stopRefresh, false);
      })
      .finally(() => {
        if (stopRefresh) {
          wx.stopPullDownRefresh();
        }
      });
  },

  useFallback(slug, stopRefresh = false, setLoading = true) {
    const fallback = normalizePayload(getRouteDetailFallback(slug));
    this.setData({
      loading: false,
      error: "",
      page: fallback.page,
      route: fallback.route,
      detailSections: fallback.detail_sections,
      overviewStats: fallback.overview_stats,
      checkpointTimeline: fallback.checkpoint_timeline,
      routeCollection: fallback.route.collection || this.data.routeCollection,
      linkedSpots: fallback.detail_sections.linked_spots || [],
      primaryMapActionLabel: "复制到浏览器",
      wantGoActionLabel: fallback.want_go_action_label,
      importAssistant: {
        enabled: false,
        title: "导入助手",
        subtitle: "",
        helper_entry_label: "不会导入？",
        troubleshooting: { title: "常见问题", items: [] },
        map_apps: [],
        default_map_app: "",
        preferred_map_app: "",
      },
      selectedImportMapAppKey: "",
      selectedImportMapApp: null,
      selectedImportSteps: [],
      showImportAssistant: false,
      showImportTroubleshooting: false,
      importDownloadStatus: "idle",
      importDownloadMessage: "",
      downloadedGpxPath: "",
    });

    if (!stopRefresh && setLoading) {
      wx.showToast({
        title: "已切换本地演示详情",
        icon: "none",
        duration: 1800,
      });
    }
  },

  handleBack() {
    const pages = getCurrentPages();
    if (pages.length > 1) {
      wx.navigateBack();
      return;
    }

    wx.switchTab({
      url: MINI_PROGRAM_PATHS.routesTab,
    });
  },

  trackNavigationEngagement(route) {
    const navigationPath = getMiniProgramApiPath(route?.mini_program?.navigation)
      || normalizeRequestPath(route?.navigation_api_href || "");
    if (!navigationPath) {
      return;
    }

    request({ path: navigationPath, method: "POST" })
      .then((payload) => {
        if (payload && payload.ok && payload.engagement) {
          const nextRoute = {
            ...this.data.route,
            engagement: {
              ...(this.data.route.engagement || {}),
              ...payload.engagement,
            },
          };
          const nextCheckpointTimeline = applyCheckpointCollection(
            buildCheckpointTimeline(nextRoute, this.data.detailSections.daily_plan, this.data.detailSections.checkpoints),
            this.data.routeCollection,
          );
          this.setData({
            route: nextRoute,
            overviewStats: buildOverviewStats(nextRoute),
            checkpointTimeline: nextCheckpointTimeline,
          });
        }
      })
      .catch(() => {});
  },

  handleDirectNavigate(mapKey = "amap") {
    const route = this.data.route || {};
    const navigationOptions = resolveDirectNavigationOptions(route);
    const selectedOption = navigationOptions.find((item) => item.key === mapKey);
    const manualUrl = selectedOption?.manualUrl || resolveCopyableNavigationUrl(route, mapKey);

    if (manualUrl) {
      this.trackNavigationEngagement(route);
      this.copyNavigationLinkForManualOpen(mapKey, true);
      return;
    }

    if (selectedOption) {
      wx.showToast({ title: `${selectedOption.label}链接暂不可用`, icon: "none" });
      return;
    }
    wx.showToast({ title: "当前路线缺少高德链接", icon: "none" });
  },

  copyNavigationLinkForManualOpen(mapKey = "amap", showFeedback = true) {
    const route = this.data.route || {};
    const manualUrl = resolveCopyableNavigationUrl(route, mapKey);
    if (!manualUrl) {
      return;
    }

    wx.setClipboardData({
      data: manualUrl,
      success: () => {
        if (!showFeedback) {
          return;
        }
        wx.showToast({
          title: "高德链接已复制",
          icon: "none",
          duration: 1800,
        });
      },
    });
  },

  handlePrimaryMapAction() {
    if (!this.ensureLoggedInForRouteAction()) {
      return;
    }

    this.handleDirectNavigate("amap");
  },

  handleCheckpointCheckin(event) {
    if (!this.ensureLoggedInForRouteAction()) {
      return;
    }

    const route = this.data.route || {};
    const slug = String(route.slug || "").trim();
    const checkpointIndex = Number(event?.currentTarget?.dataset?.index || 0);
    if (!slug || !Number.isFinite(checkpointIndex) || checkpointIndex <= 0) {
      return;
    }

    const existingCheckedSet = new Set(Array.isArray(this.data.routeCollection?.checked_indexes) ? this.data.routeCollection.checked_indexes : []);
    if (existingCheckedSet.has(checkpointIndex)) {
      wx.showToast({ title: "该打卡点已完成", icon: "none" });
      return;
    }

    request({
      path: API_PATHS.routeCheckpointCheckin(slug, checkpointIndex),
      method: "POST",
    })
      .then((payload) => {
        if (!payload?.ok) {
          wx.showToast({ title: String(payload?.error || "打卡失败，请重试"), icon: "none" });
          return;
        }

        const nextCollection = normalizeRouteCollection(
          {
            ...(this.data.route || {}),
            collection: payload.collection || {},
          },
          this.data.checkpointTimeline,
        );
        const nextTimeline = applyCheckpointCollection(this.data.checkpointTimeline, nextCollection)
          .map((item) => {
            if (Number(item?.index || 0) !== checkpointIndex) {
              return item;
            }
            const nextHitCount = Math.max(0, Number(item?.hit_count || 0)) + 1;
            return {
              ...item,
              hit_count: nextHitCount,
              hit_count_text: `${nextHitCount}人打过卡`,
            };
          });
        const nextRoute = {
          ...this.data.route,
          collection: nextCollection,
        };

        this.setData({
          route: nextRoute,
          routeCollection: nextCollection,
          checkpointTimeline: nextTimeline,
        });

        if (payload.badge_unlocked) {
          const clubHint = payload?.club_credit_awarded ? "你为俱乐部贡献了1个打卡点。" : "";
          wx.showModal({
            title: "徽章解锁",
            content: `${clubHint}${String(payload?.badge?.title || "路线征服者")}，现在可以分享海报啦。`,
            showCancel: false,
          });
          return;
        }

        const successTitle = payload?.club_credit_awarded ? "打卡成功，为俱乐部+1" : "打卡成功";
        wx.showToast({ title: successTitle, icon: "success" });
      })
      .catch((error) => {
        wx.showToast({
          title: String(error?.message || "打卡失败，请重试"),
          icon: "none",
          duration: 2200,
        });
      });
  },

  handlePrepareBadgeShare() {
    this.setData({ preparingBadgeShare: true });
  },

  ensureLoggedInForRouteAction() {
    const app = getApp();
    const profile = typeof app?.getWechatUserProfile === "function"
      ? app.getWechatUserProfile()
      : null;

    if (hasLoggedWechatProfile(profile)) {
      return true;
    }

    wx.showToast({ title: "请先去我的页面登录", icon: "none", duration: 1800 });
    return false;
  },

  handleOpenImportAssistant() {
    if (!this.ensureLoggedInForRouteAction()) {
      return;
    }

    const importAssistant = this.data.importAssistant || {};
    const mapApps = Array.isArray(importAssistant.map_apps) ? importAssistant.map_apps : [];
    if (!mapApps.length) {
      wx.showToast({ title: "当前没有可用导入配置", icon: "none" });
      return;
    }

    const selectedImportMapAppKey = resolvePreferredMapApp(
      mapApps,
      this.data.selectedImportMapAppKey || importAssistant.preferred_map_app || importAssistant.default_map_app || "",
    );
    const importView = resolveMapAppView(importAssistant, selectedImportMapAppKey, this.data.runtimePlatformKey || "general");
    this.setData({
      showImportAssistant: true,
      selectedImportMapAppKey,
      selectedImportMapApp: importView.selectedMapApp,
      selectedImportSteps: importView.selectedSteps,
    });
  },

  handleCloseImportAssistant() {
    this.setData({ showImportAssistant: false, showImportTroubleshooting: false });
  },

  handleSelectImportMapApp(event) {
    const key = String(event.currentTarget.dataset.key || "").trim();
    if (!key) {
      return;
    }

    const importAssistant = this.data.importAssistant || {};
    const importView = resolveMapAppView(importAssistant, key, this.data.runtimePlatformKey || "general");
    if (!importView.selectedMapApp) {
      return;
    }

    wx.setStorageSync(IMPORT_PREFERENCE_STORAGE_KEY, key);
    this.setData({
      selectedImportMapAppKey: key,
      selectedImportMapApp: importView.selectedMapApp,
      selectedImportSteps: importView.selectedSteps,
    });

    request({
      path: API_PATHS.meNavigationPreferences,
      method: "POST",
      data: { preferred_map_app: key },
    }).catch(() => {});
  },

  handleToggleImportTroubleshooting() {
    this.setData({ showImportTroubleshooting: !this.data.showImportTroubleshooting });
  },

  handleCopyGpxPath() {
    const filePath = String(this.data.downloadedGpxPath || "").trim();
    if (!filePath) {
      wx.showToast({ title: "当前没有可复制的文件路径", icon: "none" });
      return;
    }
    wx.setClipboardData({
      data: filePath,
      success: () => {
        wx.showToast({ title: "文件路径已复制", icon: "none" });
      },
    });
  },

  noop() {
    // Prevent overlay tap from closing the modal when tapping content.
  },

  handleToggleFavorite() {
    if (!this.ensureLoggedInForRouteAction()) {
      return;
    }

    const route = this.data.route || {};
    const slug = String(route.slug || "").trim();
    if (!slug) {
      return;
    }

    const nextFavoriteState = !route.is_favorite;
    const nextRoute = {
      ...route,
      is_favorite: nextFavoriteState,
    };

    this.setData({
      route: nextRoute,
      overviewStats: buildOverviewStats(nextRoute),
    });

    const favoritePath = getMiniProgramApiPath(route?.mini_program?.favorite)
      || normalizeRequestPath(route.favorite_api_href);

    if (!favoritePath) {
      wx.showToast({ title: "收藏功能暂不可用", icon: "none" });
      return;
    }

    request({ path: favoritePath, method: nextFavoriteState ? "POST" : "DELETE" })
      .then((payload) => {
        const confirmedState = typeof payload?.is_favorite === "boolean"
          ? payload.is_favorite
          : nextFavoriteState;
        const updatedRoute = {
          ...this.data.route,
          is_favorite: confirmedState,
          engagement: {
            ...(this.data.route.engagement || {}),
            ...(payload?.engagement || {}),
          },
        };
        this.setData({
          route: updatedRoute,
          overviewStats: buildOverviewStats(updatedRoute),
          checkpointTimeline: buildCheckpointTimeline(updatedRoute, this.data.detailSections.daily_plan, this.data.detailSections.checkpoints),
        });

        wx.showToast({
          title: confirmedState ? "已加入收藏" : "已取消收藏",
          icon: "none",
          duration: 1600,
        });
      })
      .catch(() => {
        this.setData({
          route,
          overviewStats: buildOverviewStats(route),
        });
        wx.showToast({
          title: "收藏失败，请重试",
          icon: "none",
          duration: 1800,
        });
      });
  },

  handleSetWantGoPlan() {
    if (!this.ensureLoggedInForRouteAction()) {
      return;
    }

    const route = this.data.route || {};
    const slug = String(route.slug || "").trim();
    if (!slug) {
      return;
    }

    const currentPlanBucket = String(route?.want_go?.plan_bucket || "").trim();
    if (currentPlanBucket) {
      wx.showToast({
        title: `已选择${normalizeWantGoPlanLabel(currentPlanBucket)}`,
        icon: "none",
        duration: 1800,
      });
      return;
    }

    const itemList = [...WANT_GO_PLAN_OPTIONS.map((item) => item.label), "取消想去"];
    wx.showActionSheet({
      itemList,
      success: (result) => {
        const index = Number(result.tapIndex);
        if (!Number.isFinite(index) || index < 0 || index >= itemList.length) {
          return;
        }

        const pickedOption = WANT_GO_PLAN_OPTIONS[index] || null;
        const isClear = !pickedOption;
        const requestConfig = isClear
          ? { path: API_PATHS.routeWantGo(slug), method: "DELETE" }
          : {
              path: API_PATHS.routeWantGo(slug),
              method: "POST",
              data: { plan_bucket: pickedOption.key },
            };

        request(requestConfig)
          .then((payload) => {
            const nextRoute = {
              ...this.data.route,
              engagement: {
                ...(this.data.route.engagement || {}),
                ...(payload?.engagement || {}),
              },
              want_go: {
                ...(this.data.route.want_go || {}),
                ...(payload?.want_go || {}),
              },
            };

            this.setData({
              route: nextRoute,
              wantGoActionLabel: normalizeWantGoPlanLabel(nextRoute?.want_go?.plan_bucket),
              overviewStats: buildOverviewStats(nextRoute),
              checkpointTimeline: buildCheckpointTimeline(nextRoute, this.data.detailSections.daily_plan, this.data.detailSections.checkpoints),
            });

            wx.showToast({
              title: isClear ? "已取消想去" : `已标记${pickedOption.label}`,
              icon: "none",
              duration: 1700,
            });
          })
          .catch((error) => {
            wx.showToast({ title: String(error?.message || "设置失败，请重试"), icon: "none", duration: 2200 });
          });
      },
    });
  },

  handleDownloadGpx(event) {
    const dataset = event && event.currentTarget && event.currentTarget.dataset
      ? event.currentTarget.dataset
      : {};
    const rawHref = getMiniProgramDownloadUrl(this.data.route?.gpx?.mini_program?.download)
      || dataset.href;
    const filename = dataset.filename || this.data.route?.gpx?.filename || "route.gpx";
    if (!rawHref) {
      wx.showToast({ title: "当前路线没有 GPX 文件", icon: "none" });
      return;
    }

    downloadRemoteFile({
      url: buildWebUrl(rawHref),
      filename,
      loadingText: "正在下载 GPX",
      showSavedModal: false,
    })
      .then((savedPath) => {
        const importAssistant = this.data.importAssistant || {};
        const mapApps = Array.isArray(importAssistant.map_apps) ? importAssistant.map_apps : [];
        const selectedImportMapAppKey = resolvePreferredMapApp(
          mapApps,
          this.data.selectedImportMapAppKey || importAssistant.preferred_map_app || importAssistant.default_map_app || "",
        );
        const importView = resolveMapAppView(importAssistant, selectedImportMapAppKey, this.data.runtimePlatformKey || "general");
        this.setData({
          showImportAssistant: true,
          showImportTroubleshooting: false,
          importDownloadStatus: "success",
          importDownloadMessage: `${filename} 已下载，继续按下方步骤导入。`,
          downloadedGpxPath: String(savedPath || ""),
          selectedImportMapAppKey,
          selectedImportMapApp: importView.selectedMapApp,
          selectedImportSteps: importView.selectedSteps,
        });
      })
      .catch((error) => {
        const message = error?.message || "GPX 下载失败";
        this.setData({
          showImportAssistant: true,
          showImportTroubleshooting: true,
          importDownloadStatus: "failed",
          importDownloadMessage: message,
        });
      });
  },
});
