const {
  DEFAULT_API_BASE_URL,
  DEFAULT_WEB_BASE_URL,
  applyBackendConfig,
} = require("./utils/backend-config");

App({
  globalData: {
    apiBaseUrl: DEFAULT_API_BASE_URL,
    webBaseUrl: DEFAULT_WEB_BASE_URL,
    wechatUserProfile: null,
  },

  onLaunch() {
    applyBackendConfig(this);
    this.globalData.wechatUserProfile = null;
  },

  getWechatUserProfile() {
    const storedProfile = wx.getStorageSync("wechatUserProfile");
    if (!storedProfile || typeof storedProfile !== "object") {
      return null;
    }

    const nickName = String(storedProfile.nickName || "").trim();
    const avatarUrl = String(storedProfile.avatarUrl || "").trim();
    if (!nickName && !avatarUrl) {
      return null;
    }

    return {
      nickName,
      avatarUrl,
      city: String(storedProfile.city || "").trim(),
      province: String(storedProfile.province || "").trim(),
      country: String(storedProfile.country || "").trim(),
      gender: Number(storedProfile.gender || 0),
    };
  },

  setWechatUserProfile(profile) {
    const normalizedProfile = profile && typeof profile === "object"
      ? {
          nickName: String(profile.nickName || "").trim(),
          avatarUrl: String(profile.avatarUrl || "").trim(),
          city: String(profile.city || "").trim(),
          province: String(profile.province || "").trim(),
          country: String(profile.country || "").trim(),
          gender: Number(profile.gender || 0),
        }
      : null;

    this.globalData.wechatUserProfile = normalizedProfile;

    if (normalizedProfile) {
      wx.setStorageSync("wechatUserProfile", normalizedProfile);
      return normalizedProfile;
    }

    wx.removeStorageSync("wechatUserProfile");
    return null;
  },
});