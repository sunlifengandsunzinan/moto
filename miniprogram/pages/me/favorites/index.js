const { MINI_PROGRAM_PATHS } = require("../../../utils/backend-config");
const { getFavoriteRoutes } = require("../../../utils/favorites");

Page({
  data: {
    favoriteRoutes: [],
  },

  onLoad() {
    this.syncFavoriteRoutes();
  },

  onShow() {
    this.syncFavoriteRoutes();
  },

  onPullDownRefresh() {
    this.syncFavoriteRoutes(true);
  },

  syncFavoriteRoutes(stopRefresh = false) {
    this.setData({ favoriteRoutes: getFavoriteRoutes() });

    if (stopRefresh) {
      wx.stopPullDownRefresh();
    }
  },

  handleOpenFavorite(event) {
    const slug = event.currentTarget.dataset.slug;
    if (!slug) {
      return;
    }

    wx.navigateTo({
      url: MINI_PROGRAM_PATHS.routeDetail(slug),
    });
  },
});