#!/usr/bin/env python3
"""
douyin_doubao_summary.py

从最新的 search_*.json 提取视频 URL，通过 CDP HTTP API 控制浏览器
打开豆包，让豆包逐个总结视频内容，保存结果。

输出字段（固定）：
  - video_url: 抖音视频链接
  - author: 博主
  - title: 视频标题
  - doubao_summary: 豆包总结的完整文本
  - summary_at: 总结时间
"""

import json
import os
import time
import re
import glob
import urllib.request
import urllib.error

WORKSPACE = "C:\\Users\\Administrator\\.openclaw\\workspace"
SEARCH_DIR = os.path.join(WORKSPACE, "skills", "douyin-search", "search_results")
OUTPUT_PATH = os.path.join(WORKSPACE, "moto", "data", "raw", "doubao_summaries.json")
CDP_HTTP = "http://127.0.0.1:18800"
DOUBAO_URL = "https://www.doubao.com/chat/"

SUMMARY_FIELDS = ["video_url", "author", "title", "doubao_summary", "summary_at"]


def cdp_fetch(path, method="GET", data=None):
    """通过 CDP HTTP API 请求"""
    url = f"{CDP_HTTP}{path}"
    req = urllib.request.Request(url, method=method,
                                  headers={"Content-Type": "application/json"})
    if data is not None:
        req.data = json.dumps(data).encode("utf-8")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body)
    except Exception as e:
        print(f"[!] CDP HTTP error: {e}")
        return None


def get_or_create_doubao_page():
    """获取已有的豆包页面，没有就新创建一个"""
    pages = cdp_fetch("/json")
    if not pages:
        return None, None
    
    for p in pages:
        url = p.get("url", "")
        if p.get("type") == "page" and "doubao.com/chat" in url:
            print(f"[+] Found existing Doubao page")
            return p["id"], p["webSocketDebuggerUrl"]
    
    # 创建新页面并导航
    new_page = cdp_fetch("/json/new", "PUT", {"url": DOUBAO_URL})
    if not new_page:
        print("[!] Failed to create page, trying to navigate existing tab")
        # 直接导航第一个页面
        for p in pages:
            if p.get("type") == "page":
                return p["id"], p["webSocketDebuggerUrl"]
        return None, None
    
    page_id = new_page["id"]
    ws_url = new_page["webSocketDebuggerUrl"]
    
    # 导航到豆包
    navigate_url = f"{CDP_HTTP}/json/activate/{page_id}"
    try:
        urllib.request.urlopen(urllib.request.Request(navigate_url), timeout=5)
    except:
        pass
    
    print(f"[+] Created new page {page_id[:8]}..., navigating to Doubao")
    return page_id, ws_url


def http_api_command(page_id, method, params=None):
    """通过 CDP HTTP API 发送命令（简化版）"""
    # CDP 的主要编程接口是 WebSocket，但我们可以通过
    # 截图和 evaluate 的 REST 方式
    pass


def get_page_text_http(page_id):
    """通过 CDP HTTP 获取页面文本"""
    # 使用 /json/activate/{id} 确保页面是激活的
    try:
        urllib.request.urlopen(
            urllib.request.Request(f"{CDP_HTTP}/json/activate/{page_id}"),
            timeout=5
        )
    except:
        pass
    
    # 通过 CDP 的 /json 获取页面信息
    pages = cdp_fetch("/json")
    if not pages:
        return ""
    
    for p in pages:
        if p.get("id") == page_id:
            return p.get("title", "")
    return ""


def get_latest_search_file():
    """获取最新的 search_*.json 文件"""
    files = sorted(glob.glob(os.path.join(SEARCH_DIR, "search_*.json")), reverse=True)
    if not files:
        print("[!] No search_*.json files found")
        return None
    return files[0]


def extract_video_urls(search_file):
    """从 search JSON 中提取所有视频 URL"""
    with open(search_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    urls = []
    seen = set()
    
    for keyword, items in data.get("results", {}).items():
        for item in items or []:
            url = item.get("url", "")
            if url and url not in seen:
                seen.add(url)
                urls.append({
                    "url": url,
                    "author": item.get("author", ""),
                    "title": item.get("title", ""),
                    "keyword": keyword
                })
    
    print(f"[+] Extracted {len(urls)} unique URLs from {os.path.basename(search_file)}")
    return urls


def load_existing_summaries():
    """加载已有的总结结果"""
    try:
        with open(OUTPUT_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("items", [])
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_summaries(items):
    """保存总结到文件"""
    output = {
        "source": "doubao-summary",
        "exported_at": time.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        "total": len(items),
        "items": items
    }
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[+] Saved {len(items)} summaries -> {OUTPUT_PATH}")


if __name__ == "__main__":
    print("=" * 60)
    print("Douyin → Doubao Summary Pipeline")
    print("=" * 60)
    print()
    print("[!] 本脚本通过 Python 控制浏览器")
    print("[!] 需要先运行 scan_and_summarize.py 配合 OpenClaw 的 browser 工具")
    print()
    print("[*] 独立运行仅支持文件操作（提取/加载/保存）")
    print()
    
    # 文件操作测试
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "extract":
        sf = get_latest_search_file()
        if sf:
            urls = extract_video_urls(sf)
            print(f"\nFound {len(urls)} videos:")
            for u in urls[:10]:
                print(f"  {u['author'] or '?'}: {u['url']}")
    elif len(sys.argv) > 1 and sys.argv[1] == "save-test":
        test_items = [
            {
                "video_url": "https://www.douyin.com/video/7639753707559588763",
                "author": "盛京铁骑",
                "title": "#摩旅 #摩友 #跑山 #摩托车 #沈阳摩托车",
                "doubao_summary": "作者盛京铁骑推荐一条沈阳出发的中短途摩旅跑山路线，全程约300公里，辽阳进、本溪出，可玩一整天，有三大段纯跑山路段。具体路线：导航达荷香(途经娃子沟)→沿汤河水库骑行→导航连山关镇→再导航南天门→最后导航辽燕博物馆→返程可自选高速或国道。",
                "summary_at": time.strftime("%Y-%m-%dT%H:%M:%S+08:00")
            }
        ]
        existing = load_existing_summaries()
        all_items = existing + test_items
        save_summaries(all_items)
        print(f"Saved {len(test_items)} test items")
    else:
        print("Usage:")
        print("  python douyin_doubao_summary.py extract   - 提取最新 search 文件的 URL")
        print("  python douyin_doubao_summary.py save-test - 保存测试数据")
