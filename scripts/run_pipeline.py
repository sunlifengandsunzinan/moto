#!/usr/bin/env python3
"""
run_pipeline.py

在主会话中运行完整的抖音采集→豆包总结流水线。

Phase 1: CDP 搜索（douyin_search_cdp.py）
Phase 2: 去重，找出新视频
Phase 3: 用浏览器操作豆包逐个总结
Phase 4: 保存到 doubao_summaries.json
"""

import json
import os
import subprocess
import sys
import time
import re
import asyncio
from datetime import datetime
from playwright.async_api import async_playwright

WORKSPACE = "C:\\Users\\Administrator\\.openclaw\\workspace"
SEARCH_SCRIPT = os.path.join(WORKSPACE, "skills", "douyin-search", "scripts", "douyin_search_cdp.py")
SEARCH_DIR = os.path.join(WORKSPACE, "skills", "douyin-search", "search_results")
SUMMARY_FILE = os.path.join(WORKSPACE, "moto", "data", "raw", "doubao_summaries.json")
CDP_URL = "http://127.0.0.1:18800"


def run_search():
    """Phase 1: 运行 CDP 搜索脚本"""
    print("=" * 60)
    print("Phase 1: CDP 搜索")
    print("=" * 60)
    
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    
    result = subprocess.run(
        [sys.executable, "-u", SEARCH_SCRIPT],
        capture_output=True, text=True, env=env, timeout=180
    )
    
    print(result.stdout[-2000:] if len(result.stdout) > 2000 else result.stdout)
    if result.stderr:
        print(f"STDERR: {result.stderr[-500:]}")
    
    # Find the latest search file
    files = sorted([f for f in os.listdir(SEARCH_DIR) if f.startswith("search_") and f.endswith(".json")], reverse=True)
    if not files:
        print("[!] No search results found!")
        return None
    
    latest = os.path.join(SEARCH_DIR, files[0])
    print(f"最新搜索文件: {files[0]}")
    
    with open(latest, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    print(f"搜索到视频: {data.get('total', 0)} 去重: {data.get('unique_links', 0)}")
    return latest


def find_new_videos(search_file):
    """Phase 2: 去重，找出未总结的新视频"""
    print("\n" + "=" * 60)
    print("Phase 2: 去重过滤")
    print("=" * 60)
    
    with open(search_file, "r", encoding="utf-8") as f:
        search_data = json.load(f)
    
    # Load existing summaries
    existing_urls = set()
    if os.path.exists(SUMMARY_FILE):
        with open(SUMMARY_FILE, "r", encoding="utf-8") as f:
            summary_data = json.load(f)
        for item in summary_data.get("items", []):
            existing_urls.add(item.get("video_url", ""))
    
    print(f"已有总结: {len(existing_urls)} 条")
    
    # Collect all video URLs from search results
    all_items = []
    seen_urls = set()
    
    for kw, items in search_data.get("results", {}).items():
        if not items:
            continue
        for item in items:
            url = item.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                all_items.append(item)
    
    # Filter new ones
    new_items = [it for it in all_items if it.get("url", "") not in existing_urls]
    
    print(f"搜索结果去重后: {len(all_items)} 条")
    print(f"未总结的新视频: {len(new_items)} 条")
    
    return new_items


def load_existing_summaries():
    """Load current summaries"""
    if os.path.exists(SUMMARY_FILE):
        with open(SUMMARY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"source": "doubao_summary", "items": []}


def save_summaries(items):
    """Save to summary file immediately"""
    output = {
        "source": "doubao_summary",
        "exported_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        "total": len(items),
        "items": items
    }
    os.makedirs(os.path.dirname(SUMMARY_FILE), exist_ok=True)
    with open(SUMMARY_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[+] 已保存 {len(items)} 条 -> {SUMMARY_FILE}")


async def doubao_summarize(item):
    """Phase 3: 用浏览器操作豆包总结一条视频"""
    url = item.get("url", "")
    author = item.get("author", "")
    title = item.get("title", "")
    
    prompt = f"请分析这个抖音摩旅视频的路线信息：标题「{author} - {title}」，视频链接：{url}\n\n请总结：1) 具体路线/途经点 2) 适合摩旅还是自驾 3) 里程和天数（如果有）。如果信息不足请说明。"
    
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(CDP_URL)
        context = browser.contexts[0] if browser.contexts else await browser.new_context()
        page = await context.new_page()
        
        try:
            # Open a new doubao chat
            await page.goto("https://www.doubao.com/chat/", wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(2000)
            
            # Click "新对话" button
            # Find the textbox first
            textbox = await page.query_selector('textarea, [contenteditable="true"], [class*="input"], [placeholder*="消息"]')
            if textbox:
                await textbox.fill(prompt)
                await page.wait_for_timeout(500)
                # Click send button
                send_btn = await page.query_selector('button[class*="send"], button[type="submit"]')
                if send_btn:
                    await send_btn.click()
                else:
                    await page.keyboard.press("Enter")
                    
            # Wait for response
            await page.wait_for_timeout(15000)
            
            # Get the response text
            summary = await page.evaluate("""() => {
                // Try different selectors for doubao response
                const selectors = [
                    '[class*="message-bubble"]:last-child',
                    '[class*="answer"]:last-child',
                    '[class*="response"]:last-child',
                    '.message-content:last-child',
                    '[class*="chat"] [class*="content"]:last-child'
                ];
                for (const sel of selectors) {
                    const el = document.querySelector(sel);
                    if (el) return el.textContent.trim();
                }
                // Fallback: get all text
                const main = document.querySelector('main') || document.body;
                const allText = main.innerText;
                // Try to find response after our prompt
                const lines = allText.split('\\n');
                return lines.slice(-20).join('\\n').substring(0, 500);
            }""")
            
            await page.close()
            return summary or "[总结失败] 豆包未返回有效内容"
            
        except Exception as e:
            print(f"  [!] Error: {e}")
            try:
                await page.close()
            except:
                pass
            return "[总结失败]"


async def process_new_videos(new_videos):
    """Process all new videos through doubao"""
    print("\n" + "=" * 60)
    print(f"Phase 3: 豆包总结 ({len(new_videos)} 条)")
    print("=" * 60)
    
    existing = load_existing_summaries()
    items = existing.get("items", [])
    processed = 0
    failed_count = 0
    
    for i, video in enumerate(new_videos):
        url = video.get("url", "")
        author = video.get("author", video.get("nickname", ""))
        title = video.get("title", "")
        
        print(f"\n[{i+1}/{len(new_videos)}] @{author}")
        
        summary = await doubao_summarize(video)
        
        if summary == "[总结失败] 豆包未返回有效内容" or summary == "[总结失败]":
            failed_count += 1
        
        entry = {
            "video_url": url,
            "author": author,
            "title": title,
            "doubao_summary": summary,
            "summary_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S+08:00"),
            "source": "doubao"
        }
        
        items.append(entry)
        save_summaries(items)
        processed += 1
        
        print(f"  总结: {summary[:80]}...")
        if summary != "[总结失败]":
            print(f"  [OK]")
        else:
            print(f"  [FAIL]")
        
        # Pause between videos to avoid rate limiting
        if i < len(new_videos) - 1:
            delay = 3
            print(f"  ... 等待 {delay}s ...")
            await asyncio.sleep(delay)
    
    print(f"\n→ 处理: {processed} 条, 失败: {failed_count}")


async def main():
    print(f"🚀 抖音采集流水线启动 ({datetime.now().strftime('%H:%M:%S')})")
    print()
    
    # Phase 1: Search
    search_file = run_search()
    if not search_file:
        print("[!] 搜索失败，终止")
        return
    
    # Phase 2: Find new videos
    new_videos = find_new_videos(search_file)
    
    if not new_videos:
        print("\n[✓] 没有新视频需要总结！")
        return
    
    print(f"\n  新视频预览（前10条）:" if len(new_videos) > 0 else "")
    for v in new_videos[:10]:
        print(f"    {v.get('url','')} @{v.get('author','?')}")
    
    if len(new_videos) > 10:
        print(f"    ... 还有 {len(new_videos)-10} 条")
    
    # Ask user before proceeding
    print(f"\n❓ 准备用豆包总结 {len(new_videos)} 条视频，继续吗？")
    print("   (脚本会逐个操作豆包网页版，预计耗时较长)")
    
    # Phase 3: Summarize
    await process_new_videos(new_videos)
    
    print(f"\n{'='*60}")
    print(f"[✓] 流水线完成!")
    print(f"   总计: {len(new_videos)} 条新视频")
    print(f"   保存: {SUMMARY_FILE}")
    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
