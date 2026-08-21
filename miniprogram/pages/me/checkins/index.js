const { API_PATHS, MINI_PROGRAM_PATHS } = require("../../../utils/backend-config");
const { request } = require("../../../utils/request");

function formatRecordDateLabel(value) {
  const raw = String(value || "").trim();
  if (!raw) {
    return "-";
  }
  const normalized = raw.replace("T", " ").replace(/\.\d+$/, "");
  return normalized.slice(0, 16) || normalized;
}

function normalizeCheckinRecords(records) {
  const source = Array.isArray(records) ? records : [];
  return source.map((item) => {
    const checkedCount = Number(item?.checked_count || 0);
    const checkpointTotal = Number(item?.checkpoint_total || 0);
    const updatedAt = String(item?.updated_at || "").trim();
    return {
      key: `${String(item?.slug || "").trim()}-${updatedAt}`,
      slug: String(item?.slug || "").trim(),
      routeTitle: String(item?.route_title || "").trim() || "未命名路线",
      progressText: checkpointTotal > 0 ? `${checkedCount}/${checkpointTotal}` : String(checkedCount),
      updatedAtLabel: formatRecordDateLabel(updatedAt),
    };
  });
}

function hasLoggedWechatProfile(profile) {
  if (!profile || typeof profile !== "object") {
    return false;
  }

  const nickName = String(profile.nickName || "").trim();
  const avatarUrl = String(profile.avatarUrl || "").trim();
  return Boolean(nickName && avatarUrl && nickName !== "微信用户");
}

Page({
  data: {
    records: [],
    loading: true,
    error: "",
  },

  onLoad() {
    if (!this.ensureLoggedIn()) {
      return;
    }
    this.fetchRecords();
  },

  onShow() {
    if (!this.ensureLoggedIn()) {
      return;
    }
    this.fetchRecords();
  },

  onPullDownRefresh() {
    if (!this.ensureLoggedIn()) {
      wx.stopPullDownRefresh();
      return;
    }
    this.fetchRecords(true);
  },

  ensureLoggedIn() {
    const app = getApp();
    const profile = typeof app?.getWechatUserProfile === "function"
      ? app.getWechatUserProfile()
      : null;
    if (hasLoggedWechatProfile(profile)) {
      return true;
    }

    wx.showToast({ title: "请先登录", icon: "none" });
    wx.switchTab({
      url: MINI_PROGRAM_PATHS.meTab,
    });
    return false;
  },

  fetchRecords(stopRefresh = false) {
    this.setData({ loading: true, error: "" });

    request({ path: API_PATHS.me })
      .then((payload) => {
        const records = normalizeCheckinRecords((payload?.user_records || {}).checkins || []);
        this.setData({
          records,
          loading: false,
          error: "",
        });
      })
      .catch((error) => {
        this.setData({
          records: [],
          loading: false,
          error: String(error?.message || "加载失败"),
        });
      })
      .finally(() => {
        if (stopRefresh) {
          wx.stopPullDownRefresh();
        }
      });
  },

  handleOpenRoute(event) {
    const slug = String(event?.currentTarget?.dataset?.slug || "").trim();
    if (!slug) {
      return;
    }

    wx.navigateTo({
      url: MINI_PROGRAM_PATHS.routeDetail(slug),
    });
  },
});
