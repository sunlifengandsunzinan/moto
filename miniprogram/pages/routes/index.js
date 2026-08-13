const { request, buildWebUrl } = require("../../utils/request");
const {
  API_PATHS,
  MINI_PROGRAM_PATHS,
  WEB_PATHS,
  getMiniProgramApiPath,
  getMiniProgramNavigationUrl,
  normalizeRequestPath,
} = require("../../utils/backend-config");

const EMPTY_ROUTES_STATE = {
  page: {
    title: "热门摩旅路线",
    description: "当前路线数据需要从后端加载。",
  },
  featured_summary: {
    title: "路线列表",
    description: "当前没有可展示的路线数据。",
  },
  empty_state: {
    title: "暂无路线",
    description: "请检查后端接口或在后台管理中补充路线数据。",
    action: { label: "去后台管理", href: "/moto/admin" },
  },
  routes: [],
};

const WANT_GO_PLAN_OPTIONS = [
  { key: "this_month", label: "这个月" },
  { key: "next_month", label: "下个月" },
  { key: "later", label: "再说" },
];

const SHARE_MENUS = ["shareAppMessage", "shareTimeline"];

function hasLoggedWechatProfile(profile) {
  if (!profile || typeof profile !== "object") {
    return false;
  }

  const nickName = String(profile.nickName || "").trim();
  const avatarUrl = String(profile.avatarUrl || "").trim();
  return Boolean(nickName || avatarUrl);
}

function normalizeWantGoPlanLabel(planBucket) {
  const normalized = String(planBucket || "").trim();
  const matched = WANT_GO_PLAN_OPTIONS.find((item) => item.key === normalized);
  return matched ? matched.label : "想去";
}

function compareRouteHeat(left, right) {
  const leftEngagement = left?.engagement || {};
  const rightEngagement = right?.engagement || {};
  const leftWantGo = Number(leftEngagement.want_go_count || 0);
  const rightWantGo = Number(rightEngagement.want_go_count || 0);
  if (leftWantGo !== rightWantGo) {
    return rightWantGo - leftWantGo;
  }

  const leftTotal = Number(leftEngagement.total_count || 0);
  const rightTotal = Number(rightEngagement.total_count || 0);
  if (leftTotal !== rightTotal) {
    return rightTotal - leftTotal;
  }

  const leftNavigation = Number(leftEngagement.navigation_count || 0);
  const rightNavigation = Number(rightEngagement.navigation_count || 0);
  if (leftNavigation !== rightNavigation) {
    return rightNavigation - leftNavigation;
  }

  const leftFavorite = Number(leftEngagement.favorite_count || 0);
  const rightFavorite = Number(rightEngagement.favorite_count || 0);
  if (leftFavorite !== rightFavorite) {
    return rightFavorite - leftFavorite;
  }

  return String(left?.title || "").localeCompare(String(right?.title || ""), "zh-Hans-CN");
}

function sortRoutesByHeat(routes) {
  return (Array.isArray(routes) ? routes.slice() : []).sort(compareRouteHeat);
}

function sortRoutes(routes, sortMode) {
  if (sortMode === "distance") {
    return (Array.isArray(routes) ? routes.slice() : []).sort((left, right) => {
      const leftDistance = Number(left?.distance_km || 0);
      const rightDistance = Number(right?.distance_km || 0);
      if (leftDistance !== rightDistance) {
        return rightDistance - leftDistance;
      }
      return compareRouteHeat(left, right);
    });
  }

  return sortRoutesByHeat(routes);
}

function buildDurationFilters(filters, selectedDays) {
  const quickFilters = filters && Array.isArray(filters.day_quick_filters) ? filters.day_quick_filters : [];
  if (!quickFilters.length) {
    return [{ key: "", label: "全部", value: "", is_active: true }];
  }

  return quickFilters.map((item) => ({
    key: String(item.value || "all"),
    label: item.label || "全部",
    value: item.value || "",
    is_active: String(item.value || "") === String(selectedDays || ""),
  }));
}

function normalizeCoordinatePoint(point) {
  const lng = Number(point?.lng);
  const lat = Number(point?.lat);
  if (!point?.has_coordinates || !Number.isFinite(lng) || !Number.isFinite(lat)) {
    return null;
  }

  return {
    name: String(point.name || "途径点"),
    longitude: lng,
    latitude: lat,
  };
}

function getRouteNavigationTarget(route) {
  const coordinatePoints = (route?.amap_export?.waypoints || [])
    .map(normalizeCoordinatePoint)
    .filter(Boolean);
  if (!coordinatePoints.length) {
    return null;
  }

  return coordinatePoints[coordinatePoints.length - 1];
}

function buildEstimatedDurationLabel(route) {
  const distance = Number(route?.distance_km || 0);
  if (!Number.isFinite(distance) || distance <= 0) {
    return "--";
  }

  const estimatedHours = Math.max(1, Math.round(distance / 55));
  return `${estimatedHours}H`;
}

function buildRouteCoverImage(route) {
  const explicitCoverImage = String(route?.cover_image_url || "").trim();
  if (explicitCoverImage) {
    return buildWebUrl(explicitCoverImage);
  }

  const screenshotHref = String(route?.amap_export?.screenshot_href || "").trim();
  if (screenshotHref) {
    return buildWebUrl(screenshotHref);
  }

  return "";
}

function normalizeRoute(route) {
  const safeRoute = route || {};
  const normalizedRoute = {
    mini_program_action: safeRoute.mini_program_action || null,
    mini_program: {
      replan: null,
      collect: null,
      favorite: null,
      want_go: null,
      ...((safeRoute && safeRoute.mini_program) || {}),
    },
    engagement: {
      favorite_count: 0,
      navigation_count: 0,
      total_count: 0,
      want_go_count: 0,
      ...((safeRoute && safeRoute.engagement) || {}),
    },
    want_go: {
      plan_bucket: "",
      total_count: 0,
      this_month_count: 0,
      next_month_count: 0,
      later_count: 0,
      ...((safeRoute && safeRoute.want_go) || {}),
    },
    gpx: {
      is_available: false,
      filename: "",
      download_href: "",
      source_badge: "",
      source_title: "",
      meta_text: "",
      mini_program: {
        download: null,
      },
      ...((safeRoute && safeRoute.gpx) || {}),
    },
    amap_export: {
      is_available: false,
      href: "",
      browser_href: "",
      launch_href: "",
      mini_program: {
        navigate: null,
        browser: null,
        interactive_map: null,
      },
      ...((safeRoute && safeRoute.amap_export) || {}),
    },
    source_meta: {
      label: "",
      author: "",
      detail: "",
      ...((safeRoute && safeRoute.source_meta) || {}),
    },
    favorite_api_href: String(safeRoute.favorite_api_href || ""),
    navigation_api_href: String(safeRoute.navigation_api_href || ""),
    days_plan: Array.isArray(safeRoute.days_plan) ? safeRoute.days_plan : [],
    ...safeRoute,
  };

  return {
    ...normalizedRoute,
    cover_image_url: buildRouteCoverImage(normalizedRoute),
    estimated_duration_label: buildEstimatedDurationLabel(normalizedRoute),
    reward_points_label: `${Number(normalizedRoute?.engagement?.favorite_count || 0)}分`,
    want_go_action_label: normalizeWantGoPlanLabel(normalizedRoute?.want_go?.plan_bucket),
  };
}

function normalizePayload(payload) {
  const safePayload = payload || EMPTY_ROUTES_STATE;
  const selectedDays = safePayload.filters && safePayload.filters.selected_days ? safePayload.filters.selected_days : "";
  const routes = sortRoutesByHeat(
    (Array.isArray(safePayload.routes) ? safePayload.routes : []).map(normalizeRoute),
  );

  return {
    page: safePayload.page || EMPTY_ROUTES_STATE.page,
    featuredSummary: safePayload.featured_summary || EMPTY_ROUTES_STATE.featured_summary,
    emptyState: safePayload.empty_state || EMPTY_ROUTES_STATE.empty_state,
    allRoutes: routes,
    routes,
    selectedDuration: selectedDays,
    durationFilters: buildDurationFilters(safePayload.filters, selectedDays),
  };
}

function buildRouteSharePayload(route) {
  const title = String(route?.title || "摩旅路线").trim() || "摩旅路线";
  const slug = String(route?.slug || "").trim();
  const days = Number(route?.days || 0);
  const distance = Number(route?.distance_km || 0);
  const suffix = days > 0 ? ` · ${days}天` : distance > 0 ? ` · ${distance}km` : "";

  return {
    title: `${title}${suffix}`,
    path: slug ? MINI_PROGRAM_PATHS.routeDetail(slug) : MINI_PROGRAM_PATHS.routesTab,
  };
}

function buildRoutesListSharePayload(routes, keyword) {
  const visibleCount = Array.isArray(routes) ? routes.length : 0;
  const normalizedKeyword = String(keyword || "").trim();
  const title = normalizedKeyword
    ? `摩旅路线 · ${normalizedKeyword} · ${visibleCount}条`
    : `热门摩旅路线 · ${visibleCount}条`;

  return {
    title,
    path: MINI_PROGRAM_PATHS.routesTab,
    query: normalizedKeyword ? `keyword=${encodeURIComponent(normalizedKeyword)}` : "",
  };
}

function applyRouteFilters(allRoutes, selectedDuration, keyword, sortMode) {
  const normalizedKeyword = String(keyword || "").trim().toLowerCase();
  const filtered = (Array.isArray(allRoutes) ? allRoutes : []).filter((route) => {
    if (selectedDuration && String(route.days || "") !== String(selectedDuration)) {
      return false;
    }

    if (!normalizedKeyword) {
      return true;
    }

    const title = String(route.title || "").toLowerCase();
    const summary = String(route.summary || "").toLowerCase();
    const sourceLabel = String(route?.source_meta?.label || "").toLowerCase();
    return title.includes(normalizedKeyword) || summary.includes(normalizedKeyword) || sourceLabel.includes(normalizedKeyword);
  });

  return sortRoutes(filtered, sortMode);
}

Page({
  data: {
    loading: true,
    error: "",
    page: { title: "热门摩旅路线", description: "" },
    featuredSummary: { title: "", description: "" },
    emptyState: {
      title: "暂无路线",
      description: "当前还没有匹配路线。",
      action: { label: "去采集导航点", href: WEB_PATHS.routesCollect },
    },
    allRoutes: [],
    routes: [],
    selectedDuration: "",
    keyword: "",
    sortMode: "heat",
    sortLabel: "热度",
    durationFilters: [{ key: "", label: "全部", value: "", is_active: true }],
  },

  onLoad() {
    this.enableNativeSharing();
    this.fetchData();
  },

  onShow() {
    this.enableNativeSharing();
    this.fetchData({});
  },

  enableNativeSharing() {
    if (typeof wx.showShareMenu !== "function") {
      return;
    }

    try {
      wx.showShareMenu({ menus: SHARE_MENUS });
    } catch (_) {
      // Ignore capability mismatches across client versions.
    }
  },

  onShareAppMessage(res) {
    const slug = String(res?.target?.dataset?.slug || "").trim();
    if (slug) {
      const route = this.findRoute(slug);
      const sharePayload = buildRouteSharePayload(route || { slug });
      return {
        title: sharePayload.title,
        path: sharePayload.path,
      };
    }

    const sharePayload = buildRoutesListSharePayload(this.data.routes, this.data.keyword);
    return {
      title: sharePayload.title,
      path: sharePayload.path,
    };
  },

  onShareTimeline() {
    const sharePayload = buildRoutesListSharePayload(this.data.routes, this.data.keyword);
    return {
      title: sharePayload.title,
      query: sharePayload.query,
    };
  },

  applyDurationFilter(selectedDuration, routes) {
    const sourceRoutes = routes !== undefined ? routes : this.data.allRoutes;
    this.setData({
      selectedDuration,
      routes: applyRouteFilters(sourceRoutes, selectedDuration, this.data.keyword, this.data.sortMode),
    });
  },

  onPullDownRefresh() {
    this.fetchData({}, true);
  },

  buildQuery(overrides = {}) {
    return {
      days: overrides.days !== undefined ? overrides.days : this.data.selectedDuration,
    };
  },

  fetchData(query = {}, stopRefresh = false) {
    this.setData({ loading: true, error: "" });

    const requestData = {
      ...query,
      _t: Date.now(),
    };

    request({ path: API_PATHS.routes, data: requestData })
      .then((payload) => {
        const normalized = normalizePayload(payload);
        this.setData({
          loading: false,
          error: "",
          ...normalized,
          routes: applyRouteFilters(normalized.allRoutes, normalized.selectedDuration, this.data.keyword, this.data.sortMode),
        });
      })
      .catch((error) => {
        this.setData({
          loading: false,
          error: error?.message || "加载路线失败，已切换本地空状态。",
          ...normalizePayload(EMPTY_ROUTES_STATE),
        });
      })
      .finally(() => {
        if (stopRefresh) {
          wx.stopPullDownRefresh();
        }
      });
  },

  handleDurationFilter(event) {
    const days = event.currentTarget.dataset.filterValue || "";
    this.fetchData(this.buildQuery({ days }));
  },

  handleSearchInput(event) {
    const keyword = String(event.detail.value || "");
    this.setData({
      keyword,
      routes: applyRouteFilters(this.data.allRoutes, this.data.selectedDuration, keyword, this.data.sortMode),
    });
  },

  handleSearchClear() {
    this.setData({
      keyword: "",
      routes: applyRouteFilters(this.data.allRoutes, this.data.selectedDuration, "", this.data.sortMode),
    });
  },

  handleToggleSort() {
    const nextSortMode = this.data.sortMode === "heat" ? "distance" : "heat";
    this.setData({
      sortMode: nextSortMode,
      sortLabel: nextSortMode === "heat" ? "热度" : "里程",
      routes: applyRouteFilters(this.data.allRoutes, this.data.selectedDuration, this.data.keyword, nextSortMode),
    });
  },

  ensureLoggedInForRouteAction() {
    const app = getApp();
    const profile = typeof app?.getWechatUserProfile === "function"
      ? app.getWechatUserProfile()
      : null;

    if (hasLoggedWechatProfile(profile)) {
      return true;
    }

    wx.showToast({ title: "请先去我的页面登录", icon: "none", duration: 1800 });
    return false;
  },

  updateRouteEngagement(slug, engagement) {
    const allRoutes = (this.data.allRoutes || []).map((route) => (
      route.slug === slug
        ? {
            ...route,
            engagement: {
              ...(route.engagement || {}),
              ...(engagement || {}),
            },
          }
        : route
    ));

    this.setData({
      allRoutes,
      routes: applyRouteFilters(allRoutes, this.data.selectedDuration, this.data.keyword, this.data.sortMode),
    });
  },

  findRoute(slug) {
    return (this.data.allRoutes || []).find((route) => route.slug === slug) || null;
  },

  navigateByAction(action, fallbackHref = "") {
    const targetUrl = getMiniProgramNavigationUrl(action);
    if (targetUrl) {
      if (action && action.type === "tab") {
        wx.switchTab({ url: targetUrl });
        return;
      }

      wx.navigateTo({ url: targetUrl });
      return;
    }

    if (fallbackHref) {
      this.openInWebView(fallbackHref);
    }
  },

  openInWebView(rawHref) {
    if (!rawHref) {
      return;
    }

    const href = /^https?:\/\//.test(rawHref) ? rawHref : buildWebUrl(rawHref);
    wx.navigateTo({
      url: MINI_PROGRAM_PATHS.webviewWithUrl(href),
    });
  },

  handleOpenRoute(event) {
    const slug = event.currentTarget.dataset.slug;
    const route = this.findRoute(slug);
    if (route && route.mini_program_action) {
      this.navigateByAction(route.mini_program_action, route.href);
      return;
    }

    if (slug) {
      wx.navigateTo({ url: MINI_PROGRAM_PATHS.routeDetail(slug) });
      return;
    }

    this.openInWebView(event.currentTarget.dataset.href);
  },

  handleDirectNavigate(event) {
    const route = this.findRoute(event.currentTarget.dataset.slug);
    const target = getRouteNavigationTarget(route);
    if (!target) {
      wx.showToast({ title: "当前路线缺少可导航坐标", icon: "none" });
      return;
    }

    wx.openLocation({
      latitude: target.latitude,
      longitude: target.longitude,
      name: target.name,
      address: target.name,
      scale: 12,
      success: () => {
        const navigationPath = getMiniProgramApiPath(route?.mini_program?.navigation)
          || normalizeRequestPath(route?.navigation_api_href || "");
        if (!navigationPath) {
          return;
        }

        request({ path: navigationPath, method: "POST" })
          .then((payload) => {
            if (payload && payload.ok && payload.engagement) {
              this.updateRouteEngagement(route.slug, payload.engagement);
            }
          })
          .catch(() => {});
      },
      fail: () => {
        wx.showToast({ title: "无法打开系统地图", icon: "none", duration: 2200 });
      },
    });
  },

  handleToggleFavorite(event) {
    const slug = event.currentTarget.dataset.slug;
    const route = (this.data.allRoutes || []).find((item) => item.slug === slug);
    if (!route) {
      return;
    }

    const nextFavoriteState = !route.is_favorite;
    const allRoutes = (this.data.allRoutes || []).map((item) => (
      item.slug === slug ? { ...item, is_favorite: nextFavoriteState } : item
    ));

    this.setData({
      allRoutes,
      routes: applyRouteFilters(allRoutes, this.data.selectedDuration, this.data.keyword, this.data.sortMode),
    });

    const favoritePath = getMiniProgramApiPath(route?.mini_program?.favorite)
      || normalizeRequestPath(route?.favorite_api_href || "");

    if (!favoritePath) {
      wx.showToast({ title: "收藏功能暂不可用", icon: "none" });
      return;
    }

    request({ path: favoritePath, method: nextFavoriteState ? "POST" : "DELETE" })
      .then((payload) => {
        const confirmedState = typeof payload?.is_favorite === "boolean"
          ? payload.is_favorite
          : nextFavoriteState;

        const syncedRoutes = (this.data.allRoutes || []).map((item) => (
          item.slug === slug ? { ...item, is_favorite: confirmedState } : item
        ));
        this.setData({
          allRoutes: syncedRoutes,
          routes: applyRouteFilters(syncedRoutes, this.data.selectedDuration, this.data.keyword, this.data.sortMode),
        });

        if (payload && payload.ok && payload.engagement) {
          this.updateRouteEngagement(slug, payload.engagement);
        }

        wx.showToast({
          title: confirmedState ? "已加入收藏" : "已取消收藏",
          icon: "none",
          duration: 1600,
        });
      })
      .catch(() => {
        const revertedRoutes = (this.data.allRoutes || []).map((item) => (
          item.slug === slug ? { ...item, is_favorite: route.is_favorite } : item
        ));
        this.setData({
          allRoutes: revertedRoutes,
          routes: applyRouteFilters(revertedRoutes, this.data.selectedDuration, this.data.keyword, this.data.sortMode),
        });

        wx.showToast({
          title: "收藏失败，请重试",
          icon: "none",
          duration: 1800,
        });
      });
  },

  handleSetWantGo(event) {
    if (!this.ensureLoggedInForRouteAction()) {
      return;
    }

    const slug = String(event.currentTarget.dataset.slug || "").trim();
    const route = this.findRoute(slug);
    if (!route) {
      return;
    }

    const itemList = [...WANT_GO_PLAN_OPTIONS.map((item) => item.label), "取消想去"];
    wx.showActionSheet({
      itemList,
      success: (result) => {
        const index = Number(result.tapIndex);
        if (!Number.isFinite(index) || index < 0 || index >= itemList.length) {
          return;
        }

        const pickedOption = WANT_GO_PLAN_OPTIONS[index] || null;
        const isClear = !pickedOption;
        const requestConfig = isClear
          ? { path: API_PATHS.routeWantGo(slug), method: "DELETE" }
          : {
              path: API_PATHS.routeWantGo(slug),
              method: "POST",
              data: { plan_bucket: pickedOption.key },
            };

        request(requestConfig)
          .then((payload) => {
            const allRoutes = (this.data.allRoutes || []).map((item) => {
              if (item.slug !== slug) {
                return item;
              }
              const nextRoute = {
                ...item,
                engagement: {
                  ...(item.engagement || {}),
                  ...(payload?.engagement || {}),
                },
                want_go: {
                  ...(item.want_go || {}),
                  ...(payload?.want_go || {}),
                },
              };
              nextRoute.want_go_action_label = normalizeWantGoPlanLabel(nextRoute?.want_go?.plan_bucket);
              return nextRoute;
            });

            this.setData({
              allRoutes,
              routes: applyRouteFilters(allRoutes, this.data.selectedDuration, this.data.keyword, this.data.sortMode),
            });

            wx.showToast({
              title: isClear ? "已取消想去" : `已标记${pickedOption.label}`,
              icon: "none",
              duration: 1700,
            });
          })
          .catch(() => {
            wx.showToast({ title: "设置失败，请重试", icon: "none", duration: 1800 });
          });
      },
    });
  },

  handleOpenCollect(event) {
    this.openInWebView(event.currentTarget.dataset.href);
  },

  handleOpenReplan(event) {
    this.openInWebView(event.currentTarget.dataset.href);
  },

  handleOpenPlanner() {
    this.openInWebView(WEB_PATHS.planner());
  },

  handleEmptyAction(event) {
    const href = event.currentTarget.dataset.href;
    if (href) {
      this.openInWebView(href);
    }
  },

  noop() {},
});
