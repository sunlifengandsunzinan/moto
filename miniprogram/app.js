App({
  globalData: {
    apiBaseUrl: "http://127.0.0.1:6001/api",
    webBaseUrl: "http://127.0.0.1:6001",
  },

  onLaunch() {
    const savedApiBaseUrl = wx.getStorageSync("apiBaseUrl");
    const savedWebBaseUrl = wx.getStorageSync("webBaseUrl");

    if (savedApiBaseUrl) {
      this.globalData.apiBaseUrl = savedApiBaseUrl;
    }

    if (savedWebBaseUrl) {
      this.globalData.webBaseUrl = savedWebBaseUrl;
    }
  },
});