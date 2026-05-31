const routesPageFallback = {
  routes: [
    {
      slug: "jiangzhehu-2-day",
      title: "江浙沪 2 天轻松短途",
      summary: "当前仅保留 1 条测试路线，便于直接进入原生路线详情页验证截图和示例日程。",
      distance_km: 360,
      days: 2,
      waypoint_count: 3,
      href: "/moto/routes/jiangzhehu-2-day",
      amap_export: {
        is_available: true,
        href: "https://m.amap.com/navigation/carmap/jm=1&sort=tfc&saddr=%E6%9D%AD%E5%B7%9E&daddr=%E5%AE%89%E5%90%89&maddr=%E8%8E%AB%E5%B9%B2%E5%B1%B1&src=mypage&callnative=0&innersrc=uriapi",
        status_variant: "names",
        status_badge: "名称导航",
        status_text: "0/3 个点带坐标，将按地点名称导航",
      },
    },
  ],
};

module.exports = {
  routesPageFallback,
};