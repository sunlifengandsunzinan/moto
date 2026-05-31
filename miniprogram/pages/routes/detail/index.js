const { request, buildWebUrl } = require("../../../utils/request");
const { getRouteDetailFallback } = require("../../../mock/route-detail");

function normalizePayload(payload) {
  const route = payload?.route || {};
  const amapExport = route.amap_export || {};

  return {
    page: payload?.page || { title: route.title || "路线详情", eyebrow: "路线详情" },
    route: {
      ...route,
      amap_export: {
        ...amapExport,
        screenshot_url: amapExport.screenshot_href ? buildWebUrl(amapExport.screenshot_href) : "",
      },
    },
    detail_sections: {
      daily_plan: payload?.detail_sections?.daily_plan || [],
    },
  };
}

Page({
  data: {
    loading: true,
    error: "",
    page: { title: "路线详情", eyebrow: "路线详情" },
    route: { title: "", days: 0, amap_export: { screenshot_url: "" } },
    detailSections: { daily_plan: [] },
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
});