const routeDetailFallbackBySlug = {};

function getRouteDetailFallback(slug) {
  return routeDetailFallbackBySlug[slug] || {
    page: {
      title: "路线详情暂不可用",
      eyebrow: "路线详情",
    },
    route: {
      title: "暂无可展示路线",
      days: 0,
      amap_export: {
        screenshot_href: "",
      },
    },
    detail_sections: {
      daily_plan: [],
    },
  };
}

module.exports = {
  getRouteDetailFallback,
};