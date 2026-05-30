const { request, buildWebUrl } = require("../../utils/request");

function findOptionIndex(options, value) {
  const index = options.findIndex((item) => item.value === value);
  return index >= 0 ? index : 0;
}

function parseHrefQuery(href) {
  if (!href || href.indexOf("?") === -1) {
    return {};
  }

  const queryString = href.split("?")[1];
  return queryString.split("&").reduce((result, pair) => {
    if (!pair) {
      return result;
    }

    const [rawKey, rawValue = ""] = pair.split("=");
    const key = decodeURIComponent(rawKey || "");
    const value = decodeURIComponent(rawValue || "");

    if (key) {
      result[key] = value;
    }

    return result;
  }, {});
}

Page({
  data: {
    loading: true,
    error: "",
    page: {},
    stats: {},
    spots: [],
    quickGroups: [],
    activeFilters: [],
    hasActiveFilters: false,
    regionOptions: [],
    routeTypeOptions: [],
    supportOptions: [],
    regionValue: "",
    routeTypeValue: "",
    supportValue: "",
    regionIndex: 0,
    routeTypeIndex: 0,
    supportIndex: 0,
  },

  onLoad() {
    this.fetchData();
  },

  onPullDownRefresh() {
    this.fetchData(this.buildQuery(), true);
  },

  buildQuery(overrides = {}) {
    return {
      region: overrides.region !== undefined ? overrides.region : this.data.regionValue,
      route_type: overrides.route_type !== undefined ? overrides.route_type : this.data.routeTypeValue,
      support: overrides.support !== undefined ? overrides.support : this.data.supportValue,
    };
  },

  fetchData(query = {}, stopRefresh = false) {
    this.setData({ loading: true, error: "" });

    request({ path: "/moto/spots", data: query })
      .then((payload) => {
        const fields = payload.filters.fields || [];
        const regionField = fields[0] || { options: [], value: "" };
        const routeTypeField = fields[1] || { options: [], value: "" };
        const supportField = fields[2] || { options: [], value: "" };

        this.setData({
          loading: false,
          page: payload.page,
          stats: payload.stats,
          spots: payload.spots || [],
          quickGroups: payload.filters.quick_groups || [],
          activeFilters: payload.filters.active_filters || [],
          hasActiveFilters: !!payload.filters.has_active_filters,
          regionOptions: regionField.options || [],
          routeTypeOptions: routeTypeField.options || [],
          supportOptions: supportField.options || [],
          regionValue: regionField.value || "",
          routeTypeValue: routeTypeField.value || "",
          supportValue: supportField.value || "",
          regionIndex: findOptionIndex(regionField.options || [], regionField.value || ""),
          routeTypeIndex: findOptionIndex(routeTypeField.options || [], routeTypeField.value || ""),
          supportIndex: findOptionIndex(supportField.options || [], supportField.value || ""),
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

  handleRegionChange(event) {
    const option = this.data.regionOptions[Number(event.detail.value)] || { value: "" };
    this.fetchData(this.buildQuery({ region: option.value }));
  },

  handleRouteTypeChange(event) {
    const option = this.data.routeTypeOptions[Number(event.detail.value)] || { value: "" };
    this.fetchData(this.buildQuery({ route_type: option.value }));
  },

  handleSupportChange(event) {
    const option = this.data.supportOptions[Number(event.detail.value)] || { value: "" };
    this.fetchData(this.buildQuery({ support: option.value }));
  },

  handleQuickFilter(event) {
    const href = event.currentTarget.dataset.href;
    this.fetchData(parseHrefQuery(href));
  },

  handleReset() {
    this.fetchData({});
  },

  handleOpenSpot(event) {
    const href = event.currentTarget.dataset.href;
    wx.navigateTo({
      url: `/pages/webview/index?url=${encodeURIComponent(buildWebUrl(href))}`,
    });
  },

  handleOpenPlanner(event) {
    const origin = event.currentTarget.dataset.origin;
    const path = origin ? `/moto/planner?origin=${encodeURIComponent(origin)}` : "/moto/planner";
    wx.navigateTo({
      url: `/pages/webview/index?url=${encodeURIComponent(buildWebUrl(path))}`,
    });
  },
});