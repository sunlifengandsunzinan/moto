const { request, buildWebUrl } = require("../../utils/request");
const { routesPageFallback } = require("../../mock/routes");

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

  onPullDownRefresh() {
    this.fetchData(true);
  },

  fetchData(stopRefresh = false) {
    this.setData({ loading: true, error: "" });

    request({ path: "/moto/routes" })
      .then((payload) => {
        const allRoutes = Array.isArray(payload.routes) ? payload.routes : [];
        this.setData({
          loading: false,
          page: payload.page || this.data.page,
          featuredSummary: payload.featured_summary || this.data.featuredSummary,
          emptyState: payload.empty_state || this.data.emptyState,
          allRoutes,
        });
        this.applyDurationFilter(this.data.selectedDuration, allRoutes);
      })
      .catch((_error) => {
        const allRoutes = Array.isArray(routesPageFallback.routes) ? routesPageFallback.routes : [];
        this.setData({
          loading: false,
          error: "",
          page: routesPageFallback.page || this.data.page,
          featuredSummary: routesPageFallback.featured_summary || this.data.featuredSummary,
          emptyState: routesPageFallback.empty_state || this.data.emptyState,
          allRoutes,
        });
        this.applyDurationFilter(this.data.selectedDuration, allRoutes);
      })
      .finally(() => {
        if (stopRefresh) {
          wx.stopPullDownRefresh();
        }
      });
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
    this.openInWebView(event.currentTarget.dataset.href);
  },
});