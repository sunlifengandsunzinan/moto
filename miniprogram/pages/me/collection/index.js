const { API_PATHS, MINI_PROGRAM_PATHS } = require("../../../utils/backend-config");
const { request, buildWebUrl } = require("../../../utils/request");

function normalizeCollectionPayload(payload) {
  const safePayload = payload || {};
  const routes = Array.isArray(safePayload.routes) ? safePayload.routes : [];
  const badges = Array.isArray(safePayload.badges) ? safePayload.badges : [];
  const summary = safePayload.summary && typeof safePayload.summary === "object"
    ? safePayload.summary
    : {};

  return {
    page: safePayload.page || { title: "我的收集册" },
    summary: {
      route_count: Number(summary.route_count || routes.length || 0),
      completed_route_count: Number(summary.completed_route_count || 0),
      badge_count: Number(summary.badge_count || badges.length || 0),
    },
    routes: routes.map((route) => ({
      slug: String(route.slug || "").trim(),
      title: String(route.title || "未命名路线"),
      checked_count: Number(route.checked_count || 0),
      checkpoint_total: Number(route.checkpoint_total || 0),
      completion_percent: Number(route.completion_percent || 0),
      is_completed: Boolean(route.is_completed),
      updated_at: String(route.updated_at || ""),
      days: Number(route.days || 0),
      distance_km: Number(route.distance_km || 0),
      poster_url: route.poster_href ? buildWebUrl(route.poster_href) : "",
      share_text: String(route.share_text || "我正在挑战摩旅路线打卡").trim(),
    })),
    badges: badges.map((badge) => ({
      slug: String(badge.slug || "").trim(),
      title: String(badge.title || "路线征服者"),
      subtitle: String(badge.subtitle || "路线打卡已集齐"),
      awarded_at: String(badge.awarded_at || ""),
      poster_url: badge.poster_href ? buildWebUrl(badge.poster_href) : "",
      share_text: String(badge.share_text || "我解锁了新的路线徽章").trim(),
    })),
  };
}

Page({
  data: {
    loading: true,
    error: "",
    page: { title: "我的收集册" },
    summary: {
      route_count: 0,
      completed_route_count: 0,
      badge_count: 0,
    },
    routes: [],
    badges: [],
    selectedShareItem: null,
  },

  onLoad() {
    this.fetchCollection();
  },

  onShow() {
    this.fetchCollection();
  },

  onPullDownRefresh() {
    this.fetchCollection(true);
  },

  onShareAppMessage() {
    const selected = this.data.selectedShareItem;
    const shareTitle = selected?.share_text || "我在行途中解锁了新的摩旅路线徽章";
    const slug = String(selected?.slug || "").trim();
    const path = slug ? MINI_PROGRAM_PATHS.routeDetail(slug) : MINI_PROGRAM_PATHS.meCollection;
    const imageUrl = String(selected?.poster_url || "").trim();
    this.setData({ selectedShareItem: null });
    return {
      title: shareTitle,
      path,
      imageUrl,
    };
  },

  fetchCollection(stopRefresh = false) {
    this.setData({ loading: true, error: "" });

    request({ path: API_PATHS.meCollection })
      .then((payload) => {
        const normalized = normalizeCollectionPayload(payload);
        this.setData({
          loading: false,
          error: "",
          page: normalized.page,
          summary: normalized.summary,
          routes: normalized.routes,
          badges: normalized.badges,
        });
      })
      .catch((error) => {
        this.setData({
          loading: false,
          error: error?.message || "加载我的收集册失败",
          routes: [],
          badges: [],
        });
      })
      .finally(() => {
        if (stopRefresh) {
          wx.stopPullDownRefresh();
        }
      });
  },

  handleOpenRoute(event) {
    const slug = String(event?.currentTarget?.dataset?.slug || "").trim();
    if (!slug) {
      return;
    }
    wx.navigateTo({ url: MINI_PROGRAM_PATHS.routeDetail(slug) });
  },

  handleShareRoutePoster(event) {
    const slug = String(event?.currentTarget?.dataset?.slug || "").trim();
    if (!slug) {
      return;
    }
    const pickedRoute = (this.data.routes || []).find((route) => route.slug === slug);
    if (!pickedRoute) {
      return;
    }
    this.setData({ selectedShareItem: pickedRoute });
  },

  handleShareBadgePoster(event) {
    const slug = String(event?.currentTarget?.dataset?.slug || "").trim();
    if (!slug) {
      return;
    }
    const pickedBadge = (this.data.badges || []).find((badge) => badge.slug === slug);
    if (!pickedBadge) {
      return;
    }
    this.setData({ selectedShareItem: pickedBadge });
  },

});
