const { API_PATHS, MINI_PROGRAM_PATHS } = require("../../utils/backend-config");
const { request } = require("../../utils/request");

const DEFAULT_AVATAR_TEXT = "行途";

function normalizeMetricList(metrics) {
  const sourceMetrics = Array.isArray(metrics) ? metrics : [];
  const sourceByLabel = sourceMetrics.reduce((result, item) => {
    const label = String(item?.label || "").trim();
    if (label) {
      result[label] = item;
    }
    return result;
  }, {});

  const defaults = [
    { key: "want-go", value: "0", label: "我想去的" },
    { key: "checkins", value: "0", label: "我打卡过的" },
  ];

  return defaults.map((fallback) => {
    const source = sourceByLabel[fallback.label] || {};
    return {
      key: fallback.key,
      value: String(source.value ?? fallback.value),
      label: fallback.label,
    };
  });
}

function normalizeQuickActions(sections) {
  const preferredLabels = [
    "爱车保养",
    "我的收集册",
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
  const fallbackIcons = ["▦", "◍", "⚑", "⌖", "◌", "▥", "☰", "⛭", "◎", "▤", "☑"];

  const sourceItems = (Array.isArray(sections) ? sections : [])
    .flatMap((section) => (Array.isArray(section?.items) ? section.items : []));

  return preferredLabels.map((label, index) => {
    const source = sourceItems[index] || {};
    return {
      key: `action-${index + 1}`,
      label,
      icon: fallbackIcons[index] || "•",
      isVisible: index <= 1,
      miniProgramAction: source.mini_program_action || null,
      href: String(source.href || ""),
      description: String(source.description || ""),
    };
  });
}

function normalizeMePayload(payload) {
  const safePayload = payload || {};
  return {
    page: safePayload.page || { title: "我的" },
    profile: safePayload.profile || {},
    metrics: normalizeMetricList(safePayload.metrics),
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
  return Boolean(nickName && avatarUrl && nickName !== "微信用户");
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
    showClubFeatureModal: false,
  },

  _lastSyncedProfileSignature: "",

  onLoad() {
    this.syncWechatProfile();
    this.fetchMePage();
  },

  onShow() {
    this.syncWechatProfile();
    this.fetchMePage();
  },

  onPullDownRefresh() {
    this.syncWechatProfile();
    this.fetchMePage(true);
  },

  fetchMePage(stopRefresh = false) {
    this.setData({ loading: true, error: "" });

    request({ path: API_PATHS.me })
      .then((payload) => {
        const normalized = normalizeMePayload(payload);
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
          metrics: normalizeMetricList([]),
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

    if (!isWechatLoggedIn && storedProfile && typeof app?.setWechatUserProfile === "function") {
      app.setWechatUserProfile(null);
    }

    const safeProfile = isWechatLoggedIn ? profile : null;
    const displayProfile = buildDisplayProfile(safeProfile);

    this.setData({
      wechatUserProfile: safeProfile,
      wechatProfileLocation: formatWechatLocation(safeProfile),
      displayName: displayProfile.displayName,
      avatarText: displayProfile.avatarText,
      isWechatLoggedIn,
      showWechatProfileEditor: !isWechatLoggedIn && this.data.showWechatProfileEditor,
      draftWechatNickName: profile?.nickName || this.data.draftWechatNickName,
      draftWechatAvatarUrl: profile?.avatarUrl || this.data.draftWechatAvatarUrl,
    });

    this.syncWechatProfileToBackend(safeProfile, { silent: true });
  },

  syncWechatProfileToBackend(profile, options = {}) {
    const normalizedProfile = normalizeWechatProfilePayload(profile);
    if (!hasLoggedWechatProfile(normalizedProfile)) {
      this._lastSyncedProfileSignature = "";
      return Promise.resolve(null);
    }

    const signature = JSON.stringify({
      nickName: normalizedProfile.nickName,
      avatarUrl: normalizedProfile.avatarUrl,
      city: normalizedProfile.city,
      province: normalizedProfile.province,
      country: normalizedProfile.country,
      gender: normalizedProfile.gender,
    });
    if (signature === this._lastSyncedProfileSignature) {
      return Promise.resolve(null);
    }

    return request({
      path: API_PATHS.meProfile,
      method: "POST",
      data: normalizedProfile,
    })
      .then((payload) => {
        if (payload?.ok) {
          this._lastSyncedProfileSignature = signature;
        }
        return payload;
      })
      .catch((error) => {
        if (!options.silent) {
          wx.showToast({ title: error?.message || "同步资料失败", icon: "none" });
        }
        return null;
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

      if (!hasLoggedWechatProfile(normalizedProfile)) {
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

      if (hasLoggedWechatProfile(storedProfile)) {
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
      showWechatProfileEditor: false,
      draftWechatNickName: "",
      draftWechatAvatarUrl: "",
    });
    this._lastSyncedProfileSignature = "";

    wx.showToast({
      title: "已清除资料",
      icon: "none",
    });
  },

  handleLogout() {
    wx.showModal({
      title: "退出登录",
      content: "确认退出当前微信登录状态？",
      success: (result) => {
        if (!result.confirm) {
          return;
        }

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
          showWechatProfileEditor: false,
          draftWechatNickName: "",
          draftWechatAvatarUrl: "",
        });
        this._lastSyncedProfileSignature = "";

        wx.showToast({ title: "已退出登录", icon: "none" });
      },
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

  handleOpenClubFeatureModal() {
    this.setData({ showClubFeatureModal: true });
  },

  handleCloseClubFeatureModal() {
    this.setData({ showClubFeatureModal: false });
  },

  noop() {},

  handleQuickAction(event) {
    const action = this.data.quickActions[Number(event.currentTarget.dataset.index)];
    if (!action || action.isVisible === false) {
      return;
    }

    if (action.label === "我的排名") {
      this.handleOpenFavorites();
      return;
    }

    if (action.label === "我的收集册") {
      if (!this.data.isWechatLoggedIn) {
        wx.showToast({ title: "请先登录", icon: "none" });
        this.handleShowWechatProfileEditor();
        return;
      }
      wx.navigateTo({
        url: MINI_PROGRAM_PATHS.meCollection,
      });
      return;
    }

    if (action.label === "爱车保养") {
      if (!this.data.isWechatLoggedIn) {
        wx.showToast({ title: "请先登录", icon: "none" });
        this.handleShowWechatProfileEditor();
        return;
      }
      wx.navigateTo({
        url: MINI_PROGRAM_PATHS.meVehicles,
      });
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