const { MINI_PROGRAM_PATHS } = require("../../utils/backend-config");
const { getFavoriteRoutes } = require("../../utils/favorites");

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
  },

  onLoad() {
    this.syncWechatProfile();
    this.syncFavoriteRoutes();
  },

  onShow() {
    this.syncWechatProfile();
    this.syncFavoriteRoutes();
  },

  onPullDownRefresh() {
    this.syncWechatProfile();
    this.syncFavoriteRoutes(true);
  },

  syncFavoriteRoutes(stopRefresh = false) {
    const favoriteRoutes = getFavoriteRoutes();
    this.setData({ favoriteRouteCount: favoriteRoutes.length });

    if (stopRefresh) {
      wx.stopPullDownRefresh();
    }
  },

  syncWechatProfile() {
    const app = getApp();
    const profile = typeof app?.getWechatUserProfile === "function"
      ? app.getWechatUserProfile()
      : null;

    this.setData({
      wechatUserProfile: profile,
      wechatProfileLocation: formatWechatLocation(profile),
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

        this.setData({
          isAuthorizing: false,
          wechatUserProfile: storedProfile,
          wechatProfileLocation: formatWechatLocation(storedProfile),
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
});