const { request, buildWebUrl } = require("../../utils/request");
const { downloadRemoteFile } = require("../../utils/file-download");
const { mergeRoutesWithFavorites, toggleFavoriteRoute } = require("../../utils/favorites");
const { routesPageFallback } = require("../../mock/routes");

const EMPTY_ROUTES_STATE = routesPageFallback;

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

function normalizeRoute(route) {
  const safeRoute = route || {};
  return {
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
      ...((safeRoute && safeRoute.gpx) || {}),
    },
    amap_export: {
      is_available: false,
      href: "",
      browser_href: "",
      launch_href: "",
      ...((safeRoute && safeRoute.amap_export) || {}),
    },
    source_meta: {
      label: "",
      author: "",
      detail: "",
      ...((safeRoute && safeRoute.source_meta) || {}),
    },
    favorite_api_href: String(safeRoute.favorite_api_href || ""),
    days_plan: Array.isArray(safeRoute.days_plan) ? safeRoute.days_plan : [],
    ...safeRoute,
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

Page({
  data: {
    loading: true,
    error: "",
    page: { title: "热门摩旅路线", description: "" },
    featuredSummary: { title: "", description: "" },
    emptyState: {
      title: "暂无路线",
      description: "当前还没有匹配路线。",
      action: { label: "去采集导航点", href: "/moto/routes/collect" },
    },
    allRoutes: [],
    routes: [],
    selectedDuration: "",
    durationFilters: [{ key: "", label: "全部", value: "", is_active: true }],
  },

  onLoad() {
    this.fetchData();
  },

  onShow() {
    if (this.data.allRoutes.length) {
      const allRoutes = sortRoutesByHeat(mergeRoutesWithFavorites(this.data.allRoutes));
      this.setData({ allRoutes, routes: this.filterRoutesByDuration(this.data.selectedDuration, allRoutes) });
    }
  },

  filterRoutesByDuration(selectedDuration, routes) {
    if (!selectedDuration) {
      return sortRoutesByHeat(routes);
    }

    return sortRoutesByHeat((routes || []).filter((route) => String(route.days || "") === String(selectedDuration)));
  },

  applyDurationFilter(selectedDuration, routes) {
    this.setData({
      selectedDuration,
      routes: this.filterRoutesByDuration(selectedDuration, routes !== undefined ? routes : this.data.allRoutes),
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

    request({ path: "/moto/routes", data: query })
      .then((payload) => {
        const normalized = normalizePayload(payload);
        this.setData({
          loading: false,
          error: "",
          ...normalized,
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

  updateRouteEngagement(slug, engagement) {
    const allRoutes = sortRoutesByHeat((this.data.allRoutes || []).map((route) => (
      route.slug === slug
        ? {
            ...route,
            engagement: {
              ...(route.engagement || {}),
              ...(engagement || {}),
            },
          }
        : route
    )));

    this.setData({
      allRoutes,
      routes: this.filterRoutesByDuration(this.data.selectedDuration, allRoutes),
    });
  },

  openInWebView(rawHref) {
    if (!rawHref) {
      return;
    }

    const href = /^https?:\/\//.test(rawHref) ? rawHref : buildWebUrl(rawHref);
    wx.navigateTo({
      url: `/pages/webview/index?url=${encodeURIComponent(href)}`,
    });
  },

  handleOpenRoute(event) {
    const slug = event.currentTarget.dataset.slug;
    if (slug) {
      wx.navigateTo({
        url: `/pages/routes/detail/index?slug=${encodeURIComponent(slug)}`,
      });
      return;
    }

    this.openInWebView(event.currentTarget.dataset.href);
  },

  handleDirectNavigate(event) {
    const launchHref = event.currentTarget.dataset.launchHref;
    const primaryHref = event.currentTarget.dataset.href;
    const browserHref = event.currentTarget.dataset.browserHref;
    this.openInWebView(launchHref || primaryHref || browserHref);
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

  handleToggleFavorite(event) {
    const slug = event.currentTarget.dataset.slug;
    const favoriteApiHref = event.currentTarget.dataset.favoriteUrl || "";
    const route = (this.data.allRoutes || []).find((item) => item.slug === slug);
    if (!route) {
      return;
    }

    const result = toggleFavoriteRoute(route);
    const allRoutes = sortRoutesByHeat((this.data.allRoutes || []).map((item) => (
      item.slug === slug ? { ...item, is_favorite: result.isFavorite } : item
    )));

    this.setData({ allRoutes, routes: this.filterRoutesByDuration(this.data.selectedDuration, allRoutes) });

    if (result.isFavorite && favoriteApiHref) {
      request({ path: favoriteApiHref.replace(/^\/api/, ""), method: "POST" })
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
    this.openInWebView("/moto/planner");
  },

  handleEmptyAction(event) {
    const href = event.currentTarget.dataset.href;
    if (href) {
      this.openInWebView(href);
    }
  },
});