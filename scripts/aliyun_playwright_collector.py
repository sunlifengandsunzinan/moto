#!/usr/bin/env python3
"""阿里云抖音视频采集 - 使用 Playwright 无头浏览器"""
import asyncio
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

OUTPUT_DIR = Path("/root/moto/data/raw")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ===== 路线搜索关键词 =====
ROUTES = [
    {"slug": "liaoning-bengxi-greenriver", "title": "本溪到绿江边境风景线", "keywords": ["本溪 绿江村 摩旅", "本桓公路 骑行", "青山沟 宽甸 摩旅"]},
    {"slug": "liaoning-dalian-coastal", "title": "大连滨海轻骑线", "keywords": ["大连滨海路 骑行", "大连 金石滩 摩旅", "大连 旅顺 沿海 骑行"]},
    {"slug": "liaoning-border-scenic", "title": "辽东边境风景线", "keywords": ["青山沟 绿江村 摩旅", "宽甸 丹东 骑行", "辽东边境 摩旅"]},
    {"slug": "liaoning-red-beach", "title": "红海滩海滨轻松线", "keywords": ["盘锦红海滩 摩旅", "兴城 葫芦岛 骑行", "红海滩 摩旅"]},
    {"slug": "liaoning-general", "title": "辽宁摩旅通用", "keywords": ["辽宁摩旅", "沈阳周边骑行", "辽宁机车路线"]},
]

async def search_douyin(page, keyword, max_items=6):
    """在抖音搜索页面搜索关键词"""
    url = f"https://www.douyin.com/search/{keyword}?type=video"
    await page.goto(url, timeout=30000, wait_until="domcontentloaded")
    # 等待内容加载
    await asyncio.sleep(4)
    
    results = []
    
    # 方法1: 提取视频链接 a[href*=video/]
    links = await page.query_selector_all("a[href*='/video/']")
    seen = set()
    for link in links:
        href = await link.get_attribute("href")
        if not href:
            continue
        vid = href.split("/video/")[-1].split("?")[0] if "/video/" in href else ""
        if not vid or vid in seen:
            continue
        seen.add(vid)
        
        # 尝试获取标题
        title = ""
        spans = await link.query_selector_all("span")
        for s in spans:
            t = await s.inner_text()
            if t.strip():
                title = t.strip()
                break
        
        results.append({
            "video_id": vid,
            "source_url": f"https://www.douyin.com/video/{vid}",
            "title": title[:200] if len(title) > 200 else title,
            "keyword": keyword,
        })
        
        if len(results) >= max_items:
            break
    
    return results

async def fetch_video_details(page, video_url):
    """获取视频页面详情"""
    try:
        await page.goto(video_url, timeout=15000, wait_until="domcontentloaded")
        await asyncio.sleep(2)
    except:
        return {"title": "", "description": "", "author": ""}
    
    title = await page.title()
    title = title.replace(" - 抖音", "").strip()
    
    # 提取页面JSON数据
    author = ""
    description = ""
    html = await page.content()
    
    # 从meta标签提取
    desc_meta = await page.query_selector('meta[name="description"]')
    if desc_meta:
        description = await desc_meta.get_attribute("content") or ""
    
    # 尝试从页面文本提取作者
    author_el = await page.query_selector('[class*=author], [class*=nickname]')
    if author_el:
        author = await author_el.inner_text()
    
    return {"title": title[:200], "description": description[:300], "author": author.strip()}

def extract_waypoints(text):
    """从文本中提取途经点名"""
    waypoints = set()
    t = text.strip()
    if not t:
        return []
    
    for sep in ["->", "→", "➡", "－", "—", "至", "到", "经"]:
        if sep in t:
            parts = re.split(r"(?:->|→|➡|⟶|－|—|至|到|经|途经|路过)", t)
            for p in parts:
                name = re.sub(r"^[^\u4e00-\u9fa5A-Za-z0-9]+|[^\u4e00-\u9fa5A-Za-z0-9]+$", "", p).strip()
                if name and 2 <= len(name) <= 20:
                    waypoints.add(name)
    
    poi = re.compile(r"[\u4e00-\u9fa5A-Za-z0-9]{2,20}(?:服务区|古镇|景区|风景区|观景台|村|镇|县城|公路|大桥|驿站|营地|湖|山|岛|口岸|码头|隧道|广场|滨海路)")
    for m in poi.finditer(t):
        waypoints.add(m.group())
    
    return list(waypoints)

async def should_page_intercept(response):
    """拦截XHR响应获取数据"""
    pass  # 暂不需要

async def main():
    print(f"[{datetime.now().isoformat()}] 启动 Playwright 采集")
    
    from playwright.async_api import async_playwright
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
            locale="zh-CN"
        )
        page = await context.new_page()
        
        all_results = []
        
        for route in ROUTES:
            route_videos = []
            for keyword in route["keywords"]:
                print(f"  搜索: {keyword}")
                items = await search_douyin(page, keyword, max_items=4)
                
                for item in items:
                    details = await fetch_video_details(page, item["source_url"])
                    item.update(details)
                    combined = f"{item.get('title','')} {item.get('description','')}"
                    item["waypoints"] = extract_waypoints(combined)
                    item["fetched_at"] = datetime.now(timezone.utc).isoformat()
                    route_videos.append(item)
                    await asyncio.sleep(1)
            
            all_results.append({
                "slug": route["slug"],
                "title": route["title"],
                "video_count": len(route_videos),
                "videos": route_videos,
            })
            print(f"  [{route['title']}] 找到 {len(route_videos)} 个视频")
        
        await browser.close()
    
    output = {
        "source": "aliyun-douyin-playwright",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "total_videos": sum(r["video_count"] for r in all_results),
        "routes": all_results,
    }
    
    output_path = OUTPUT_DIR / "douyin_collected_videos.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f"\n采集完成！共 {output['total_videos']} 个视频 -> {output_path}")

if __name__ == "__main__":
    asyncio.run(main())
