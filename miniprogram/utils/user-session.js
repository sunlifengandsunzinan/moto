const USER_ID_KEY = "motoUserId";

function generateUserId() {
  const timestamp = Date.now().toString(36);
  const random = Math.random().toString(36).slice(2, 10);
  return `mp-${timestamp}-${random}`;
}

function getStoredUserId() {
  try {
    const value = wx.getStorageSync(USER_ID_KEY);
    if (!value) {
      return "";
    }

    return String(value).trim();
  } catch (_) {
    return "";
  }
}

function setStoredUserId(userId) {
  try {
    wx.setStorageSync(USER_ID_KEY, userId);
  } catch (_) {
    // Ignore write failure; caller can still use the in-memory value.
  }
}

function getOrCreateUserId() {
  const stored = getStoredUserId();
  if (stored) {
    return stored;
  }

  const generated = generateUserId();
  setStoredUserId(generated);
  return generated;
}

module.exports = {
  getOrCreateUserId,
};
