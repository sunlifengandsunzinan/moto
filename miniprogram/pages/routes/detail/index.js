const { request, buildWebUrl } = require("../../../utils/request");
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

function buildMarkerCallout(point, index, totalCount) {
  const isStart = index === 0;
  const isEnd = index === totalCount - 1;

  if (isStart) {
    return {
      content: `起 · ${point.name}`,
      bgColor: "#D17E45",
      color: "#FBF7F0",
    };
  }

  if (isEnd) {
    return {
      content: `终 · ${point.name}`,
      bgColor: "#4F4A46",
      color: "#FBF7F0",
    };
  }

  return {
    content: `${index + 1}. ${point.name}`,
    bgColor: "#8F7F70",
    color: "#FBF7F0",
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
        width: 26,
        height: 34,
        anchor: { x: 0.5, y: 1 },
        zIndex: index === 0 || index === coordinatePoints.length - 1 ? 20 : 10,
        callout: {
          content: callout.content,
          display: "ALWAYS",
          padding: 6,
          borderRadius: 999,
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
          color: "#D17E45",
          width: 6,
          dottedLine: false,
          arrowLine: false,
          borderColor: "#F7EFE4",
          borderWidth: 1,
        }]
      : [],
    scale: coordinatePoints.length >= 4 ? 7 : 9,
  };
}

function normalizePayload(payload) {
  const route = payload?.route || {};
  const amapExport = route.amap_export || {};
  const mapPayload = buildMapPayload(amapExport);
  const tripAdvice = payload?.detail_sections?.trip_advice || {};
  const slug = String(route.slug || "").trim();

  return {
    page: payload?.page || { title: route.title || "路线详情", eyebrow: "路线详情" },
    route: {
      ...route,
      slug,
      is_favorite: slug ? isFavoriteRoute(slug) : false,
      favorite_api_href: String(route.favorite_api_href || ""),
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
        ...(route.gpx || {}),
      },
      amap_export: {
        ...amapExport,
        embed_url: amapExport.embed_href ? buildWebUrl(amapExport.embed_href) : "",
        map_preview_available: mapPayload.preview_available,
        map_center: mapPayload.center,
        map_include_points: mapPayload.include_points,
        map_markers: mapPayload.markers,
        map_polyline: mapPayload.polyline,
        map_scale: mapPayload.scale,
        screenshot_url: amapExport.screenshot_href ? buildWebUrl(amapExport.screenshot_href) : "",
      },
    },
    detail_sections: {
      daily_plan: payload?.detail_sections?.daily_plan || [],
      trip_advice: {
        title: tripAdvice.title || "行途建议",
        comment: tripAdvice.comment || "",
        items: Array.isArray(tripAdvice.items) ? tripAdvice.items : [],
        source_line: tripAdvice.source_line || "",
      },
    },
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
      amap_export: {
        embed_url: "",
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

    request({ path: `/moto/routes/${slug}` })
      .then((payload) => {
        const normalized = normalizePayload(payload);
        this.setData({
          loading: false,
          page: normalized.page,
          route: normalized.route,
          detailSections: normalized.detail_sections,
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
      url: "/pages/routes/index",
    });
  },

  handleDirectNavigate(event) {
    const launchHref = event.currentTarget.dataset.launchHref;
    const rawHref = event.currentTarget.dataset.href;
    const browserHref = event.currentTarget.dataset.browserHref;
    const targetHref = launchHref || rawHref || browserHref;
    if (!targetHref) {
      return;
    }

    wx.navigateTo({
      url: `/pages/webview/index?url=${encodeURIComponent(buildWebUrl(targetHref))}`,
    });
  },

  handleOpenInteractiveMap(event) {
    const rawUrl = event.currentTarget.dataset.url;
    if (!rawUrl) {
      return;
    }

    wx.navigateTo({
      url: `/pages/webview/index?url=${encodeURIComponent(rawUrl)}`,
    });
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

    this.setData({ route: nextRoute });

    if (result.isFavorite && route.favorite_api_href) {
      request({ path: String(route.favorite_api_href || "").replace(/^\/api/, ""), method: "POST" })
        .then((payload) => {
          if (payload && payload.ok && payload.engagement) {
            this.setData({
              route: {
                ...this.data.route,
                engagement: {
                  ...(this.data.route.engagement || {}),
                  ...payload.engagement,
                },
              },
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
    const rawHref = event.currentTarget.dataset.href;
    const filename = event.currentTarget.dataset.filename || "route.gpx";
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