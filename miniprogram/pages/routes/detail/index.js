const { request, buildWebUrl } = require("../../../utils/request");
const {
  API_PATHS,
  MINI_PROGRAM_PATHS,
  getMiniProgramNavigationUrl,
  getMiniProgramApiPath,
  getMiniProgramDownloadUrl,
  normalizeRequestPath,
  TENCENT_MAP_SUBKEY,
} = require("../../../utils/backend-config");
const { downloadRemoteFile } = require("../../../utils/file-download");
const { getRouteDetailFallback } = require("../../../mock/route-detail");
const { isFavoriteRoute, toggleFavoriteRoute } = require("../../../utils/favorites");

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

function buildMapPayload(amapExport) {
  const coordinatePoints = (amapExport?.waypoints || [])
    .map(normalizeCoordinatePoint)
    .filter(Boolean);

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

  return {
    preview_available: true,
    center: {
      longitude: coordinatePoints[0].longitude,
      latitude: coordinatePoints[0].latitude,
    },
    include_points: includePoints,
    markers: coordinatePoints.map((point, index) => {
      const callout = buildMarkerCallout(point, index, coordinatePoints.length);
      return {
        id: index + 1,
        longitude: point.longitude,
        latitude: point.latitude,
        width: 28,
        height: 36,
        anchor: { x: 0.5, y: 1 },
        zIndex: index === 0 || index === coordinatePoints.length - 1 ? 20 : 10,
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
    polyline: coordinatePoints.length >= 2
      ? [{
          points: coordinatePoints.map((point) => ({
            longitude: point.longitude,
            latitude: point.latitude,
          })),
          color: "#1f87bd",
          width: 5,
          dottedLine: false,
          arrowLine: false,
          borderColor: "#f3f7f8",
          borderWidth: 1,
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

function buildCheckpointTimeline(route, dailyPlan) {
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

function normalizePayload(payload) {
  const route = payload?.route || {};
  const amapExport = route.amap_export || {};
  const mapPayload = buildMapPayload(amapExport);
  const slug = String(route.slug || "").trim();

  const normalizedRoute = {
    ...route,
    tencentMapSubkey: TENCENT_MAP_SUBKEY,
    slug,
    is_favorite: slug ? isFavoriteRoute(slug) : false,
    favorite_api_href: String(route.favorite_api_href || ""),
    navigation_api_href: String(route.navigation_api_href || ""),
    mini_program: {
      favorite: null,
      navigation: null,
      ...((route && route.mini_program) || {}),
    },
    engagement: {
      favorite_count: 0,
      navigation_count: 0,
      total_count: 0,
      ...(route.engagement || {}),
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
  };

  const dailyPlan = payload?.detail_sections?.daily_plan || [];

  return {
    page: payload?.page || { title: route.title || "路线详情", eyebrow: "路线详情" },
    route: normalizedRoute,
    detail_sections: {
      daily_plan: dailyPlan,
      trip_advice: payload?.detail_sections?.trip_advice || { title: "行途建议", comment: "", items: [], source_line: "" },
    },
    overview_stats: buildOverviewStats(normalizedRoute),
    checkpoint_timeline: buildCheckpointTimeline(normalizedRoute, dailyPlan),
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
  },

  onLoad(options) {
    const slug = decodeURIComponent(options.slug || "");
    this.slug = slug;
    this.fetchData(slug);
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

    request({ path: API_PATHS.routeDetail(slug) })
      .then((payload) => {
        const normalized = normalizePayload(payload);
        this.setData({
          loading: false,
          page: normalized.page,
          route: normalized.route,
          detailSections: normalized.detail_sections,
          overviewStats: normalized.overview_stats,
          checkpointTimeline: normalized.checkpoint_timeline,
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

  handleDirectNavigate() {
    const route = this.data.route || {};
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
                checkpointTimeline: buildCheckpointTimeline(nextRoute, this.data.detailSections.daily_plan),
              });
            }
          })
          .catch(() => {});
      },
      fail: () => {
        wx.showToast({ title: "无法打开系统地图", icon: "none", duration: 2200 });
      },
    });
  },

  handleOpenRouteMap() {
    const route = this.data.route || {};
    const interactiveMapAction = route?.amap_export?.mini_program?.interactive_map;
    const navigateAction = route?.amap_export?.mini_program?.navigate;
    const mapPageUrl = getMiniProgramNavigationUrl(interactiveMapAction)
      || getMiniProgramNavigationUrl(navigateAction);

    if (mapPageUrl) {
      wx.navigateTo({
        url: mapPageUrl,
      });
      return;
    }

    this.handleDirectNavigate();
  },

  handleToggleFavorite() {
    const route = this.data.route || {};
    const slug = String(route.slug || "").trim();
    if (!slug) {
      return;
    }

    const result = toggleFavoriteRoute(route);
    const nextRoute = {
      ...route,
      is_favorite: result.isFavorite,
    };

    this.setData({
      route: nextRoute,
      overviewStats: buildOverviewStats(nextRoute),
    });

    const favoritePath = getMiniProgramApiPath(route?.mini_program?.favorite)
      || normalizeRequestPath(route.favorite_api_href);

    if (result.isFavorite && favoritePath) {
      request({ path: favoritePath, method: "POST" })
        .then((payload) => {
          if (payload && payload.ok && payload.engagement) {
            const updatedRoute = {
              ...this.data.route,
              engagement: {
                ...(this.data.route.engagement || {}),
                ...payload.engagement,
              },
            };
            this.setData({
              route: updatedRoute,
              overviewStats: buildOverviewStats(updatedRoute),
              checkpointTimeline: buildCheckpointTimeline(updatedRoute, this.data.detailSections.daily_plan),
            });
          }
        })
        .catch(() => {
          wx.showToast({
            title: "后端收藏计数失败",
            icon: "none",
            duration: 1800,
          });
        });
    }

    wx.showToast({
      title: result.isFavorite ? "已加入收藏" : "已取消收藏",
      icon: "none",
      duration: 1600,
    });
  },

  handleDownloadGpx(event) {
    const rawHref = getMiniProgramDownloadUrl(this.data.route?.gpx?.mini_program?.download)
      || event.currentTarget.dataset.href;
    const filename = event.currentTarget.dataset.filename || this.data.route?.gpx?.filename || "route.gpx";
    if (!rawHref) {
      wx.showToast({ title: "当前路线没有 GPX 文件", icon: "none" });
      return;
    }

    downloadRemoteFile({
      url: buildWebUrl(rawHref),
      filename,
      loadingText: "正在下载 GPX",
    }).catch((error) => {
      wx.showToast({
        title: error?.message || "GPX 下载失败",
        icon: "none",
        duration: 2200,
      });
    });
  },
});
