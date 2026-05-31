const FAVORITE_ROUTES_KEY = "favoriteRoutes";

function getFavoriteRoutes() {
  const storedValue = wx.getStorageSync(FAVORITE_ROUTES_KEY);
  if (!Array.isArray(storedValue)) {
    return [];
  }

  return storedValue.filter((item) => item && typeof item === "object" && String(item.slug || "").trim());
}

function saveFavoriteRoutes(routes) {
  wx.setStorageSync(FAVORITE_ROUTES_KEY, Array.isArray(routes) ? routes : []);
}

function normalizeFavoriteRoute(route) {
  return {
    slug: String(route.slug || "").trim(),
    title: String(route.title || "").trim(),
    days: Number(route.days || 0),
    distance_km: Number(route.distance_km || 0),
    waypoint_count: Number(route.waypoint_count || 0),
    href: String(route.href || "").trim(),
    summary: String(route.summary || "").trim(),
    gpx: route.gpx || { is_available: false },
    amap_export: route.amap_export || { is_available: false, href: "" },
    days_plan: Array.isArray(route.days_plan) ? route.days_plan.slice(0, 2) : [],
    favorite_saved_at: Date.now(),
  };
}

function isFavoriteRoute(slug) {
  return getFavoriteRoutes().some((route) => route.slug === slug);
}

function toggleFavoriteRoute(route) {
  const favorites = getFavoriteRoutes();
  const slug = String(route?.slug || "").trim();
  if (!slug) {
    return { favorites, isFavorite: false };
  }

  const existingIndex = favorites.findIndex((item) => item.slug === slug);
  if (existingIndex >= 0) {
    favorites.splice(existingIndex, 1);
    saveFavoriteRoutes(favorites);
    return { favorites, isFavorite: false };
  }

  favorites.unshift(normalizeFavoriteRoute(route));
  saveFavoriteRoutes(favorites);
  return { favorites, isFavorite: true };
}

function mergeRoutesWithFavorites(routes) {
  const favorites = getFavoriteRoutes();
  const favoritesBySlug = favorites.reduce((accumulator, route) => {
    accumulator[route.slug] = route;
    return accumulator;
  }, {});

  return (routes || []).map((route) => ({
    ...route,
    is_favorite: Boolean(favoritesBySlug[route.slug]),
  }));
}

module.exports = {
  getFavoriteRoutes,
  isFavoriteRoute,
  mergeRoutesWithFavorites,
  toggleFavoriteRoute,
};