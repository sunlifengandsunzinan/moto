const { getFavoriteRoutes } = require("../../utils/favorites");

Page({
  data: {
    loading: true,
    page: { title: "我的收藏" },
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
    this.setData({
      loading: false,
      favoriteRoutes: getFavoriteRoutes(),
    });

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
      url: `/pages/routes/detail/index?slug=${encodeURIComponent(slug)}`,
    });
  },
});