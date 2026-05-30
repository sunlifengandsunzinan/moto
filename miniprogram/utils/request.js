const DEFAULT_API_BASE_URL = "http://127.0.0.1:6001/api";
const DEFAULT_WEB_BASE_URL = "http://127.0.0.1:6001";

function getApiBaseUrl() {
  const app = getApp();
  return app?.globalData?.apiBaseUrl || DEFAULT_API_BASE_URL;
}

function getWebBaseUrl() {
  const app = getApp();
  return app?.globalData?.webBaseUrl || DEFAULT_WEB_BASE_URL;
}

function request({ path, data = {}, method = "GET" }) {
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${getApiBaseUrl()}${path}`,
      data,
      method,
      success: (response) => {
        const { statusCode, data: payload } = response;

        if (statusCode >= 200 && statusCode < 300) {
          resolve(payload);
          return;
        }

        reject(new Error(payload?.message || `Request failed with status ${statusCode}`));
      },
      fail: () => {
        reject(new Error("无法连接 Flask 接口，请确认后端运行在配置地址。"));
      },
    });
  });
}

function buildWebUrl(path) {
  if (!path) {
    return getWebBaseUrl();
  }

  if (/^https?:\/\//.test(path)) {
    return path;
  }

  return `${getWebBaseUrl()}${path}`;
}

module.exports = {
  request,
  buildWebUrl,
};