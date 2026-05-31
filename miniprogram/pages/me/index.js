const { request, buildWebUrl } = require("../../utils/request");
const { getFavoriteRoutes } = require("../../utils/favorites");
const { mePageFallback } = require("../../mock/me");

function mergeProfile(profile, wechatProfile) {
  const mergedProfile = { ...(profile || {}) };
  const activeWechatProfile = wechatProfile && typeof wechatProfile === "object" ? wechatProfile : null;
  const nickName = String(activeWechatProfile?.nickName || "").trim();
  const avatarUrl = String(activeWechatProfile?.avatarUrl || "").trim();
  const location = [activeWechatProfile?.province, activeWechatProfile?.city].filter(Boolean).join(" ");

  if (nickName) {
    mergedProfile.name = nickName;
  }
  if (location) {
    mergedProfile.tagline = location;
  }
  if (avatarUrl) {
    mergedProfile.avatar_url = avatarUrl;
  }

  if (nickName) {
    mergedProfile.summary = profile?.summary
      ? `微信用户 ${nickName} 已同步到当前小程序展示。${profile.summary}`
      : `微信用户 ${nickName} 已同步到当前小程序展示。`;
  }

  return mergedProfile;
}

Page({
  data: {
    loading: true,
    error: "",
    page: {},
    profile: {},
    baseProfile: {},
    metrics: [],
    sections: [],
    quickActions: [],
    wechatProfile: null,
    hasWechatProfile: false,
    profileLoading: false,
    favoriteRoutes: [],
    showFavoriteRoutes: false,
  },

  onLoad() {
    this.syncWechatProfile();
    this.syncFavoriteRoutes();
    this.fetchData();
  },

  onShow() {
    this.syncWechatProfile();
    this.syncFavoriteRoutes();
  },

  onPullDownRefresh() {
    this.fetchData(true);
  },

  fetchData(stopRefresh = false) {
    this.setData({ loading: true, error: "" });

    request({ path: "/moto/me" })
      .then((payload) => {
        const baseProfile = payload.profile || {};
        this.setData({
          loading: false,
          page: payload.page,
          baseProfile,
          profile: mergeProfile(baseProfile, this.data.wechatProfile),
          metrics: payload.metrics || [],
          sections: payload.sections || [],
          quickActions: payload.quick_actions || [],
        });
      })
      .catch((error) => {
        const baseProfile = mePageFallback.profile;
        this.setData({
          loading: false,
          error: "",
          page: mePageFallback.page,
          baseProfile,
          profile: mergeProfile(baseProfile, this.data.wechatProfile),
          metrics: mePageFallback.metrics || [],
          sections: mePageFallback.sections || [],
          quickActions: mePageFallback.quick_actions || [],
        });
        wx.showToast({
          title: "已切换本地演示数据",
          icon: "none",
          duration: 1800,
        });
      })
      .finally(() => {
        if (stopRefresh) {
          wx.stopPullDownRefresh();
        }
      });
  },

  syncFavoriteRoutes() {
    this.setData({
      favoriteRoutes: getFavoriteRoutes(),
    });
  },

  syncWechatProfile() {
    const app = getApp();
    const wechatProfile = app?.getWechatUserProfile ? app.getWechatUserProfile() : app?.globalData?.wechatUserProfile || null;
    this.setData({
      wechatProfile,
      hasWechatProfile: Boolean(wechatProfile),
    });

    if (Object.keys(this.data.baseProfile || {}).length) {
      this.setData({
        profile: mergeProfile(this.data.baseProfile, wechatProfile),
      });
    }
  },

  handleGetWechatProfile() {
    if (!wx.getUserProfile) {
      wx.showToast({
        title: "当前基础库不支持",
        icon: "none",
        duration: 1800,
      });
      return;
    }

    this.setData({ profileLoading: true });

    wx.getUserProfile({
      desc: "用于在“我的”页面展示你的微信头像和昵称",
      success: ({ userInfo }) => {
        const app = getApp();
        const wechatProfile = app?.setWechatUserProfile ? app.setWechatUserProfile(userInfo) : userInfo;
        this.setData({
          profileLoading: false,
          wechatProfile,
          hasWechatProfile: Boolean(wechatProfile),
          profile: mergeProfile(this.data.baseProfile, wechatProfile),
        });
      },
      fail: () => {
        this.setData({ profileLoading: false });
        wx.showToast({
          title: "未授权微信信息",
          icon: "none",
          duration: 1800,
        });
      },
    });
  },

  handleOpenHref(event) {
    const href = event.currentTarget.dataset.href;
    wx.navigateTo({
      url: `/pages/webview/index?url=${encodeURIComponent(buildWebUrl(href))}`,
    });
  },

  handleToggleFavoriteRoutes() {
    this.setData({
      showFavoriteRoutes: !this.data.showFavoriteRoutes,
      favoriteRoutes: getFavoriteRoutes(),
    });
  },

  handleOpenFavorite(event) {
    const slug = event.currentTarget.dataset.slug;
    if (!slug) {
      return;
    }

    wx.navigateTo({
      url: `/pages/routes/detail/index?slug=${encodeURIComponent(slug)}`,
    });
  },
});