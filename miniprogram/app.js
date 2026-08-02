const {
  DEFAULT_API_BASE_URL,
  DEFAULT_WEB_BASE_URL,
  applyBackendConfig,
} = require("./utils/backend-config");
const { initDebugConsole } = require("./utils/debug-console");

App({
  globalData: {
    apiBaseUrl: DEFAULT_API_BASE_URL,
    webBaseUrl: DEFAULT_WEB_BASE_URL,
    wechatUserProfile: null,
  },

  onLaunch() {
    applyBackendConfig(this);
    initDebugConsole();
    this.globalData.wechatUserProfile = null;
  },

  getWechatUserProfile() {
    const storedProfile = wx.getStorageSync("wechatUserProfile");
    if (!storedProfile || typeof storedProfile !== "object") {
      return null;
    }

    const nickName = String(
      storedProfile.nickName || storedProfile.nickname || storedProfile.nick_name || "",
    ).trim();
    const avatarUrl = String(
      storedProfile.avatarUrl || storedProfile.avatar || storedProfile.avatar_url || storedProfile.headImgUrl || "",
    ).trim();

    return {
      nickName: nickName || "微信用户",
      avatarUrl,
      city: String(storedProfile.city || "").trim(),
      province: String(storedProfile.province || "").trim(),
      country: String(storedProfile.country || "").trim(),
      gender: Number(storedProfile.gender || 0),
    };
  },

  setWechatUserProfile(profile) {
    const source = profile && typeof profile === "object"
      ? (profile.userInfo && typeof profile.userInfo === "object" ? profile.userInfo : profile)
      : null;

    const normalizedProfile = source
      ? {
          nickName: String(
            source.nickName || source.nickname || source.nick_name || source.name || "",
          ).trim(),
          avatarUrl: String(
            source.avatarUrl || source.avatar || source.avatar_url || source.headImgUrl || "",
          ).trim(),
          city: String(source.city || "").trim(),
          province: String(source.province || "").trim(),
          country: String(source.country || "").trim(),
          gender: Number(source.gender || 0),
        }
      : null;

    const sanitizedProfile = normalizedProfile
      ? {
          ...normalizedProfile,
          nickName: normalizedProfile.nickName || "微信用户",
        }
      : null;

    this.globalData.wechatUserProfile = sanitizedProfile;

    if (sanitizedProfile) {
      wx.setStorageSync("wechatUserProfile", sanitizedProfile);
      return sanitizedProfile;
    }

    wx.removeStorageSync("wechatUserProfile");
    return null;
  },
});