const { API_PATHS, MINI_PROGRAM_PATHS } = require("../../../utils/backend-config");
const { request } = require("../../../utils/request");

const WANT_GO_BUCKET_LABELS = {
  this_month: "这个月",
  next_month: "下个月",
  later: "再说",
};

function formatRecordDateLabel(value) {
  const raw = String(value || "").trim();
  if (!raw) {
    return "-";
  }
  const normalized = raw.replace("T", " ").replace(/\.\d+$/, "");
  return normalized.slice(0, 16) || normalized;
}

function normalizeWantGoRecords(records) {
  const source = Array.isArray(records) ? records : [];
  return source.map((item) => {
    const planBucket = String(item?.plan_bucket || "").trim();
    const planLabel = String(item?.plan_label || "").trim() || WANT_GO_BUCKET_LABELS[planBucket] || "未选择";
    const updatedAt = String(item?.updated_at || "").trim();
    return {
      key: `${String(item?.slug || "").trim()}-${updatedAt}`,
      slug: String(item?.slug || "").trim(),
      routeTitle: String(item?.route_title || "").trim() || "未命名路线",
      planLabel,
      updatedAtLabel: formatRecordDateLabel(updatedAt),
      status: String(item?.status || "active").trim() || "active",
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
    activeRecords: [],
    archivedRecords: [],
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
        const records = normalizeWantGoRecords((payload?.user_records || {}).want_go || []);
        const activeRecords = records.filter((item) => item.status !== "archived");
        const archivedRecords = records.filter((item) => item.status === "archived");
        this.setData({
          activeRecords,
          archivedRecords,
          loading: false,
          error: "",
        });
      })
      .catch((error) => {
        this.setData({
          activeRecords: [],
          archivedRecords: [],
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
