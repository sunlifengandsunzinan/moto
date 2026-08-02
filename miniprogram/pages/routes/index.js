const { request, buildWebUrl } = require("../../utils/request");
const {
  API_PATHS,
  MINI_PROGRAM_PATHS,
  WEB_PATHS,
  getMiniProgramApiPath,
  getMiniProgramDownloadUrl,
  getMiniProgramNavigationUrl,
  normalizeRequestPath,
} = require("../../utils/backend-config");
const { downloadRemoteFile } = require("../../utils/file-download");
const { mergeRoutesWithFavorites, toggleFavoriteRoute } = require("../../utils/favorites");

const EMPTY_ROUTES_STATE = {
  page: {
    title: "热门摩旅路线",
    description: "当前路线数据需要从后端加载。",
  },
  featured_summary: {
    title: "路线列表",
    description: "当前没有可展示的路线数据。",
  },
  empty_state: {
    title: "暂无路线",
    description: "请检查后端接口或在后台管理中补充路线数据。",
    action: { label: "去后台管理", href: "/moto/admin" },
  },
  routes: [],
};

function compareRouteHeat(left, right) {
  const leftEngagement = left?.engagement || {};
  const rightEngagement = right?.engagement || {};
  const leftTotal = Number(leftEngagement.total_count || 0);
  const rightTotal = Number(rightEngagement.total_count || 0);
  if (leftTotal !== rightTotal) {
    return rightTotal - leftTotal;
  }

  const leftNavigation = Number(leftEngagement.navigation_count || 0);
  const rightNavigation = Number(rightEngagement.navigation_count || 0);
  if (leftNavigation !== rightNavigation) {
    return rightNavigation - leftNavigation;
  }

  const leftFavorite = Number(leftEngagement.favorite_count || 0);
  const rightFavorite = Number(rightEngagement.favorite_count || 0);
  if (leftFavorite !== rightFavorite) {
    return rightFavorite - leftFavorite;
  }

  return String(left?.title || "").localeCompare(String(right?.title || ""), "zh-Hans-CN");
}

function sortRoutesByHeat(routes) {
  return (Array.isArray(routes) ? routes.slice() : []).sort(compareRouteHeat);
}

function sortRoutes(routes, sortMode) {
  if (sortMode === "distance") {
    return (Array.isArray(routes) ? routes.slice() : []).sort((left, right) => {
      const leftDistance = Number(left?.distance_km || 0);
      const rightDistance = Number(right?.distance_km || 0);
      if (leftDistance !== rightDistance) {
        return rightDistance - leftDistance;
      }
      return compareRouteHeat(left, right);
    });
  }

  return sortRoutesByHeat(routes);
}

function buildDurationFilters(filters, selectedDays) {
  const quickFilters = filters && Array.isArray(filters.day_quick_filters) ? filters.day_quick_filters : [];
  if (!quickFilters.length) {
    return [{ key: "", label: "全部", value: "", is_active: true }];
  }

  return quickFilters.map((item) => ({
    key: String(item.value || "all"),
    label: item.label || "全部",
    value: item.value || "",
    is_active: String(item.value || "") === String(selectedDays || ""),
  }));
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

function buildEstimatedDurationLabel(route) {
  const distance = Number(route?.distance_km || 0);
  if (!Number.isFinite(distance) || distance <= 0) {
    return "--";
  }

  const estimatedHours = Math.max(1, Math.round(distance / 55));
  return `${estimatedHours}H`;
}

function buildRouteCoverImage(route) {
  const screenshotHref = String(route?.amap_export?.screenshot_href || "").trim();
  if (screenshotHref) {
    return buildWebUrl(screenshotHref);
  }

  return "";
}

function normalizeRoute(route) {
  const safeRoute = route || {};
  const normalizedRoute = {
    mini_program_action: safeRoute.mini_program_action || null,
    mini_program: {
      replan: null,
      collect: null,
      favorite: null,
      ...((safeRoute && safeRoute.mini_program) || {}),
    },
    engagement: {
      favorite_count: 0,
      navigation_count: 0,
      total_count: 0,
      ...((safeRoute && safeRoute.engagement) || {}),
    },
    gpx: {
      is_available: false,
      filename: "",
      download_href: "",
      source_badge: "",
      source_title: "",
      meta_text: "",
      mini_program: {
        download: null,
      },
      ...((safeRoute && safeRoute.gpx) || {}),
    },
    amap_export: {
      is_available: false,
      href: "",
      browser_href: "",
      launch_href: "",
      mini_program: {
        navigate: null,
        browser: null,
        interactive_map: null,
      },
      ...((safeRoute && safeRoute.amap_export) || {}),
    },
    source_meta: {
      label: "",
      author: "",
      detail: "",
      ...((safeRoute && safeRoute.source_meta) || {}),
    },
    favorite_api_href: String(safeRoute.favorite_api_href || ""),
    navigation_api_href: String(safeRoute.navigation_api_href || ""),
    days_plan: Array.isArray(safeRoute.days_plan) ? safeRoute.days_plan : [],
    ...safeRoute,
  };

  return {
    ...normalizedRoute,
    cover_image_url: buildRouteCoverImage(normalizedRoute),
    estimated_duration_label: buildEstimatedDurationLabel(normalizedRoute),
    reward_points_label: `${Number(normalizedRoute?.engagement?.favorite_count || 0)}分`,
  };
}

function normalizePayload(payload) {
  const safePayload = payload || EMPTY_ROUTES_STATE;
  const selectedDays = safePayload.filters && safePayload.filters.selected_days ? safePayload.filters.selected_days : "";
  const routes = sortRoutesByHeat(mergeRoutesWithFavorites(
    (Array.isArray(safePayload.routes) ? safePayload.routes : []).map(normalizeRoute),
  ));

  return {
    page: safePayload.page || EMPTY_ROUTES_STATE.page,
    featuredSummary: safePayload.featured_summary || EMPTY_ROUTES_STATE.featured_summary,
    emptyState: safePayload.empty_state || EMPTY_ROUTES_STATE.empty_state,
    allRoutes: routes,
    routes,
    selectedDuration: selectedDays,
    durationFilters: buildDurationFilters(safePayload.filters, selectedDays),
  };
}

function applyRouteFilters(allRoutes, selectedDuration, keyword, sortMode) {
  const normalizedKeyword = String(keyword || "").trim().toLowerCase();
  const filtered = (Array.isArray(allRoutes) ? allRoutes : []).filter((route) => {
    if (selectedDuration && String(route.days || "") !== String(selectedDuration)) {
      return false;
    }

    if (!normalizedKeyword) {
      return true;
    }

    const title = String(route.title || "").toLowerCase();
    const summary = String(route.summary || "").toLowerCase();
    const sourceLabel = String(route?.source_meta?.label || "").toLowerCase();
    return title.includes(normalizedKeyword) || summary.includes(normalizedKeyword) || sourceLabel.includes(normalizedKeyword);
  });

  return sortRoutes(filtered, sortMode);
}

Page({
  data: {
    loading: true,
    error: "",
    page: { title: "热门摩旅路线", description: "" },
    featuredSummary: { title: "", description: "" },
    emptyState: {
      title: "暂无路线",
      description: "当前还没有匹配路线。",
      action: { label: "去采集导航点", href: WEB_PATHS.routesCollect },
    },
    allRoutes: [],
    routes: [],
    selectedDuration: "",
    keyword: "",
    sortMode: "heat",
    sortLabel: "热度",
    durationFilters: [{ key: "", label: "全部", value: "", is_active: true }],
  },

  onLoad() {
    this.fetchData();
  },

  onShow() {
    this.fetchData(this.buildQuery());
  },

  applyDurationFilter(selectedDuration, routes) {
    const sourceRoutes = routes !== undefined ? routes : this.data.allRoutes;
    this.setData({
      selectedDuration,
      routes: applyRouteFilters(sourceRoutes, selectedDuration, this.data.keyword, this.data.sortMode),
    });
  },

  onPullDownRefresh() {
    this.fetchData(this.buildQuery(), true);
  },

  buildQuery(overrides = {}) {
    return {
      days: overrides.days !== undefined ? overrides.days : this.data.selectedDuration,
    };
  },

  fetchData(query = {}, stopRefresh = false) {
    this.setData({ loading: true, error: "" });

    const requestData = {
      ...query,
      _t: Date.now(),
    };

    request({ path: API_PATHS.routes, data: requestData })
      .then((payload) => {
        const normalized = normalizePayload(payload);
        this.setData({
          loading: false,
          error: "",
          ...normalized,
          routes: applyRouteFilters(normalized.allRoutes, normalized.selectedDuration, this.data.keyword, this.data.sortMode),
        });
      })
      .catch((error) => {
        this.setData({
          loading: false,
          error: error?.message || "加载路线失败，已切换本地空状态。",
          ...normalizePayload(EMPTY_ROUTES_STATE),
        });
      })
      .finally(() => {
        if (stopRefresh) {
          wx.stopPullDownRefresh();
        }
      });
  },

  handleDurationFilter(event) {
    const days = event.currentTarget.dataset.filterValue || "";
    this.fetchData(this.buildQuery({ days }));
  },

  handleSearchInput(event) {
    const keyword = String(event.detail.value || "");
    this.setData({
      keyword,
      routes: applyRouteFilters(this.data.allRoutes, this.data.selectedDuration, keyword, this.data.sortMode),
    });
  },

  handleSearchClear() {
    this.setData({
      keyword: "",
      routes: applyRouteFilters(this.data.allRoutes, this.data.selectedDuration, "", this.data.sortMode),
    });
  },

  handleToggleSort() {
    const nextSortMode = this.data.sortMode === "heat" ? "distance" : "heat";
    this.setData({
      sortMode: nextSortMode,
      sortLabel: nextSortMode === "heat" ? "热度" : "里程",
      routes: applyRouteFilters(this.data.allRoutes, this.data.selectedDuration, this.data.keyword, nextSortMode),
    });
  },

  updateRouteEngagement(slug, engagement) {
    const allRoutes = (this.data.allRoutes || []).map((route) => (
      route.slug === slug
        ? {
            ...route,
            engagement: {
              ...(route.engagement || {}),
              ...(engagement || {}),
            },
          }
        : route
    ));

    this.setData({
      allRoutes,
      routes: applyRouteFilters(allRoutes, this.data.selectedDuration, this.data.keyword, this.data.sortMode),
    });
  },

  findRoute(slug) {
    return (this.data.allRoutes || []).find((route) => route.slug === slug) || null;
  },

  navigateByAction(action, fallbackHref = "") {
    const targetUrl = getMiniProgramNavigationUrl(action);
    if (targetUrl) {
      if (action && action.type === "tab") {
        wx.switchTab({ url: targetUrl });
        return;
      }

      wx.navigateTo({ url: targetUrl });
      return;
    }

    if (fallbackHref) {
      this.openInWebView(fallbackHref);
    }
  },

  openInWebView(rawHref) {
    if (!rawHref) {
      return;
    }

    const href = /^https?:\/\//.test(rawHref) ? rawHref : buildWebUrl(rawHref);
    wx.navigateTo({
      url: MINI_PROGRAM_PATHS.webviewWithUrl(href),
    });
  },

  handleOpenRoute(event) {
    const slug = event.currentTarget.dataset.slug;
    const route = this.findRoute(slug);
    if (route && route.mini_program_action) {
      this.navigateByAction(route.mini_program_action, route.href);
      return;
    }

    if (slug) {
      wx.navigateTo({ url: MINI_PROGRAM_PATHS.routeDetail(slug) });
      return;
    }

    this.openInWebView(event.currentTarget.dataset.href);
  },

  handleDirectNavigate(event) {
    const route = this.findRoute(event.currentTarget.dataset.slug);
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
              this.updateRouteEngagement(route.slug, payload.engagement);
            }
          })
          .catch(() => {});
      },
      fail: () => {
        wx.showToast({ title: "无法打开系统地图", icon: "none", duration: 2200 });
      },
    });
  },

  handleDownloadGpx(event) {
    const route = this.findRoute(event.currentTarget.dataset.slug);
    const rawHref = getMiniProgramDownloadUrl(route?.gpx?.mini_program?.download) || event.currentTarget.dataset.href;
    const filename = event.currentTarget.dataset.filename || route?.gpx?.filename || "route.gpx";
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

  handleToggleFavorite(event) {
    const slug = event.currentTarget.dataset.slug;
    const route = (this.data.allRoutes || []).find((item) => item.slug === slug);
    if (!route) {
      return;
    }

    const result = toggleFavoriteRoute(route);
    const allRoutes = (this.data.allRoutes || []).map((item) => (
      item.slug === slug ? { ...item, is_favorite: result.isFavorite } : item
    ));

    this.setData({
      allRoutes,
      routes: applyRouteFilters(allRoutes, this.data.selectedDuration, this.data.keyword, this.data.sortMode),
    });

    const favoritePath = getMiniProgramApiPath(route?.mini_program?.favorite)
      || normalizeRequestPath(route?.favorite_api_href || "");

    if (result.isFavorite && favoritePath) {
      request({ path: favoritePath, method: "POST" })
        .then((payload) => {
          if (payload && payload.ok && payload.engagement) {
            this.updateRouteEngagement(slug, payload.engagement);
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

  handleOpenCollect(event) {
    this.openInWebView(event.currentTarget.dataset.href);
  },

  handleOpenReplan(event) {
    this.openInWebView(event.currentTarget.dataset.href);
  },

  handleOpenPlanner() {
    this.openInWebView(WEB_PATHS.planner());
  },

  handleEmptyAction(event) {
    const href = event.currentTarget.dataset.href;
    if (href) {
      this.openInWebView(href);
    }
  },
});
