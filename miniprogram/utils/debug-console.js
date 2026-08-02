let vConsoleInstance = null;
let initAttempted = false;

function tryRequireVConsole() {
  try {
    return require("vconsole.miniprogram");
  } catch (_) {
    return null;
  }
}

function isDevtoolsPlatform() {
  try {
    const systemInfo = typeof wx.getSystemInfoSync === "function" ? wx.getSystemInfoSync() : null;
    return String(systemInfo?.platform || "").toLowerCase() === "devtools";
  } catch (_) {
    return false;
  }
}

function isVConsoleEnabledByFlag() {
  try {
    return wx.getStorageSync("enableVConsole") === true;
  } catch (_) {
    return false;
  }
}

function initDebugConsole() {
  if (initAttempted) {
    return null;
  }

  initAttempted = true;
  vConsoleInstance = null;
  return null;
}

module.exports = {
  initDebugConsole,
};
