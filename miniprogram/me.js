const { MINI_PROGRAM_PATHS } = require("./utils/backend-config");

Page({
  onLoad() {
    wx.switchTab({
      url: MINI_PROGRAM_PATHS.meTab,
    });
  },
});