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
const WANT_GO_PLAN_OPTIONS = [
  { key: "this_month", label: "这个月" },
  { key: "next_month", label: "下个月" },
  { key: "later", label: "再说" },
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
  return Boolean(nickName || avatarUrl);
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

function buildMapPayload(amapExport) {
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
  const fallbackPolylinePoints = dedupePolylinePoints(includePoints);
  const visiblePolylinePoints = safePolylinePoints.length >= 2 ? safePolylinePoints : fallbackPolylinePoints;

  return {
    preview_available: true,
    center: {
      longitude: markerPoints[0].longitude,
      latitude: markerPoints[0].latitude,
    },
    include_points: markerPoints.map((point) => ({
      longitude: point.longitude,
      latitude: point.latitude,
    })),
    markers: markerPoints.map((point, index) => {
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
    }),
    polyline: visiblePolylinePoints.length >= 2
      ? [{
          points: visiblePolylinePoints,
          color: "#1372CFFF",
          width: 8,
          dottedLine: false,
          arrowLine: false,
          borderColor: "#FFFFFFD9",
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
      const hitCountText = String(item?.hit_count_text || item?.hit_count || "--").trim() || "--";

      return {
        index: index + 1,
        name,
        score_text: summary || "可获得打卡积分0点",
        distance_text: distanceText,
        duration_text: timing,
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
      : routeDistance;

    return waypoints.map((waypoint, index) => ({
      index: index + 1,
      name: String(waypoint?.name || `打卡点${index + 1}`),
      score_text: "可获得打卡积分0点",
      distance_text: index === 0 ? "起点" : `${segmentDistance}km`,
      duration_text: index === 0 ? "" : `00小时${String(10 + index * 2).padStart(2, "0")}分钟`,
      hit_count_text: `${Math.max(0, Number(route?.engagement?.navigation_count || 0) - index * 3)}次`,
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
    hit_count_text: "--",
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
  const tencentUrl = resolveManualNavigationUrl(route, "tencent");
  const coordinateTarget = getRouteNavigationTarget(route);
  return [
    {
      key: "amap",
      label: "高德地图",
      url: "",
      manualUrl: amapUrl,
      isAvailable: Boolean(amapUrl || coordinateTarget),
    },
    {
      key: "tencent",
      label: "腾讯地图",
      url: "",
      manualUrl: tencentUrl,
      isAvailable: Boolean(tencentUrl || coordinateTarget),
    },
  ];
}

function resolveManualNavigationUrl(route, mapKey) {
  if (mapKey === "tencent") {
    return String(route?.tencent_export?.href || route?.tencent_export?.app_href || "").trim();
  }
  return String(route?.amap_export?.app_href || route?.amap_export?.href || route?.amap_export?.browser_href || "").trim();
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

function normalizePayload(payload) {
  const route = payload?.route || {};
  const amapExport = route.amap_export || {};
  const mapPayload = buildMapPayload(amapExport);
  const slug = String(route.slug || "").trim();

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
      map_center: mapPayload.center,
      map_include_points: mapPayload.include_points,
      map_markers: mapPayload.markers,
      map_polyline: mapPayload.polyline,
      map_scale: mapPayload.scale,
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

  const dailyPlan = payload?.detail_sections?.daily_plan || [];
  const configuredCheckpoints = normalizeConfiguredCheckpoints(payload?.detail_sections?.checkpoints || []);

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
    checkpoint_timeline: buildCheckpointTimeline(normalizedRoute, dailyPlan, configuredCheckpoints),
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
        map_center: { longitude: 0, latitude: 0 },
        map_include_points: [],
        map_markers: [],
        map_polyline: [],
        map_scale: 8,
      },
    },
    detailSections: { daily_plan: [], trip_advice: { title: "行途建议", comment: "", items: [], source_line: "" } },
    overviewStats: [],
    checkpointTimeline: [],
    linkedSpots: [],
    primaryMapActionLabel: "直接导航",
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
  },

  onLoad(options) {
    const slug = decodeURIComponent(options.slug || "");
    this.slug = slug;
    this.runtimePlatformKey = detectPlatformKey();
    this.enableNativeSharing();
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
    return {
      title: sharePayload.title,
      path: sharePayload.path,
    };
  },

  onShareTimeline() {
    const sharePayload = buildRouteSharePayload(this.data.route || {}, this.slug);
    return {
      title: sharePayload.title,
      query: sharePayload.query,
    };
  },

  onPullDownRefresh() {
    this.fetchData(this.slug, true);
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
        const primaryMapActionLabel = "直接导航";

        this.setData({
          loading: false,
          page: normalized.page,
          route: normalized.route,
          detailSections: normalized.detail_sections,
          overviewStats: normalized.overview_stats,
          checkpointTimeline: normalized.checkpoint_timeline,
          linkedSpots: normalized.detail_sections.linked_spots || [],
          primaryMapActionLabel,
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
      })
      .catch(() => {
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
      linkedSpots: fallback.detail_sections.linked_spots || [],
      primaryMapActionLabel: "直接导航",
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
          this.setData({
            route: nextRoute,
            overviewStats: buildOverviewStats(nextRoute),
            checkpointTimeline: buildCheckpointTimeline(nextRoute, this.data.detailSections.daily_plan, this.data.detailSections.checkpoints),
          });
        }
      })
      .catch(() => {});
  },

  handleDirectNavigate(mapKey = "amap") {
    const route = this.data.route || {};
    const navigationOptions = resolveDirectNavigationOptions(route);
    const selectedOption = navigationOptions.find((item) => item.key === mapKey);
    const navigateUrl = selectedOption?.url || "";
    const manualUrl = selectedOption?.manualUrl || resolveManualNavigationUrl(route, mapKey);

    if (manualUrl) {
      this.trackNavigationEngagement(route);
      this.copyNavigationLinkForManualOpen(mapKey, true);
      return;
    }

    if (navigateUrl) {
      this.trackNavigationEngagement(route);
      wx.navigateTo({ url: navigateUrl });
      return;
    }

    if (selectedOption) {
      wx.showToast({ title: `${selectedOption.label}路线暂不可用`, icon: "none" });
    }

    const target = getRouteNavigationTarget(route);
    if (!target) {
      wx.showToast({ title: "当前路线缺少可导航坐标", icon: "none" });
      return;
    }

    wx.openLocation({
      latitude: target.latitude,
      longitude: target.longitude,
      name: target.name,
      address: target.name,
      scale: 12,
      success: () => {
        this.trackNavigationEngagement(route);
      },
      fail: () => {
        this.copyNavigationLinkForManualOpen(mapKey, true);
        wx.showToast({ title: "无法打开系统地图", icon: "none", duration: 2200 });
      },
    });
  },

  copyNavigationLinkForManualOpen(mapKey = "amap", showFeedback = true) {
    const route = this.data.route || {};
    const mapLabel = mapKey === "tencent" ? "腾讯地图" : "高德地图";
    const manualUrl = resolveManualNavigationUrl(route, mapKey);
    if (!manualUrl) {
      return;
    }

    const waypointSummary = buildWaypointSummary(route);
    const payload = [
      `路线：${String(route.title || "未命名路线")}`,
      `地图：${mapLabel}`,
      `链接：${manualUrl}`,
      waypointSummary ? `途径：${waypointSummary}` : "",
    ]
      .filter(Boolean)
      .join("\n");

    wx.setClipboardData({
      data: payload,
      success: () => {
        if (!showFeedback) {
          return;
        }
        wx.showToast({
          title: "路线链接已复制",
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

    const navigationOptions = resolveDirectNavigationOptions(this.data.route || {});
    wx.showActionSheet({
      itemList: navigationOptions.map((item) => item.label),
      success: (result) => {
        const index = Number(result.tapIndex);
        if (!Number.isFinite(index) || index < 0 || index >= navigationOptions.length) {
          return;
        }
        this.handleDirectNavigate(navigationOptions[index].key);
      },
    });
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
          .catch(() => {
            wx.showToast({ title: "设置失败，请重试", icon: "none", duration: 1800 });
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
