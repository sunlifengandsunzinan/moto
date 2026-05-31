const DEFAULT_API_BASE_URL = "http://192.168.0.119:6001/api";
const DEFAULT_WEB_BASE_URL = "http://192.168.0.119:6001";

function replaceLocalhostHost(value) {
  return String(value || "").replace(/\/\/(127\.0\.0\.1|localhost)(?=[:/]|$)/i, "//192.168.0.119");
}

function normalizeBaseUrl(rawValue) {
  const value = replaceLocalhostHost(rawValue).trim().replace(/\/+$/, "");
  if (!/^https?:\/\//.test(value)) {
    return "";
  }

  return value;
}

function normalizeApiBaseUrl(rawValue) {
  const value = normalizeBaseUrl(rawValue);
  if (!value) {
    return DEFAULT_API_BASE_URL;
  }

  return `${value.replace(/\/api(?:\/.*)?$/, "").replace(/\/moto(?:\/.*)?$/, "")}/api`;
}

function normalizeWebBaseUrl(rawValue) {
  const value = normalizeBaseUrl(rawValue);
  if (!value) {
    return DEFAULT_WEB_BASE_URL;
  }

  return value.replace(/\/api(?:\/.*)?$/, "");
}

App({
  globalData: {
    apiBaseUrl: DEFAULT_API_BASE_URL,
    webBaseUrl: DEFAULT_WEB_BASE_URL,
  },

  onLaunch() {
    const savedApiBaseUrl = wx.getStorageSync("apiBaseUrl");
    const savedWebBaseUrl = wx.getStorageSync("webBaseUrl");
    const apiBaseUrl = normalizeApiBaseUrl(savedApiBaseUrl || DEFAULT_API_BASE_URL);
    const webBaseUrl = normalizeWebBaseUrl(savedWebBaseUrl || DEFAULT_WEB_BASE_URL);

    this.globalData.apiBaseUrl = apiBaseUrl;
    this.globalData.webBaseUrl = webBaseUrl;

    if (savedApiBaseUrl !== apiBaseUrl) {
      wx.setStorageSync("apiBaseUrl", apiBaseUrl);
    }

    if (savedWebBaseUrl !== webBaseUrl) {
      wx.setStorageSync("webBaseUrl", webBaseUrl);
    }
  },
});