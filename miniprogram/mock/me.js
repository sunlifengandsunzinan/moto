const mePageFallback = {
  page: {
    title: "我的摩旅",
  },
  profile: {
    name: "摩旅计划",
    tagline: "路线规划 · 直接导航 · 行程定制",
    summary: "当前环境无法直接连接本地 Flask 接口时，会自动切换到本地演示数据，方便继续预览页面。",
  },
  metrics: [
    { label: "路线模板", value: 3 },
    { label: "时长分档", value: 4 },
    { label: "直接导航", value: 3 },
  ],
  quick_actions: [
    { href: "/moto/routes", kind: "primary", label: "路线库" },
    { href: "/moto/custom", kind: "secondary", label: "定制需求" },
    { href: "/moto/routes/collect", kind: "secondary", label: "采集导航点" },
  ],
  sections: [
    {
      title: "常用功能",
      items: [
        { href: "/moto/routes", label: "查看路线库", description: "按骑行时长切换路线，并直接打开导航。" },
        { href: "/moto/planner", label: "开始路线规划", description: "从模板路线出发，继续延展成完整行程。" },
        { href: "/moto/routes/collect", label: "采集导航点", description: "把视频、地图或游记里的途径点整理成结构化路线数据。" },
      ],
    },
  ],
};

module.exports = {
  mePageFallback,
};