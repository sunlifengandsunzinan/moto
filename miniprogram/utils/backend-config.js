const DEFAULT_WEB_BASE_URL = "http://127.0.0.1:6001";
const DEFAULT_DEVICE_WEB_BASE_URL = "https://www.xingtu.ltd";
const TENCENT_MAP_SUBKEY = "4MABZ-BYQKZ-4CAXR-TZUQC-MRP6E-MHBDI";
const DEFAULT_API_BASE_URL = `${DEFAULT_WEB_BASE_URL}/api`;
const BACKEND_CONFIG_STORAGE_VERSION = 4;

const STORAGE_KEYS = {
  backendConfig: "backendConfig",
  legacyBackendConfigs: ["backendConfig.v2", "backendConfig.v3", "backendConfig.v4"],
  legacyApiBaseUrl: "apiBaseUrl",
  legacyWebBaseUrl: "webBaseUrl",
};

const API_PATHS = {
  routes: "/moto/routes",
  routeDetail(slug) {
    return `/moto/routes/${encodeURIComponent(String(slug || "").trim())}`;
  },
  routeWantGo(slug) {
    return `/moto/routes/${encodeURIComponent(String(slug || "").trim())}/want-go`;
  },
  spots: "/moto/spots",
  me: "/moto/me",
  meNavigationPreferences: "/moto/me/navigation-preferences",
};

const WEB_PATHS = {
  planner(origin) {
    return origin
      ? `/moto/planner?origin=${encodeURIComponent(origin)}`
      : "/moto/planner";
  },
  routesCollect: "/moto/routes/collect",
};

const MINI_PROGRAM_PATHS = {
  routesTab: "/pages/routes/index",
  spotsTab: "/pages/spots/index",
  meTab: "/pages/me/index",
  meFavorites: "/pages/me/favorites/index",
  meUpload: "/pages/me/upload/index",
  webview: "/pages/webview/index",
  routeDetail(slug) {
    return buildMiniProgramUrl("/pages/routes/detail/index", { slug });
  },
  webviewWithUrl(url) {
    return buildMiniProgramUrl("/pages/webview/index", { url });
  },
};

function buildMiniProgramUrl(path, query = {}) {
  const normalizedPath = String(path || "").trim();
  const search = Object.keys(query).reduce((params, key) => {
    const value = query[key];
    if (value === undefined || value === null || value === "") {
      return params;
    }

    params.push(`${encodeURIComponent(key)}=${encodeURIComponent(String(value))}`);
    return params;
  }, []);

  return search.length ? `${normalizedPath}?${search.join("&")}` : normalizedPath;
}

function getMiniProgramTabPath(tab) {
  switch (String(tab || "").trim()) {
    case "routes":
      return MINI_PROGRAM_PATHS.routesTab;
    case "spots":
      return MINI_PROGRAM_PATHS.spotsTab;
    case "me":
      return MINI_PROGRAM_PATHS.meTab;
    default:
      return "";
  }
}

function getMiniProgramNavigationUrl(action) {
  if (!action || typeof action !== "object") {
    return "";
  }

  switch (String(action.type || "").trim()) {
    case "route-detail":
      return MINI_PROGRAM_PATHS.routeDetail(action.slug);
    case "tab":
      return getMiniProgramTabPath(action.tab);
    case "webview":
      return MINI_PROGRAM_PATHS.webviewWithUrl(buildWebUrl(action.path || action.url || ""));
    default:
      return "";
  }
}

function getMiniProgramApiPath(action) {
  if (!action || typeof action !== "object" || String(action.type || "").trim() !== "api") {
    return "";
  }

  return normalizeRequestPath(action.path || "");
}

function getMiniProgramDownloadUrl(action) {
  if (!action || typeof action !== "object" || String(action.type || "").trim() !== "download") {
    return "";
  }

  return buildWebUrl(action.path || action.url || "");
}

function getMiniProgramQuery(action) {
  if (!action || typeof action !== "object" || String(action.type || "").trim() !== "spots-filter") {
    return {};
  }

  return action.query && typeof action.query === "object" ? action.query : {};
}

function getRuntimePlatform() {
  try {
    if (typeof wx.getDeviceInfo === "function") {
      const deviceInfo = wx.getDeviceInfo();
      if (deviceInfo && deviceInfo.platform) {
        return String(deviceInfo.platform).toLowerCase();
      }
    }
  } catch (_) {
    // Fall through to legacy system info lookup.
  }

  try {
    if (typeof wx.getSystemInfoSync === "function") {
      const systemInfo = wx.getSystemInfoSync();
      if (systemInfo && systemInfo.platform) {
        return String(systemInfo.platform).toLowerCase();
      }
    }
  } catch (_) {
    // Ignore runtime detection failure and fall back to localhost.
  }

  return "";
}

function getDefaultWebBaseUrl() {
  return getRuntimePlatform() === "devtools" ? DEFAULT_WEB_BASE_URL : DEFAULT_DEVICE_WEB_BASE_URL;
}

function getDefaultApiBaseUrl() {
  return `${getDefaultWebBaseUrl()}/api`;
}

function isLoopbackUrl(value) {
  return /^https?:\/\/(127\.0\.0\.1|localhost)(?::\d+)?(?=\/|$)/i.test(String(value || "").trim());
}

function normalizeRuntimeHost(value) {
  const rawValue = String(value || "").trim();
  if (!rawValue) {
    return "";
  }

  if (getRuntimePlatform() !== "devtools" && isLoopbackUrl(rawValue)) {
    return rawValue.replace(/^https?:\/\/(127\.0\.0\.1|localhost)(?::\d+)?(?=\/|$)/i, DEFAULT_DEVICE_WEB_BASE_URL);
  }

  return replaceLocalhostHost(rawValue);
}

function collapseDuplicatePort(value) {
  return String(value || "").replace(/^(https?:\/\/[^/:?#]+:\d+)(?::\d+)+(?=[/?#]|$)/i, "$1");
}

function replaceLocalhostHost(value) {
  return String(value || "").replace(/\/\/(127\.0\.0\.1|localhost)(?=[:/]|$)/i, "//127.0.0.1");
}

function normalizeBaseUrl(rawValue) {
  const value = collapseDuplicatePort(normalizeRuntimeHost(rawValue)).trim().replace(/\/+$/, "");
  if (!/^https?:\/\//.test(value)) {
    return "";
  }

  return value;
}

function normalizeApiBaseUrl(rawValue) {
  const value = normalizeBaseUrl(rawValue);
  if (!value) {
    return getDefaultApiBaseUrl();
  }

  return `${value.replace(/\/api(?:\/.*)?$/, "").replace(/\/moto(?:\/.*)?$/, "")}/api`;
}

function normalizeWebBaseUrl(rawValue) {
  const value = normalizeBaseUrl(rawValue);
  if (!value) {
    return getDefaultWebBaseUrl();
  }

  return value.replace(/\/api(?:\/.*)?$/, "");
}

function normalizeRequestPath(rawPath) {
  const value = String(rawPath || "").trim();
  if (!value) {
    return "/";
  }

  const strippedOrigin = value.replace(/^https?:\/\/[^/]+/i, "");
  const withoutApiPrefix = strippedOrigin.replace(/^\/api(?=\/|$)/, "");
  return withoutApiPrefix.startsWith("/") ? withoutApiPrefix : `/${withoutApiPrefix}`;
}

function joinUrl(baseUrl, path) {
  const normalizedBaseUrl = String(baseUrl || "").replace(/\/+$/, "");
  return `${normalizedBaseUrl}${normalizeRequestPath(path)}`;
}

function getStoredValue(key) {
  try {
    return wx.getStorageSync(key);
  } catch (_) {
    return "";
  }
}

function removeStoredValue(key) {
  try {
    wx.removeStorageSync(key);
  } catch (_) {
    // Ignore storage cleanup errors when sync storage is unavailable.
  }
}

function setStoredValue(key, value) {
  try {
    wx.setStorageSync(key, value);
  } catch (_) {
    // Ignore storage errors when sync storage is unavailable.
  }
}

function getLegacyStoredBackendConfig() {
  const legacyVersionedConfig = STORAGE_KEYS.legacyBackendConfigs.reduce((result, key) => {
    if (result.apiBaseUrl || result.webBaseUrl) {
      return result;
    }

    const storedValue = getStoredValue(key);
    if (!storedValue || typeof storedValue !== "object") {
      return result;
    }

    return {
      apiBaseUrl: String(storedValue.apiBaseUrl || "").trim(),
      webBaseUrl: String(storedValue.webBaseUrl || "").trim(),
    };
  }, { apiBaseUrl: "", webBaseUrl: "" });

  return {
    apiBaseUrl: legacyVersionedConfig.apiBaseUrl || getStoredValue(STORAGE_KEYS.legacyApiBaseUrl),
    webBaseUrl: legacyVersionedConfig.webBaseUrl || getStoredValue(STORAGE_KEYS.legacyWebBaseUrl),
  };
}

function getVersionedStoredBackendConfig() {
  const storedValue = getStoredValue(STORAGE_KEYS.backendConfig);
  if (!storedValue || typeof storedValue !== "object") {
    return {};
  }

  if (Number(storedValue.version || 0) !== BACKEND_CONFIG_STORAGE_VERSION) {
    removeStoredValue(STORAGE_KEYS.backendConfig);
    return {};
  }

  return {
    apiBaseUrl: String(storedValue.apiBaseUrl || "").trim(),
    webBaseUrl: String(storedValue.webBaseUrl || "").trim(),
  };
}

function clearLegacyStoredBackendConfig() {
  removeStoredValue(STORAGE_KEYS.legacyApiBaseUrl);
  removeStoredValue(STORAGE_KEYS.legacyWebBaseUrl);
  STORAGE_KEYS.legacyBackendConfigs.forEach((key) => removeStoredValue(key));
}

function resolveBackendConfig(source = {}) {
  const versionedStoredConfig = getVersionedStoredBackendConfig();
  const legacyStoredConfig = getLegacyStoredBackendConfig();

  return {
    apiBaseUrl: normalizeApiBaseUrl(
      source.apiBaseUrl || versionedStoredConfig.apiBaseUrl || legacyStoredConfig.apiBaseUrl || getDefaultApiBaseUrl(),
    ),
    webBaseUrl: normalizeWebBaseUrl(
      source.webBaseUrl || versionedStoredConfig.webBaseUrl || legacyStoredConfig.webBaseUrl || getDefaultWebBaseUrl(),
    ),
  };
}

function applyBackendConfig(app, source = {}) {
  const backendConfig = resolveBackendConfig(source);

  if (app && app.globalData) {
    app.globalData.apiBaseUrl = backendConfig.apiBaseUrl;
    app.globalData.webBaseUrl = backendConfig.webBaseUrl;
  }

  setStoredValue(STORAGE_KEYS.backendConfig, {
    version: BACKEND_CONFIG_STORAGE_VERSION,
    apiBaseUrl: backendConfig.apiBaseUrl,
    webBaseUrl: backendConfig.webBaseUrl,
  });
  clearLegacyStoredBackendConfig();

  return backendConfig;
}

function getBackendConfig() {
  const app = typeof getApp === "function" ? getApp() : null;
  return resolveBackendConfig(app?.globalData || {});
}

function getBackendDebugInfo() {
  const backendConfig = getBackendConfig();
  const platform = getRuntimePlatform() || "unknown";

  return {
    platform,
    storageKey: STORAGE_KEYS.backendConfig,
    storageVersion: BACKEND_CONFIG_STORAGE_VERSION,
    webBaseUrl: backendConfig.webBaseUrl,
    apiBaseUrl: backendConfig.apiBaseUrl,
  };
}

function buildApiUrl(path) {
  return joinUrl(getBackendConfig().apiBaseUrl, path);
}

function buildWebUrl(path) {
  if (!path) {
    return getBackendConfig().webBaseUrl;
  }

  if (/^https?:\/\//.test(path)) {
    return path;
  }

  return joinUrl(getBackendConfig().webBaseUrl, path);
}

module.exports = {
  API_PATHS,
  DEFAULT_API_BASE_URL,
  DEFAULT_DEVICE_WEB_BASE_URL,
  DEFAULT_WEB_BASE_URL,
  MINI_PROGRAM_PATHS,
  TENCENT_MAP_SUBKEY,
  WEB_PATHS,
  applyBackendConfig,
  buildApiUrl,
  buildWebUrl,
  buildMiniProgramUrl,
  getBackendDebugInfo,
  getDefaultApiBaseUrl,
  getDefaultWebBaseUrl,
  getMiniProgramApiPath,
  getMiniProgramDownloadUrl,
  getMiniProgramNavigationUrl,
  getMiniProgramQuery,
  normalizeRequestPath,
};