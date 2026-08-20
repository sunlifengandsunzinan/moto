const { API_PATHS, MINI_PROGRAM_PATHS } = require("../../../utils/backend-config");
const { request, buildWebUrl } = require("../../../utils/request");

function normalizeCollectionPayload(payload) {
  const safePayload = payload || {};
  const routes = Array.isArray(safePayload.routes) ? safePayload.routes : [];
  const badges = Array.isArray(safePayload.badges) ? safePayload.badges : [];
  const summary = safePayload.summary && typeof safePayload.summary === "object"
    ? safePayload.summary
    : {};
  const clubPublic = safePayload.club_public && typeof safePayload.club_public === "object"
    ? safePayload.club_public
    : {};
  const clubRouteBoard = safePayload.club_route_board && typeof safePayload.club_route_board === "object"
    ? safePayload.club_route_board
    : {};

  return {
    page: safePayload.page || { title: "我的收集册" },
    summary: {
      route_count: Number(summary.route_count || routes.length || 0),
      completed_route_count: Number(summary.completed_route_count || 0),
      badge_count: Number(summary.badge_count || badges.length || 0),
    },
    clubPublic: {
      title: String(clubPublic.title || "俱乐部公开内容"),
      activity_level: String(clubPublic.activity_level || "中"),
      route_styles: Array.isArray(clubPublic.route_styles)
        ? clubPublic.route_styles.map((item) => ({
            label: String(item?.label || "综合路线"),
            count: Number(item?.count || 0),
          }))
        : [],
      activity_posters: Array.isArray(clubPublic.activity_posters)
        ? clubPublic.activity_posters.map((item) => ({
            slug: String(item?.slug || "").trim(),
            title: String(item?.title || "未命名路线"),
            poster_url: item?.poster_href ? buildWebUrl(item.poster_href) : "",
            signup_count: Number(item?.signup_count || 0),
            is_signed_up: Boolean(item?.is_signed_up),
          }))
        : [],
    },
    clubRouteBoard: {
      weekly_checkpoint_total: Number(clubRouteBoard.weekly_checkpoint_total || 0),
      weekly_completed_routes: Number(clubRouteBoard.weekly_completed_routes || 0),
      routes: Array.isArray(clubRouteBoard.routes)
        ? clubRouteBoard.routes.map((item) => ({
            slug: String(item?.slug || "").trim(),
            title: String(item?.title || "未命名路线"),
            member_count: Number(item?.member_count || 0),
            completed_member_count: Number(item?.completed_member_count || 0),
            avg_completion_percent: Number(item?.avg_completion_percent || 0),
          }))
        : [],
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
      club_avg_completion_percent: Number(route.club_avg_completion_percent || 0),
      club_member_count: Number(route.club_member_count || 0),
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
    clubPublic: {
      title: "俱乐部公开内容",
      activity_level: "中",
      route_styles: [],
      activity_posters: [],
    },
    clubRouteBoard: {
      weekly_checkpoint_total: 0,
      weekly_completed_routes: 0,
      routes: [],
    },
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
          clubPublic: normalized.clubPublic,
          clubRouteBoard: normalized.clubRouteBoard,
          routes: normalized.routes,
          badges: normalized.badges,
        });
      })
      .catch((error) => {
        this.setData({
          loading: false,
          error: error?.message || "加载收集册失败",
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

  handleSignupClubActivity(event) {
    const slug = String(event?.currentTarget?.dataset?.slug || "").trim();
    const title = String(event?.currentTarget?.dataset?.title || "").trim();
    if (!slug) {
      return;
    }

    const posters = (this.data.clubPublic?.activity_posters || []);
    const currentPoster = posters.find((item) => item.slug === slug);
    if (currentPoster?.is_signed_up) {
      wx.showToast({ title: "你已报名该活动", icon: "none" });
      return;
    }

    request({
      path: API_PATHS.clubActivitySignup(slug),
      method: "POST",
      data: { title },
    })
      .then((payload) => {
        if (!payload?.ok) {
          wx.showToast({ title: String(payload?.error || "报名失败"), icon: "none" });
          return;
        }

        const nextPosters = posters.map((item) => {
          if (item.slug !== slug) {
            return item;
          }
          return {
            ...item,
            is_signed_up: true,
            signup_count: Number(payload?.signup_count || item.signup_count || 0),
          };
        });

        this.setData({
          clubPublic: {
            ...(this.data.clubPublic || {}),
            activity_posters: nextPosters,
          },
        });

        wx.showToast({ title: "报名成功", icon: "success" });
      })
      .catch((error) => {
        wx.showToast({ title: error?.message || "报名失败", icon: "none" });
      });
  },
});
