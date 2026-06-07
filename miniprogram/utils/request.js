const DEFAULT_API_BASE_URL = "http://127.0.0.1:6001/api";
const DEFAULT_WEB_BASE_URL = "http://127.0.0.1:6001";

function replaceLocalhostHost(value) {
  return String(value || "").replace(/\/\/(127\.0\.0\.1|localhost)(?=[:/]|$)/i, "//127.0.0.1");
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

function joinUrl(baseUrl, path) {
  const normalizedBaseUrl = baseUrl.replace(/\/+$/, "");
  const normalizedPath = String(path || "").startsWith("/") ? path : `/${path || ""}`;
  return `${normalizedBaseUrl}${normalizedPath}`;
}

function getApiBaseUrl() {
  const app = getApp();
  return normalizeApiBaseUrl(app?.globalData?.apiBaseUrl || DEFAULT_API_BASE_URL);
}

function getWebBaseUrl() {
  const app = getApp();
  return normalizeWebBaseUrl(app?.globalData?.webBaseUrl || DEFAULT_WEB_BASE_URL);
}

function request({ path, data = {}, method = "GET" }) {
  return new Promise((resolve, reject) => {
    const fallbackUrl = joinUrl(DEFAULT_API_BASE_URL, path);

    function send(url, allowFallback) {
      wx.request({
        url,
        data,
        method,
        success: (response) => {
          const { statusCode, data: payload } = response;

          if (statusCode >= 200 && statusCode < 300) {
            resolve(payload);
            return;
          }

          if (statusCode === 404 && allowFallback && url !== fallbackUrl) {
            send(fallbackUrl, false);
            return;
          }

          reject(new Error(payload?.message || `Request failed with status ${statusCode}`));
        },
        fail: () => {
          reject(new Error("无法连接 Flask 接口，请确认后端运行在配置地址。"));
        },
      });
    }

    send(joinUrl(getApiBaseUrl(), path), true);
  });
}

function buildWebUrl(path) {
  if (!path) {
    return getWebBaseUrl();
  }

  if (/^https?:\/\//.test(path)) {
    return path;
  }

  return joinUrl(getWebBaseUrl(), path);
}

module.exports = {
  request,
  buildWebUrl,
};