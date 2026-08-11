# 自动剪辑方案

## 目标

基于当前仓库已有的路线模板、点位库、抖音/小红书采集、视频分析和待审核数据流，补出一条可执行的自动剪辑链路，用于生成摩旅短视频的粗剪结果。

这条链路的目标不是一步到位做成专业成片，而是先稳定产出可复核的 `rough cut`：

- 自动筛出可用片段
- 自动生成时间线和分镜顺序
- 自动拼接字幕、转场占位和封面文案
- 输出可继续人工精修的剪映 / Premiere / DaVinci 中间产物

## 适配当前仓库的原因

当前仓库已经具备自动剪辑最难的上游基础：

- 社媒采集入口：`openclaw/liaoning_social_task.js`
- 本地社媒采集执行器：`scripts/run_local_social_collection.py`
- 路线模板与导航点：`app/services/route_templates.json`
- 视频分析结果接入点：候选数据里的 `transcript`、`summary`、`sceneSummary`
- 路线点位提取任务：`openclaw/douyin_route_waypoint_task.js`
- 待审核入库流：`scripts/run_candidate_pipeline.py`

也就是说，当前项目已经能拿到三类自动剪辑必需信息：

- 视频来自哪里
- 视频讲了什么
- 视频和哪条路线、哪个点位有关

缺的主要不是采集，而是“如何把素材变成时间线”。

## 核心思路

把自动剪辑拆成四层：

1. 素材层：采集视频、封面、字幕、OCR、评论摘要、路线点位。
2. 片段层：把完整视频切成多个候选镜头，给每段打标签和分数。
3. 时间线层：按成片模板把镜头拼成开场、行进、打卡、收尾。
4. 导出层：输出可直接预览的视频，或输出给剪映 / Premiere / DaVinci 的中间文件。

建议先做“脚本驱动的粗剪”，不要一开始就深度绑定某个 NLE。

## 推荐成片模板

先只做 3 种模板，避免策略分散。

### 模板 A：路线种草

适合 `routes` 数据。

- 时长：30 到 60 秒
- 结构：开场钩子 -> 路线概览 -> 3 到 5 个关键点位 -> 收尾 CTA
- 适合内容：本桓公路、绿江村、滨海路等整线内容

### 模板 B：单点打卡

适合 `spots` 数据。

- 时长：15 到 35 秒
- 结构：点位亮点 -> 到达视角 -> 停留体验 -> 补给/注意事项
- 适合内容：骑士驿站、观景台、补给站

### 模板 C：一天路书回顾

适合按路线日程输出。

- 时长：45 到 90 秒
- 结构：出发 -> 上午路段 -> 午间停靠 -> 下午路段 -> 日落/夜宿
- 适合内容：已有 `days_plan` 的路线模板

## 数据输入设计

建议新增一个中间素材清单，不直接从原始采集结果拼视频。

建议文件：`data/raw/video_edit_candidates.json`

建议单条结构：

```json
{
  "asset_id": "douyin_738001",
  "source_platform": "douyin",
  "source_url": "https://www.douyin.com/video/...",
  "local_video_path": "data/raw/videos/douyin_738001.mp4",
  "cover_url": "https://...jpg",
  "duration_seconds": 43.2,
  "transcript": "今天从本溪跑到绿江村...",
  "ocr_text": ["本桓公路", "绿江村"],
  "summary": "辽宁摩旅风景线视频，包含山路和江边镜头。",
  "scene_tags": ["骑行第一视角", "山路", "江景", "驿站"],
  "route_slugs": ["liaoning-benhuan-3-day"],
  "spot_slugs": ["benxi-benhuan-road-viewpoint"],
  "quality_score": 0.86,
  "risk_flags": ["duplicate-opening-shot"]
}
```

这个文件的作用是把“采集结果”和“剪辑结果”之间加一层稳定契约。

## 片段切分策略

### MVP 做法

先不要做复杂镜头检测，先做可控规则切分：

- 按字幕时间戳切段
- 没有字幕时按固定时长切段，比如 2.5 到 4 秒
- 遇到明显停顿、黑屏、转场字卡时强制切段

建议优先采用：

- `ffmpeg` + `silencedetect` 做静音点切分
- `ffprobe` 读取时长、码率、分辨率
- Whisper 或已有分析结果补字幕时间轴

### 升级做法

后续再加入：

- 画面重复检测
- 抖动检测
- 模糊帧过滤
- 人声高潮 / 地名出现时的关键句提取
- OCR 命中路线名、点位名时提高权重

## 片段打分模型

每个片段生成一个 `clip_score`，先用规则分，不必先上训练模型。

建议分数组成：

- 内容相关性 35%：字幕、OCR、summary 是否命中路线或点位关键词
- 画面可用性 20%：清晰度、分辨率、稳定性、无明显遮挡
- 信息密度 15%：是否出现地名、路牌、补给点、景观点
- 叙事位置 15%：是否适合作为开场、过渡、结尾
- 多样性 15%：避免连续多个同类镜头

建议先定义标签：

- `hook`
- `ride`
- `landscape`
- `arrival`
- `stopover`
- `food`
- `night`
- `cta`

## 时间线编排策略

以“路线种草”模板为例，推荐固定骨架：

1. 开场 3 秒：优先选 `hook`，配标题文案。
2. 路线概览 4 到 6 秒：用路线名、里程、天数、区域。
3. 中段 15 到 35 秒：按 `waypoints` 顺序挑 3 到 5 个高分片段。
4. 收尾 3 到 6 秒：补给建议、适合谁、收藏/导航 CTA。

路线顺序不要完全依赖视频原顺序，优先依赖：

- `app/services/route_templates.json` 中的 `days_plan`
- `navigation.waypoints`
- `openclaw_route_waypoints.json` 提取出的 waypoint 顺序

这能避免素材来源很杂时，成片叙事顺序混乱。

## 字幕与文案生成

建议把文案分成三层：

### 第一层：事实层

直接来自现有数据：

- 路线名
- 天数
- 推荐季节
- 补给点
- 里程范围

### 第二层：摘要层

来自现有 `summary`、`sceneSummary`、路线摘要。

用途：

- 片头标题
- 片段说明字幕
- 收尾一句话总结

### 第三层：平台风格层

按渠道生成不同口吻：

- 抖音版：短句、节奏快、钩子强
- 小红书版：信息更完整，强调体验和建议
- 视频号版：中性、实用、少口语

建议新增一个文案模板文件，而不是把文案逻辑写死在脚本里。

建议文件：`structured_output_template_video_edit.md`

## 音乐与节奏

MVP 不做自动选歌接入平台版权库，先做节奏占位：

- 输出静音粗剪版
- 或使用本地免版权 BGM 库按 BPM 标签选一首

节奏规则建议：

- 开场 0.8 到 1.5 秒快速切
- 行进镜头 2 到 3 秒
- 风景镜头 2.5 到 4 秒
- 收尾停留 2 到 3 秒

## 导出方案

优先级建议如下：

### 方案 1：直接 ffmpeg 出粗剪成片

优点：

- 最快落地
- 不依赖外部 GUI 软件
- 适合批量生成预览

输出：

- `data/exports/rough_cut_<route_slug>.mp4`
- `data/exports/rough_cut_<route_slug>.srt`
- `data/exports/rough_cut_<route_slug>.json`

### 方案 2：导出 EDL / FCPXML / CSV

优点：

- 方便导入 Premiere / DaVinci 二次精修
- 保留自动排序结果但不强迫最终视觉样式

建议优先做 CSV 或 JSON timecode 清单，后续再转 FCPXML。

## 与当前仓库的落地映射

建议新增以下文件：

- `scripts/build_video_edit_candidates.py`
  - 汇总社媒采集结果、视频分析结果、路线/点位关联，生成剪辑候选素材池
- `scripts/generate_auto_edit_plan.py`
  - 对素材切段、打分、按模板编排，输出时间线 JSON
- `scripts/render_rough_cut.py`
  - 调用 `ffmpeg` 生成粗剪视频或导出中间文件
- `data/raw/video_edit_candidates.json`
  - 剪辑候选素材池
- `data/exports/`
  - 粗剪输出目录

建议复用的现有数据源：

- `data/raw/openclaw_export.json`
- `data/raw/openclaw_route_waypoints.json`
- `data/normalized/candidate_spots.json`
- `app/services/route_templates.json`

## 最小可行版本

第一阶段只做以下能力：

1. 输入 1 条路线 slug。
2. 自动收集关联视频素材。
3. 从每条视频切出 3 到 8 个候选片段。
4. 选出总计 8 到 12 个片段组成 30 到 45 秒粗剪。
5. 自动加标题、路线简介字幕、结尾 CTA。
6. 输出一个 mp4 和一份时间线 JSON。

这一版不解决：

- 高级转场
- 智能卡点
- 自动调色
- 多音轨混音
- 平台级版权音乐接入

## 推荐实现顺序

### 第 1 步：素材池归一化

先把现有采集结果统一为 `video_edit_candidates.json`。

目标：解决“素材在哪里、对应哪条路线、有哪些文字线索”。

### 第 2 步：输出剪辑计划 JSON

先不渲染视频，只输出：

- 选择了哪些片段
- 每段起止时间
- 每段字幕文案
- 每段属于哪种镜头标签

目标：先验证编排逻辑是否合理。

### 第 3 步：ffmpeg 粗剪渲染

等时间线 JSON 质量稳定后，再生成成片。

### 第 4 步：人工复核入口

把粗剪结果挂到现有审核流或单独页面，支持：

- 片段删除
- 片段顺序微调
- 替换标题文案

## 成功判断标准

一条自动剪辑结果至少满足：

- 叙事顺序和路线顺序基本一致
- 无明显重复镜头
- 字幕与路线信息无硬错误
- 30 到 45 秒内能看出“从哪到哪、沿途看什么、适合谁”

## 风险与规避

- 平台原视频未必容易直接下载：先接受“仅导出剪辑计划，不自动落地原始视频文件”的运行模式。
- OCR / transcript 质量不稳定：优先用路线 waypoint 和已知 spot 词典兜底。
- 素材重复率高：增加开场镜头去重和感知哈希过滤。
- 文案容易空泛：优先复用现有 route/spot summary，不直接全量生成营销话术。

## 结论

对当前仓库，最合适的自动剪辑路线不是新建一套独立视频系统，而是在现有“社媒采集 -> 路线/点位结构化 -> 审核入库”旁边补一条“素材池 -> 片段打分 -> 时间线 JSON -> ffmpeg 粗剪”的轻量链路。

这样改动最小，能最快验证自动剪辑是否真的对摩旅内容有价值。