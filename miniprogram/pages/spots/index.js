const { request, buildWebUrl } = require("../../utils/request");
const {
  API_PATHS,
  MINI_PROGRAM_PATHS,
  WEB_PATHS,
  getMiniProgramNavigationUrl,
  getMiniProgramQuery,
} = require("../../utils/backend-config");

const AUTO_SYNC_COOLDOWN_MS = 20 * 1000;

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

function navigateByAction(action, fallbackHref = "") {
  const targetUrl = getMiniProgramNavigationUrl(action);
  if (targetUrl) {
    wx.navigateTo({ url: targetUrl });
    return;
  }

  if (fallbackHref) {
    wx.navigateTo({ url: MINI_PROGRAM_PATHS.webviewWithUrl(buildWebUrl(fallbackHref)) });
  }
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
    this._skipNextOnShowSync = true;
    this.fetchData();
  },

  onShow() {
    if (this._skipNextOnShowSync) {
      this._skipNextOnShowSync = false;
      return;
    }

    this.syncOnShow();
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

  fetchData(query = {}, stopRefresh = false, options = {}) {
    const silent = Boolean(options && options.silent);
    if (!silent) {
      this.setData({ loading: true, error: "" });
    }

    request({ path: API_PATHS.spots, data: query })
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
        this._lastSyncedAt = Date.now();
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

  syncOnShow() {
    if (this.data.loading) {
      return;
    }

    const lastSyncedAt = Number(this._lastSyncedAt || 0);
    const now = Date.now();
    if (lastSyncedAt > 0 && now - lastSyncedAt < AUTO_SYNC_COOLDOWN_MS) {
      return;
    }

    this.fetchData(this.buildQuery(), false, { silent: true });
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
    const group = this.data.quickGroups[Number(event.currentTarget.dataset.groupIndex)] || { items: [] };
    const item = group.items[Number(event.currentTarget.dataset.itemIndex)] || {};
    const query = getMiniProgramQuery(item.mini_program_action);
    this.fetchData(Object.keys(query).length ? query : parseHrefQuery(event.currentTarget.dataset.href));
  },

  handleReset() {
    this.fetchData({});
  },

  handleOpenSpot(event) {
    const spot = this.data.spots[Number(event.currentTarget.dataset.index)] || {};
    navigateByAction(spot.mini_program_action, event.currentTarget.dataset.href);
  },

  handleOpenPlanner(event) {
    const origin = event.currentTarget.dataset.origin;
    const path = WEB_PATHS.planner(origin);
    wx.navigateTo({
      url: MINI_PROGRAM_PATHS.webviewWithUrl(buildWebUrl(path)),
    });
  },
});