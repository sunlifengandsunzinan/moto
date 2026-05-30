const { request, buildWebUrl } = require("../../utils/request");

Page({
  data: {
    loading: true,
    error: "",
    page: {},
    featuredSummary: {},
    routes: [],
    daysValue: "",
    dayQuickFilters: [],
  },

  onLoad() {
    this.fetchData();
  },

  onPullDownRefresh() {
    this.fetchData(this.data.daysValue, true);
  },

  fetchData(days = "", stopRefresh = false) {
    this.setData({ loading: true, error: "" });

    const query = {};
    if (days) {
      query.days = days;
    }

    request({ path: "/moto/routes", data: query })
      .then((payload) => {
        this.setData({
          loading: false,
          page: payload.page,
          featuredSummary: payload.featured_summary,
          routes: payload.routes || [],
          daysValue: payload.filters.selected_days || "",
          dayQuickFilters: payload.filters.day_quick_filters || [],
        });
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

  handleDaysFilter(event) {
    const days = event.currentTarget.dataset.days || "";
    this.fetchData(days, false);
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

  handleOpenAmap(event) {
    const href = event.currentTarget.dataset.href;
    wx.navigateTo({
      url: `/pages/webview/index?url=${encodeURIComponent(href)}`,
    });
  },
});