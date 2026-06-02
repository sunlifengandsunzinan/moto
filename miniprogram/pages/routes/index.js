const { request, buildWebUrl } = require("../../utils/request");
const { downloadRemoteFile } = require("../../utils/file-download");
const { mergeRoutesWithFavorites, toggleFavoriteRoute } = require("../../utils/favorites");
const { routesPageFallback } = require("../../mock/routes");

const EMPTY_ROUTES_STATE = routesPageFallback;

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
      ...((safeRoute && safeRoute.amap_export) || {}),
    },
    days_plan: Array.isArray(safeRoute.days_plan) ? safeRoute.days_plan : [],
    ...safeRoute,
  };
}

function normalizePayload(payload) {
  const safePayload = payload || EMPTY_ROUTES_STATE;
  const selectedDays = safePayload.filters && safePayload.filters.selected_days ? safePayload.filters.selected_days : "";
  const routes = mergeRoutesWithFavorites(
    (Array.isArray(safePayload.routes) ? safePayload.routes : []).map(normalizeRoute),
  );

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
      const allRoutes = mergeRoutesWithFavorites(this.data.allRoutes);
      this.setData({ allRoutes, routes: allRoutes });
    }
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
        this.setData({
          loading: false,
          error: "",
          ...normalizePayload(payload),
        });
      })
      .catch((error) => {
        this.setData({
          loading: false,
          error: error?.message || "加载路线失败，已切换本地演示数据。",
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
    this.openInWebView(event.currentTarget.dataset.href);
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
    const route = (this.data.allRoutes || []).find((item) => item.slug === slug);
    if (!route) {
      return;
    }

    const result = toggleFavoriteRoute(route);
    const allRoutes = (this.data.allRoutes || []).map((item) => (
      item.slug === slug ? { ...item, is_favorite: result.isFavorite } : item
    ));

    this.setData({ allRoutes });
    this.applyDurationFilter(this.data.selectedDuration, allRoutes);
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