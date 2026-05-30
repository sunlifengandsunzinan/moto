const { request, buildWebUrl } = require("../../utils/request");

Page({
  data: {
    loading: true,
    error: "",
    page: {},
    profile: {},
    metrics: [],
    sections: [],
    quickActions: [],
  },

  onLoad() {
    this.fetchData();
  },

  onPullDownRefresh() {
    this.fetchData(true);
  },

  fetchData(stopRefresh = false) {
    this.setData({ loading: true, error: "" });

    request({ path: "/moto/me" })
      .then((payload) => {
        this.setData({
          loading: false,
          page: payload.page,
          profile: payload.profile,
          metrics: payload.metrics || [],
          sections: payload.sections || [],
          quickActions: payload.quick_actions || [],
        });
      })
      .catch((error) => {
        this.setData({ loading: false, error: error.message || "加载失败" });
      })
      .finally(() => {
        if (stopRefresh) {
          wx.stopPullDownRefresh();
        }
      });
  },

  handleOpenHref(event) {
    const href = event.currentTarget.dataset.href;
    wx.navigateTo({
      url: `/pages/webview/index?url=${encodeURIComponent(buildWebUrl(href))}`,
    });
  },
});