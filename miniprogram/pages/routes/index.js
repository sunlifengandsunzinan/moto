const { request, buildWebUrl } = require("../../utils/request");

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
    page: {},
    featuredSummary: {},
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
        const allRoutes = payload.routes || [];
        this.setData({
          loading: false,
          page: payload.page,
          featuredSummary: payload.featured_summary,
          allRoutes,
        });
        this.applyDurationFilter(this.data.selectedDuration, allRoutes);
      })
      .catch((error) => {
        this.setData({
          loading: false,
          error: error.message || "加载失败",
        });
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

  handleOpenPlanner() {
    wx.navigateTo({
      url: `/pages/webview/index?url=${encodeURIComponent(buildWebUrl("/moto/planner"))}`,
    });
  },

  handleOpenRoute(event) {
    const href = event.currentTarget.dataset.href;
    wx.navigateTo({
      url: `/pages/webview/index?url=${encodeURIComponent(buildWebUrl(href))}`,
    });
  },

  handleDirectNavigate(event) {
    const href = event.currentTarget.dataset.href;
    wx.navigateTo({
      url: `/pages/webview/index?url=${encodeURIComponent(href)}`,
    });
  },
});