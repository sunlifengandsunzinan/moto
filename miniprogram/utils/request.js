const {
  DEFAULT_API_BASE_URL,
  buildApiUrl,
  buildWebUrl,
  normalizeRequestPath,
} = require("./backend-config");
const { getOrCreateUserId } = require("./user-session");

function request({ path, data = {}, method = "GET" }) {
  return new Promise((resolve, reject) => {
    const fallbackUrl = `${DEFAULT_API_BASE_URL}${normalizeRequestPath(path)}`;

    function send(url, allowFallback) {
      wx.request({
        url,
        data,
        method,
        header: {
          "X-Moto-User-Id": getOrCreateUserId(),
        },
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

    send(buildApiUrl(path), true);
  });
}

module.exports = {
  request,
  buildWebUrl,
};