const { API_PATHS, MINI_PROGRAM_PATHS } = require("../../utils/backend-config");
const { request } = require("../../utils/request");
const { getFavoriteRoutes } = require("../../utils/favorites");

const DEFAULT_AVATAR_TEXT = "骑";

function normalizeMetricList(metrics, favoriteRouteCount) {
  const sourceMetrics = Array.isArray(metrics) ? metrics : [];
  const defaults = [
    { key: "ranking", value: "27", label: "我的排名" },
    { key: "points", value: "0", label: "我的积分" },
    { key: "cards", value: "0", label: "我的卡券" },
  ];

  return defaults.map((fallback, index) => {
    const source = sourceMetrics[index] || {};
    if (index === 1) {
      return {
        key: fallback.key,
        value: String(favoriteRouteCount || 0),
        label: fallback.label,
      };
    }

    return {
      key: fallback.key,
      value: String(source.value ?? fallback.value),
      label: String(source.label || fallback.label),
    };
  });
}

function normalizeQuickActions(sections) {
  const preferredLabels = [
    "VIP识别",
    "活动照片",
    "我的打卡",
    "团队管理",
    "我的排名",
    "个人档案",
    "车辆管理",
    "团队排名",
    "驿站入驻",
    "商户报名",
  ];
  const fallbackIcons = ["▦", "⚑", "⌖", "◌", "▥", "☰", "⛭", "◎", "▤", "☑"];

  const sourceItems = (Array.isArray(sections) ? sections : [])
    .flatMap((section) => (Array.isArray(section?.items) ? section.items : []));

  return preferredLabels.map((label, index) => {
    const source = sourceItems[index] || {};
    return {
      key: `action-${index + 1}`,
      label,
      icon: fallbackIcons[index] || "•",
      miniProgramAction: source.mini_program_action || null,
      href: String(source.href || ""),
      description: String(source.description || ""),
    };
  });
}

function normalizeMePayload(payload, favoriteRouteCount) {
  const safePayload = payload || {};
  return {
    page: safePayload.page || { title: "我的" },
    profile: safePayload.profile || {},
    metrics: normalizeMetricList(safePayload.metrics, favoriteRouteCount),
    quickActions: normalizeQuickActions(safePayload.sections),
  };
}

function buildDisplayProfile(wechatUserProfile) {
  const nickName = String(wechatUserProfile?.nickName || "").trim();
  return {
    displayName: nickName || "点击登录",
    avatarText: nickName ? nickName.slice(0, 1) : DEFAULT_AVATAR_TEXT,
  };
}

function formatWechatLocation(profile) {
  if (!profile || typeof profile !== "object") {
    return "";
  }

  const parts = [profile.province, profile.city].filter(Boolean);
  return parts.join(" · ");
}

Page({
  data: {
    isAuthorizing: false,
    favoriteRouteCount: 0,
    wechatProfileLocation: "",
    wechatUserProfile: null,
    page: { title: "我的" },
    profile: { name: "点击登录", tagline: "", summary: "" },
    metrics: [],
    quickActions: [],
    loading: true,
    error: "",
    displayName: "点击登录",
    avatarText: DEFAULT_AVATAR_TEXT,
  },

  onLoad() {
    this.syncWechatProfile();
    this.syncFavoriteRoutes();
    this.fetchMePage();
  },

  onShow() {
    this.syncWechatProfile();
    this.syncFavoriteRoutes();
  },

  onPullDownRefresh() {
    this.syncWechatProfile();
    this.syncFavoriteRoutes();
    this.fetchMePage(true);
  },

  syncFavoriteRoutes(stopRefresh = false) {
    const favoriteRoutes = getFavoriteRoutes();
    const favoriteRouteCount = favoriteRoutes.length;
    this.setData({
      favoriteRouteCount,
      metrics: normalizeMetricList(this.data.metrics, favoriteRouteCount),
    });

    if (stopRefresh) {
      wx.stopPullDownRefresh();
    }
  },

  fetchMePage(stopRefresh = false) {
    this.setData({ loading: true, error: "" });

    request({ path: API_PATHS.me })
      .then((payload) => {
        const normalized = normalizeMePayload(payload, this.data.favoriteRouteCount);
        this.setData({
          loading: false,
          error: "",
          page: normalized.page,
          profile: normalized.profile,
          metrics: normalized.metrics,
          quickActions: normalized.quickActions,
        });
      })
      .catch((error) => {
        this.setData({
          loading: false,
          error: error?.message || "加载我的页面失败",
          metrics: normalizeMetricList([], this.data.favoriteRouteCount),
          quickActions: normalizeQuickActions([]),
        });
      })
      .finally(() => {
        if (stopRefresh) {
          wx.stopPullDownRefresh();
        }
      });
  },

  syncWechatProfile() {
    const app = getApp();
    const profile = typeof app?.getWechatUserProfile === "function"
      ? app.getWechatUserProfile()
      : null;
    const displayProfile = buildDisplayProfile(profile);

    this.setData({
      wechatUserProfile: profile,
      wechatProfileLocation: formatWechatLocation(profile),
      displayName: displayProfile.displayName,
      avatarText: displayProfile.avatarText,
    });
  },

  handleAuthorizeWechatProfile() {
    if (this.data.isAuthorizing) {
      return;
    }

    if (typeof wx.getUserProfile !== "function") {
      wx.showToast({
        title: "当前基础库不支持",
        icon: "none",
      });
      return;
    }

    this.setData({ isAuthorizing: true });

    wx.getUserProfile({
      desc: "用于在我的页面展示微信头像和昵称",
      success: (result) => {
        const profile = result && result.userInfo ? result.userInfo : null;
        const app = getApp();
        const storedProfile = typeof app?.setWechatUserProfile === "function"
          ? app.setWechatUserProfile(profile)
          : profile;
        const displayProfile = buildDisplayProfile(storedProfile);

        this.setData({
          isAuthorizing: false,
          wechatUserProfile: storedProfile,
          wechatProfileLocation: formatWechatLocation(storedProfile),
          displayName: displayProfile.displayName,
          avatarText: displayProfile.avatarText,
        });
      },
      fail: () => {
        this.setData({ isAuthorizing: false });
      },
    });
  },

  handleClearWechatProfile() {
    const app = getApp();
    if (typeof app?.setWechatUserProfile === "function") {
      app.setWechatUserProfile(null);
    }

    this.setData({
      wechatUserProfile: null,
      wechatProfileLocation: "",
      displayName: "点击登录",
      avatarText: DEFAULT_AVATAR_TEXT,
    });

    wx.showToast({
      title: "已清除资料",
      icon: "none",
    });
  },

  handleOpenFavorites() {
    wx.navigateTo({
      url: MINI_PROGRAM_PATHS.meFavorites,
    });
  },

  handleOpenUpload() {
    wx.navigateTo({
      url: MINI_PROGRAM_PATHS.meUpload,
    });
  },

  handleOpenPrivacyPolicy() {
    wx.navigateTo({
      url: "/pages/me/privacy/index",
    });
  },

  handleOpenUserTerms() {
    wx.navigateTo({
      url: "/pages/me/terms/index",
    });
  },

  handleHeroTap() {
    if (this.data.wechatUserProfile) {
      wx.showToast({ title: "已登录", icon: "none" });
      return;
    }

    this.handleAuthorizeWechatProfile();
  },

  handleQuickAction(event) {
    const action = this.data.quickActions[Number(event.currentTarget.dataset.index)];
    if (!action) {
      return;
    }

    if (action.label === "我的排名") {
      this.handleOpenFavorites();
      return;
    }

    if (action.label === "个人档案") {
      if (this.data.wechatUserProfile) {
        wx.showToast({ title: "已登录", icon: "none" });
        return;
      }
      this.handleAuthorizeWechatProfile();
      return;
    }

    wx.showToast({ title: "功能建设中", icon: "none" });
  },
});