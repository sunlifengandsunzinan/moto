const { API_PATHS, MINI_PROGRAM_PATHS } = require("../../utils/backend-config");
const { request } = require("../../utils/request");
const { getFavoriteRoutes } = require("../../utils/favorites");

const DEFAULT_AVATAR_TEXT = "行途";

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

function normalizeWechatProfileForDisplay(rawProfile) {
  if (!rawProfile || typeof rawProfile !== "object") {
    return null;
  }

  const source = rawProfile.userInfo && typeof rawProfile.userInfo === "object"
    ? rawProfile.userInfo
    : rawProfile;

  const nickName = String(
    source.nickName || source.nickname || source.nick_name || source.name || "",
  ).trim();
  const avatarUrl = String(
    source.avatarUrl || source.avatar || source.avatar_url || source.headImgUrl || "",
  ).trim();

  if (!nickName && !avatarUrl) {
    return null;
  }

  return {
    nickName: nickName || "微信用户",
    avatarUrl,
    city: String(source.city || "").trim(),
    province: String(source.province || "").trim(),
    country: String(source.country || "").trim(),
    gender: Number(source.gender || 0),
  };
}

function hasLoggedWechatProfile(profile) {
  if (!profile || typeof profile !== "object") {
    return false;
  }

  const nickName = String(profile.nickName || "").trim();
  const avatarUrl = String(profile.avatarUrl || "").trim();
  return Boolean(nickName || avatarUrl);
}

function formatWechatLocation(profile) {
  if (!profile || typeof profile !== "object") {
    return "";
  }

  const parts = [profile.province, profile.city].filter(Boolean);
  return parts.join(" · ");
}

function normalizeWechatProfilePayload(rawProfile) {
  if (!rawProfile || typeof rawProfile !== "object") {
    return null;
  }

  const source = rawProfile.userInfo && typeof rawProfile.userInfo === "object"
    ? rawProfile.userInfo
    : rawProfile;

  const nickName = String(
    source.nickName || source.nickname || source.nick_name || source.name || "",
  ).trim();
  const avatarUrl = String(
    source.avatarUrl || source.avatar || source.avatar_url || source.headImgUrl || "",
  ).trim();

  return {
    nickName: nickName || "微信用户",
    avatarUrl,
    city: String(source.city || "").trim(),
    province: String(source.province || "").trim(),
    country: String(source.country || "").trim(),
    gender: Number(source.gender || 0),
  };
}

function resolveAuthorizeErrorMessage(error) {
  const errMsg = String(error?.errMsg || "");
  if (errMsg.includes("auth deny") || errMsg.includes("auth denied") || errMsg.includes("cancel")) {
    return "已取消授权";
  }
  return "登录失败，请重试";
}

Page({
  data: {
    isAuthorizing: false,
    showWechatProfileEditor: false,
    draftWechatNickName: "",
    draftWechatAvatarUrl: "",
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
    isWechatLoggedIn: false,
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
    const storedProfile = typeof app?.getWechatUserProfile === "function"
      ? app.getWechatUserProfile()
      : null;
    const profile = normalizeWechatProfileForDisplay(storedProfile);
    const isWechatLoggedIn = hasLoggedWechatProfile(profile);

    if (!profile && storedProfile && typeof app?.setWechatUserProfile === "function") {
      app.setWechatUserProfile(null);
    }

    const displayProfile = buildDisplayProfile(profile);

    this.setData({
      wechatUserProfile: profile,
      wechatProfileLocation: formatWechatLocation(profile),
      displayName: displayProfile.displayName,
      avatarText: displayProfile.avatarText,
      isWechatLoggedIn,
      showWechatProfileEditor: !isWechatLoggedIn && this.data.showWechatProfileEditor,
      draftWechatNickName: profile?.nickName || this.data.draftWechatNickName,
      draftWechatAvatarUrl: profile?.avatarUrl || this.data.draftWechatAvatarUrl,
    });
  },

  handleShowWechatProfileEditor() {
    if (this.data.isWechatLoggedIn) {
      return;
    }

    this.setData({
      showWechatProfileEditor: true,
      draftWechatNickName: this.data.draftWechatNickName || "",
      draftWechatAvatarUrl: this.data.draftWechatAvatarUrl || "",
    });
  },

  handleCancelWechatProfileEditor() {
    this.setData({
      showWechatProfileEditor: false,
      draftWechatNickName: "",
      draftWechatAvatarUrl: "",
    });
  },

  handleChooseWechatAvatar(event) {
    const avatarUrl = String(event?.detail?.avatarUrl || "").trim();
    this.setData({
      draftWechatAvatarUrl: avatarUrl,
    });
  },

  handleWechatNicknameInput(event) {
    const nickName = String(event?.detail?.value || "").trim();
    this.setData({
      draftWechatNickName: nickName,
    });
  },

  handleSaveWechatProfileFromEditor() {
    const nickName = String(this.data.draftWechatNickName || "").trim() || "微信用户";
    const avatarUrl = String(this.data.draftWechatAvatarUrl || "").trim();

    if (!avatarUrl) {
      wx.showToast({ title: "请先选择头像", icon: "none" });
      return;
    }

    const app = getApp();
    const storedProfile = typeof app?.setWechatUserProfile === "function"
      ? app.setWechatUserProfile({
          nickName,
          avatarUrl,
        })
      : {
          nickName,
          avatarUrl,
        };
    const normalizedProfile = normalizeWechatProfileForDisplay(storedProfile);
    const isWechatLoggedIn = hasLoggedWechatProfile(normalizedProfile);

    const displayProfile = buildDisplayProfile(normalizedProfile);
    this.setData({
      wechatUserProfile: normalizedProfile,
      wechatProfileLocation: formatWechatLocation(normalizedProfile),
      displayName: displayProfile.displayName,
      avatarText: displayProfile.avatarText,
      isWechatLoggedIn,
      showWechatProfileEditor: false,
      draftWechatNickName: "",
      draftWechatAvatarUrl: "",
    });

    this.syncWechatProfile();
    wx.showToast({ title: "登录成功", icon: "none" });
  },

  handleAuthorizeWechatProfile() {
    if (this.data.isAuthorizing) {
      return;
    }

    this.setData({ isAuthorizing: true });

    const finishAuthorize = (profile) => {
      const normalizedProfile = normalizeWechatProfilePayload(profile);
      if (!normalizedProfile) {
        this.setData({ isAuthorizing: false });
        wx.showToast({ title: "未获取到微信头像昵称", icon: "none" });
        return;
      }

      const app = getApp();
      const storedProfile = typeof app?.setWechatUserProfile === "function"
        ? app.setWechatUserProfile(normalizedProfile)
        : normalizedProfile;
      const displayProfile = buildDisplayProfile(storedProfile);

      this.setData({
        isAuthorizing: false,
        wechatUserProfile: storedProfile,
        wechatProfileLocation: formatWechatLocation(storedProfile),
        displayName: displayProfile.displayName,
        avatarText: displayProfile.avatarText,
        isWechatLoggedIn: hasLoggedWechatProfile(storedProfile),
      });

      // Read back from app storage to keep UI and persisted state consistent.
      this.syncWechatProfile();

      if (storedProfile) {
        wx.showToast({ title: "登录成功", icon: "none" });
        return;
      }

      wx.showToast({ title: "未获取到微信头像昵称", icon: "none" });
    };

    const fallbackAuthorize = (originError) => {
      if (typeof wx.getUserInfo !== "function") {
        this.setData({ isAuthorizing: false });
        wx.showToast({ title: resolveAuthorizeErrorMessage(originError), icon: "none" });
        return;
      }

      wx.getUserInfo({
        lang: "zh_CN",
        success: (result) => {
          finishAuthorize(result);
        },
        fail: (error) => {
          this.setData({ isAuthorizing: false });
          wx.showToast({ title: resolveAuthorizeErrorMessage(error || originError), icon: "none" });
        },
      });
    };

    if (typeof wx.getUserProfile !== "function") {
      fallbackAuthorize({ errMsg: "getUserProfile unavailable" });
      return;
    }

    wx.getUserProfile({
      desc: "用于在我的页面展示微信头像和昵称",
      success: (result) => {
        finishAuthorize(result);
      },
      fail: (error) => {
        fallbackAuthorize(error);
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
      isWechatLoggedIn: false,
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
    if (this.data.isWechatLoggedIn) {
      wx.showToast({ title: "已登录", icon: "none" });
      return;
    }

    this.handleShowWechatProfileEditor();
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
      if (this.data.isWechatLoggedIn) {
        wx.showToast({ title: "已登录", icon: "none" });
        return;
      }
      this.handleShowWechatProfileEditor();
      return;
    }

    wx.showToast({ title: "功能建设中", icon: "none" });
  },
});