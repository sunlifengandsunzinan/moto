const { request, buildWebUrl } = require("../../utils/request");
const { downloadRemoteFile } = require("../../utils/file-download");
const { mergeRoutesWithFavorites, toggleFavoriteRoute } = require("../../utils/favorites");
const { routesPageFallback } = require("../../mock/routes");

const EMPTY_ROUTES_STATE = {
  page: {
    title: "热门摩旅路线",
    description: "当前小程序展示数据已清空。",
  },
  featured_summary: {
    title: "路线列表",
    description: "当前没有展示中的路线数据。",
  },
  empty_state: {
    title: "路线已清空",
    description: "当前小程序没有展示任何路线、GPX 或收藏数据。",
    action: { label: "当前为空", href: "" },
  },
  routes: [],
};

const DURATION_FILTERS = [
  { key: "1-day", label: "1天" },
  { key: "1-2-days", label: "1-2天" },
  { key: "2-3-days", label: "2-3天" },
  { key: "3-plus-days", label: "3天以上" },
];

function matchesDuration(days, filterKey) {
  if (filterKey === "1-day") {
    return days <= 1;
  }
  if (filterKey === "1-2-days") {
    return days > 1 && days <= 2;
  }
  if (filterKey === "2-3-days") {
    return days > 2 && days <= 3;
  }
  if (filterKey === "3-plus-days") {
    return days > 3;
  }
  return true;
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
    selectedDuration: "1-2-days",
    durationFilters: DURATION_FILTERS.map((item) => ({
      ...item,
      is_active: item.key === "1-2-days",
    })),
  },

  onLoad() {
    this.fetchData();
  },

  onShow() {
    if (this.data.allRoutes.length) {
      const allRoutes = mergeRoutesWithFavorites(this.data.allRoutes);
      this.setData({ allRoutes });
      this.applyDurationFilter(this.data.selectedDuration, allRoutes);
    }
  },

  onPullDownRefresh() {
    this.fetchData(true);
  },

  fetchData(stopRefresh = false) {
    this.setData({ loading: true, error: "" });

    const payload = EMPTY_ROUTES_STATE;
    const allRoutes = mergeRoutesWithFavorites(Array.isArray(payload.routes) ? payload.routes : []);
    this.setData({
      loading: false,
      page: payload.page || this.data.page,
      featuredSummary: payload.featured_summary || this.data.featuredSummary,
      emptyState: payload.empty_state || this.data.emptyState,
      allRoutes,
    });
    this.applyDurationFilter(this.data.selectedDuration, allRoutes);

    if (stopRefresh) {
      wx.stopPullDownRefresh();
    }
  },

  applyDurationFilter(filterKey, routeList = this.data.allRoutes) {
    const routes = (routeList || []).filter((route) => matchesDuration(Number(route.days || 0), filterKey));
    this.setData({
      selectedDuration: filterKey,
      routes,
      durationFilters: DURATION_FILTERS.map((item) => ({
        ...item,
        is_active: item.key === filterKey,
      })),
    });
  },

  handleDurationFilter(event) {
    const filterKey = event.currentTarget.dataset.filterKey || "1-2-days";
    this.applyDurationFilter(filterKey);
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