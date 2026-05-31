const routeDetailFallbackBySlug = {
  "jiangzhehu-2-day": {
    page: {
      title: "江浙沪 2 天轻松短途",
      eyebrow: "路线详情",
    },
    route: {
      title: "江浙沪 2 天轻松短途",
      days: 2,
      amap_export: {
        screenshot_href: "",
      },
    },
    detail_sections: {
      daily_plan: [
        {
          day: 1,
          title: "杭州 -> 莫干山 -> 安吉",
          ride_time: "约 4 小时",
          distance: "约 170 km",
          highlights: ["山路热身", "午后咖啡停靠"],
          note: "第一天以适应节奏为主，重点看山路和停靠点之间的衔接。",
        },
        {
          day: 2,
          title: "安吉 -> 临安 -> 杭州",
          ride_time: "约 4.5 小时",
          distance: "约 190 km",
          highlights: ["林道穿行", "返程补给"],
          note: "第二天按返程节奏压缩停靠时间，保持连续骑行的完整度。",
        },
      ],
    },
  },
};

function getRouteDetailFallback(slug) {
  return routeDetailFallbackBySlug[slug] || {
    page: {
      title: "路线详情",
      eyebrow: "路线详情",
    },
    route: {
      title: "示例路线",
      days: 2,
      amap_export: {
        screenshot_href: "",
      },
    },
    detail_sections: {
      daily_plan: [
        {
          day: 1,
          title: "起点 -> 途径点 A -> 终点",
          ride_time: "约 4 小时",
          distance: "约 160 km",
          highlights: ["山路", "补给点"],
          note: "接口不可用时展示本地示例日程。",
        },
      ],
    },
  };
}

module.exports = {
  getRouteDetailFallback,
};