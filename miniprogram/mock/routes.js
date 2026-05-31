const routesPageFallback = {
  routes: [
    {
      slug: "liaodong-coast-2-day",
      title: "辽东海岸 2 天轻骑",
      summary: "大连出发，沿海岸线补给和观景点较密，适合周末快速成行。",
      distance_km: 286,
      days: 2,
      waypoint_count: 4,
      href: "/moto/routes/hainan-5-day",
      amap_export: {
        is_available: true,
        href: "https://m.amap.com/navigation/carmap/jm=1&sort=tfc&saddr=%E5%A4%A7%E8%BF%9E&daddr=%E6%97%85%E9%A1%BA&maddr=%E6%BB%A8%E6%B5%B7%E8%B7%AF|%E9%87%91%E7%9F%B3%E6%BB%A9&src=mypage&callnative=0&innersrc=uriapi",
        status_variant: "names",
        status_badge: "名称导航",
        status_text: "0/4 个点带坐标，将按地点名称导航",
      },
    },
    {
      slug: "benxi-huanren-3-day",
      title: "本溪桓仁 3 天山路线",
      summary: "重点覆盖本桓公路和桓仁一带山路，弯道密集，适合连续骑行。",
      distance_km: 468,
      days: 3,
      waypoint_count: 5,
      href: "/moto/routes/wannan-3-day",
      amap_export: {
        is_available: true,
        href: "https://m.amap.com/navigation/carmap/jm=1&sort=tfc&saddr=%E6%B2%88%E9%98%B3&daddr=%E6%A1%93%E4%BB%81&maddr=%E6%9C%AC%E6%BA%AA|%E6%9C%AC%E6%A1%93%E5%85%AC%E8%B7%AF|%E8%80%81%E8%BE%B9%E6%B2%9F&src=mypage&callnative=0&innersrc=uriapi",
        status_variant: "names",
        status_badge: "名称导航",
        status_text: "0/5 个点带坐标，将按地点名称导航",
      },
    },
    {
      slug: "dandong-river-2-day",
      title: "丹东鸭绿江 2 天沿江线",
      summary: "沿丹东到绿江村的经典沿江段骑行，补给清晰，适合拍摄打卡。",
      distance_km: 318,
      days: 2,
      waypoint_count: 4,
      href: "/moto/routes/jiangzhehu-2-day",
      amap_export: {
        is_available: true,
        href: "https://m.amap.com/navigation/carmap/jm=1&sort=tfc&saddr=%E4%B8%B9%E4%B8%9C&daddr=%E7%BB%BF%E6%B1%9F%E6%9D%91&maddr=%E8%99%8E%E5%B1%B1%E9%95%BF%E5%9F%8E|%E5%AE%BD%E7%94%B8&src=mypage&callnative=0&innersrc=uriapi",
        status_variant: "names",
        status_badge: "名称导航",
        status_text: "0/4 个点带坐标，将按地点名称导航",
      },
    },
  ],
};

module.exports = {
  routesPageFallback,
};