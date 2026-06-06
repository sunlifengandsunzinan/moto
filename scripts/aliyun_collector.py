#!/usr/bin/env python3
"""阿里云抖音视频采集脚本 - 纯Python，零浏览器依赖，每6小时执行一次"""
import json, re, sys, time, os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, quote_plus, urljoin
from urllib.request import Request, urlopen

PROJECT_ROOT = Path("/root/moto")
OUTPUT_DIR = PROJECT_ROOT / "data" / "raw"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

# ===== 路线关键词映射 =====
ROUTE_KEYWORDS = [
    # 辽宁4条路线 + 通用关键词
    {"slug": "liaoning-bengxi-greenriver", "title": "辽宁 3 天本溪到绿江边境风景线", "keywords": ["本溪 绿江村 摩旅", "本桓公路 骑行", "青山沟 宽甸 摩旅"]},
    {"slug": "liaoning-dalian-coastal", "title": "辽宁 2 天大连滨海轻骑线", "keywords": ["大连滨海路 骑行", "大连 金石滩 摩旅", "大连 旅顺 沿海 骑行"]},
    {"slug": "liaoning-border-scenic", "title": "辽宁 2 天辽东边境风景线", "keywords": ["青山沟 绿江村 摩旅", "宽甸 丹东 骑行", "辽东边境 摩旅"]},
    {"slug": "liaoning-red-beach", "title": "辽宁 2 天红海滩海滨轻松线", "keywords": ["盘锦红海滩 摩旅", "兴城 葫芦岛 骑行", "红海滩 摩旅 路线"]},
    {"slug": "liaoning-general", "title": "辽宁摩旅通用", "keywords": ["辽宁摩旅", "沈阳周边骑行", "辽宁机车路线"]},
]

def fetch(url, timeout=15):
    req = Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/json,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
    })
    try:
        with urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        return f"ERROR:{e}"

def parse_share_urls(text):
    """从文本中提取抖音分享链接 /video/xxx 或 share/link"""
    urls = set()
    for m in re.finditer(r'(?:https?://)?(?:www\.)?(?:v\.)?douyin\.com/(?:share/video/|video/)(\d+)', text):
        urls.add(f"https://www.douyin.com/video/{m.group(1)}")
    for m in re.finditer(r'(?:https?://)?(?:www\.)?douyin\.com/note/(\d+)', text):
        urls.add(f"https://www.douyin.com/note/{m.group(1)}")
    return list(urls)

def search_douyin_html(keyword, max_items=6):
    """通过抖音搜索页面HTML提取视频信息（非JS渲染版）"""
    encoded = quote_plus(keyword)
    url = f"https://www.douyin.com/search/{encoded}?type=video"
    html = fetch(url, timeout=15)
    
    results = []
    
    # 尝试从HTML中提取视频ID
    video_ids = set()
    for m in re.finditer(r'/video/(\d+)', html):
        video_ids.add(m.group(1))
    
    # 从JSON数据中提取（抖音搜索页内嵌了JSON数据）
    json_blocks = re.findall(r'window\._SSR_HYDRATED_DATA\s*=\s*({.*?});', html, re.DOTALL)
    for block in json_blocks:
        try:
            data = json.loads(block)
            items = data.get("app", {}).get("videoList", []) or data.get("defaultSearchData", {}).get("videoList", []) or []
            for item in items[:max_items]:
                vid = item.get("aweme_id", "") or item.get("video", {}).get("aweme_id", "")
                title = item.get("desc", "") or item.get("video", {}).get("description", "")
                author = item.get("author", {}).get("nickname", "") if isinstance(item.get("author"), dict) else ""
                results.append({
                    "video_id": vid,
                    "source_url": f"https://www.douyin.com/video/{vid}",
                    "title": title[:200] if len(title) > 200 else title,
                    "author": author,
                    "keyword": keyword,
                })
        except (json.JSONDecodeError, TypeError):
            pass
    
    # 如果JSON方式没取到数据，用视频ID构建基础条目
    if not results and video_ids:
        for vid in list(video_ids)[:max_items]:
            results.append({
                "video_id": vid,
                "source_url": f"https://www.douyin.com/video/{vid}",
                "title": "",
                "author": "",
                "keyword": keyword,
            })
    
    return results

def fetch_video_info(video_url):
    """从抖音视频页面提取标题、描述等"""
    html = fetch(video_url, timeout=10)
    title = ""
    description = ""
    
    # 尝试从 meta 标签提取
    title_match = re.search(r'<title[^>]*>([^<]+)</title>', html)
    if title_match:
        title = title_match.group(1).replace(" - 抖音", "").strip()
    
    desc_match = re.search(r'<meta[^>]*name="description"[^>]*content="([^"]+)"', html)
    if desc_match:
        description = desc_match.group(1)[:300]
    
    # 尝试JSON数据中提取更完整的信息
    json_blocks = re.findall(r'<script[^>]*id="RENDER_DATA"[^>]*>({.*?})</script>', html, re.DOTALL)
    for block in json_blocks:
        try:
            data = json.loads(block.replace("&q;", '"'))
            # 递归找 description
            def find_key(obj, key):
                if isinstance(obj, dict):
                    for k, v in obj.items():
                        if k == key:
                            return v
                        r = find_key(v, key)
                        if r:
                            return r
                return None
            desc = find_key(data, "desc") or find_key(data, "description") or ""
            if desc:
                description = str(desc)[:300]
        except:
            pass
    
    return {"title": title, "description": description}

def extract_waypoints(text):
    """从文本中提取途经点"""
    waypoints = set()
    t = text.strip()
    if not t:
        return []
    
    # 路线连接符模式
    for sep in ["->", "→", "➡", "－", "—", "至", "到", "经", "途经", "路过"]:
        if sep in t:
            parts = re.split(r'(?:->|→|➡|⟶|－|—|至|到|经|途经|路过)', t)
            for p in parts:
                name = re.sub(r'^[^\u4e00-\u9fa5A-Za-z0-9]+|[^\u4e00-\u9fa5A-Za-z0-9]+$', '', p).strip()
                if name and 2 <= len(name) <= 20:
                    waypoints.add(name)
    
    # POI特征后缀匹配
    poi_pattern = re.compile(r'[\u4e00-\u9fa5A-Za-z0-9]{2,20}(?:服务区|古镇|景区|风景区|观景台|村|镇|县城|城区|公路|大道|大桥|驿站|营地|加油站|停车区|湖|山|岛|口岸|码头|隧道|广场|滨海路|检查站)')
    for m in poi_pattern.finditer(t):
        waypoints.add(m.group())
    
    return list(waypoints)

def main():
    print(f"[{datetime.now().isoformat()}] 开始抖音采集")
    
    all_results = []
    
    for route in ROUTE_KEYWORDS:
        route_results = []
        for keyword in route["keywords"]:
            print(f"  搜索: {keyword}")
            items = search_douyin_html(keyword, max_items=4)
            
            for item in items:
                # 获取完整视频信息
                info = fetch_video_info(item["source_url"])
                item["title"] = item["title"] or info["title"]
                item["description"] = info["description"]
                
                # 提取途径点
                combined_text = f"{item['title']} {item['description']}"
                item["waypoints"] = extract_waypoints(combined_text)
                item["fetched_at"] = datetime.now(timezone.utc).isoformat()
                
                route_results.append(item)
            
            time.sleep(2)  # 礼貌延迟
        
        all_results.append({
            "slug": route["slug"],
            "title": route["title"],
            "keyword_count": len(route["keywords"]),
            "video_count": len(route_results),
            "videos": route_results,
        })
        
        print(f"  {route['title']}: 找到 {len(route_results)} 个视频")
    
    output = {
        "source": "aliyun-douyin-collector",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "total_videos": sum(len(r["videos"]) for r in all_results),
        "routes": all_results,
    }
    
    output_path = OUTPUT_DIR / "douyin_collected_videos.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f"\n采集完成！共 {output['total_videos']} 个视频 -> {output_path}")

if __name__ == "__main__":
    main()
