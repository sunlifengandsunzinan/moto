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

function initDebugConsole() {
  if (initAttempted) {
    return vConsoleInstance;
  }

  initAttempted = true;

  const VConsole = tryRequireVConsole();
  if (!VConsole) {
    return null;
  }

  try {
    vConsoleInstance = new VConsole({
      theme: isDevtoolsPlatform() ? "light" : "dark",
    });
  } catch (_) {
    vConsoleInstance = null;
  }

  return vConsoleInstance;
}

module.exports = {
  initDebugConsole,
};
