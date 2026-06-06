## 模板：小红书笔记 → 结构化输出（v3 含路线图片+坐标+里程）

收到一条原始数据后，按以下格式输出。**v3新增**：路线封面图、途经点实景图片。

### 分析流程

```
step 1: 从原始数据提取 image_list（首张图作为封面）
step 2: 从 title/desc/comments 提取路线途经点
step 3: 查坐标库获取途经点坐标
step 4: 用 Haversine 公式计算里程
step 5: 调用 Ollama 做 AI 深度点评
step 6: 输出完整结构化结果
```

### 结构化输出模板（v3 含图片）

```json
{
  "note_id": "68475d27000000002202790d",
  "platform": "小红书",
  "basic_info": {
    "title": "属于辽宁的独库公路，带你走走",
    "media_type": "video",
    "author": "儒予",
    "publish_time": "2025-06-10",
    "source_keyword": "辽宁摩旅路线",
    "cover_images": [
      "http://sns-webpic-qc.xhscdn.com/202606022251/xxx/xxx.jpg",
      "http://sns-webpic-qc.xhscdn.com/202606022251/xxx/xxx.jpg"
    ],
    "cover_image_count": 2,
    "video_url": "",
    "description": "属于辽宁的独库公路，带你走走"
  },

  "engagement": {
    "likes": 2871,
    "collects": 4920,
    "comments": 72,
    "shares": 2862
  },

  "topic_classification": {
    "category": "自驾路线",
    "subcategory": "辽宁短途自驾",
    "keywords_extracted": ["辽宁", "独库公路", "崔桂线", "盖州", "庄河"]
  },

  "route_analysis": {
    "has_route_info": true,
    "route_type": "跨区短途",

    "waypoint_names": ["沈阳", "盖州", "庄河", "崔桂线"],

    "waypoint_coords": {
      "沈阳": {"lng": 123.431, "lat": 41.808},
      "盖州": {"lng": 122.350, "lat": 40.410},
      "庄河": {"lng": 122.980, "lat": 39.690},
      "崔桂线": {"lng": 122.850, "lat": 39.720}
    },

    "route_order": ["沈阳", "盖州", "庄河", "崔桂线"],

    "distance_km": 345.2,
    "estimated_motorcycle_km": 449,
    "distance_calculation_method": "Haversine直线距离 + 30%路况系数",
    "segments": [
      "沈阳→盖州: 179.9km",
      "盖州→庄河: 96.4km",
      "庄河→崔桂线: 11.6km"
    ],

    "estimated_days": "1天",
    "suitable_for_motorcycle": true,

    "scenic_images": {
      "沈阳": "https://img.example.com/shenyang.jpg",
      "崔桂线": "https://img.example.com/cuiguixian.jpg"
    },

    "mentions": {
      "roads": ["崔桂线"],
      "cities_or_regions": ["沈阳", "盖州", "庄河", "大连"],
      "scenic_spots": ["挂壁公路"]
    },

    "source_comment_insights": [
      "崔桂线实际驾车视角不如航拍震撼，期望值管理很重要",
      "有网友确认能骑摩托车通行",
      "沈阳出发用户关心是否需走回头路"
    ]
  },

  "qualification_assessment": {
    "qualified": true,
    "confidence": "high",
    "is_liaoning_related": true,
    "notes": "确认为辽宁摩旅/自驾相关路线内容，具备路线参考价值。"
  },

  "ai_review": {
    "score": 7.0,
    "rating": "推荐",
    "comment": "辽宁独库公路非典型摩旅路线，更适合短途探索。",
    "riding_advice": "推荐125cc-600cc越野/街车；秋季骑行，耗时约4小时。"
  },

  "data_source": {
    "source_keyword": "辽宁摩旅路线",
    "crawl_time": "2026-06-02",
    "note_url": "https://www.xiaohongshu.com/explore/68475d27000000002202790d?..."
  }
}
```

### 图片字段说明

| 字段 | 说明 |
|---|---|
| `cover_images` | 笔记配图列表（从原始 `image_list` 字段解析，逗号分隔URL） |
| `cover_image_count` | 配图数量 |
| `scenic_images` | 途经点实景图片（可选，可从百度/高德图片搜索抓取） |
| `video_url` | 若为视频类型，视频URL |

如果 `image_list` 为空或视频类型，则 `cover_images` 留空数组。

### 坐标库（预置辽宁摩旅常用坐标 GCJ-02）

```python
known_coords = {
    "沈阳": (123.431, 41.808), "大连": (121.615, 38.914),
    "丹东": (124.356, 40.000), "本溪": (123.766, 41.330),
    "桓仁": (125.360, 41.270), "庄河": (122.980, 39.690),
    "盖州": (122.350, 40.410), "绿江村": (125.380, 40.720),
    "崔桂线": (122.850, 39.720), "本桓公路": (124.120, 41.300),
    "锦州": (121.130, 41.100), "盘锦": (121.970, 40.720),
    "鞍山": (122.980, 41.120), "抚顺": (123.930, 41.880),
    "营口": (122.230, 40.670), "葫芦岛": (120.830, 40.720),
    "大连滨海路": (121.620, 38.880), "丹东绿江村": (125.380, 40.720),
    "本溪水洞": (124.080, 41.320), "关门山": (124.020, 41.160),
    "天桥沟": (124.780, 40.980), "老秃顶子": (125.020, 41.320),
    "滨江公路": (124.350, 40.050), "辽河": (122.000, 41.200),
    "红海滩": (121.970, 40.720), "笔架山": (121.120, 40.850),
    "冰峪沟": (122.940, 39.870), "步云山": (122.540, 39.870),
    "青山沟": (124.780, 40.880), "凤凰山（丹东）": (124.110, 40.420),
    "宽甸": (124.780, 40.730), "鸭绿江": (124.300, 39.900),
}
```

### 里程计算

```python
import math
def haversine(lng1, lat1, lng2, lat2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

# 系数：高速1.2, 省道1.3, 山路1.5
estimated_motorcycle_km = round(total_km * 1.3)
```
