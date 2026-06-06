"""
小红书路线采集v3 - 直接从搜索结果页提取，不开详情页
"""
from __future__ import annotations

import argparse
import json
import sys
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.run_local_social_collection import (
    update_status,
    sync_pending_candidate_queue,
    now_iso,
)
from scripts.gpx_generator import analyze_video_route_content, extract_place_names


DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "raw" / "xiaohongshu_route_manifest.json"
DEFAULT_CANDIDATES = PROJECT_ROOT / "data" / "raw" / "xiaohongshu_route_candidates.json"
DEFAULT_STATUS = PROJECT_ROOT / "data" / "raw" / "local_collection_status.json"

SEARCH_KEYWORDS = [
    "摩旅路线",
    "摩旅路线推荐",
    "摩旅西藏路线",
    "摩旅新疆路线",
    "自驾路线",
    "自驾游路线推荐",
    "自驾川藏线",
    "阿里大环线",
    "滇藏线 路书",
    "318川藏线 攻略",
]

XHS_SEARCH_URL = "https://www.xiaohongshu.com/search_result?keyword={}&source=web_search_result_notes"

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--keyword", action="append", dest="keywords")
    parser.add_argument("--max-items", type=int, default=50, help="总共最多采集数")
    parser.add_argument("--headless", action="store_true", default=True)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--raw-candidates-output", default=str(DEFAULT_CANDIDATES))
    parser.add_argument("--status", default=str(DEFAULT_STATUS))
    return parser.parse_args()


def current_cycle_index(status_path: Path) -> int:
    try:
        data = json.loads(status_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return 0
    return (data.get("cycle_count") or 0) + 1


def extract_items_from_search(page, max_items=50) -> list[dict]:
    """从搜索结果页提取笔记信息（不进入详情页）"""
    items = []

    # 尝试1: 从meta提取
    try:
        # 读取页面中所有note卡片
        note_data = page.evaluate("""() => {
            const cards = document.querySelectorAll('[class*="note-item"], [class*="search-result-item"], section.note-list > div, .feeds-page > div');
            const results = [];
            cards.forEach(card => {
                const link = card.querySelector('a');
                const titleEl = card.querySelector('[class*="title"], h3');
                const descEl = card.querySelector('[class*="desc"], [class*="abstract"], p');
                const authorEl = card.querySelector('[class*="author"], [class*="user"]');
                results.push({
                    url: link ? link.href : '',
                    title: titleEl ? titleEl.innerText.trim() : '',
                    desc: descEl ? descEl.innerText.trim() : '',
                    author: authorEl ? authorEl.innerText.trim() : '',
                });
            });
            return results;
        }""")
        if note_data:
            items.extend(note_data)
    except Exception:
        pass

    # 尝试2: 从window.__INITIAL_STATE__提取
    if len(items) < 5:
        try:
            state = page.evaluate("""() => {
                try { return JSON.parse(document.getElementById('__NEXT_DATA__').textContent); }
                catch(e) { return null; }
            }""")
            if state:
                items.append({"_source": "next_data", "state_keys": str(list(state.keys())[:5])})
        except Exception:
            pass

    # 尝试3: 从页面HTML正则匹配
    if len(items) < 5:
        html = page.content()
        # 匹配 note-card 结构
        note_ids = re.findall(r'/explore/([a-f0-9]{24})', html)
        titles = re.findall(r'<span[^>]*class="[^"]*title[^"]*"[^>]*>([^<]+)</span>', html)
        descs = re.findall(r'<span[^>]*class="[^"]*desc[^"]*"[^>]*>([^<]+)</span>', html)
        unique_ids = list(set(note_ids))

        for i, nid in enumerate(unique_ids[:max_items]):
            items.append({
                "url": f"https://www.xiaohongshu.com/explore/{nid}",
                "title": titles[i] if i < len(titles) else "",
                "desc": descs[i] if i < len(descs) else "",
                "author": "",
                "tags": [],
            })

    return items


def main():
    args = parse_args()
    started_at = datetime.now(timezone.utc)

    keywords = args.keywords or SEARCH_KEYWORDS
    output_path = Path(args.output).resolve()
    candidates_path = Path(args.raw_candidates_output).resolve()
    status_path = Path(args.status).resolve()
    cycle_index = current_cycle_index(status_path)

    all_items = []
    seen_urls = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.headless)
        context = browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent=USER_AGENT,
        )
        page = context.new_page()

        for kw in keywords:
            if len(all_items) >= args.max_items:
                break

            print(f"\n[搜索] {kw}")
            url = XHS_SEARCH_URL.format(kw)
            try:
                page.goto(url, timeout=30000, wait_until="domcontentloaded")
                time.sleep(3)
                # 关弹窗
                page.keyboard.press("Escape")
                time.sleep(1)
            except Exception as e:
                print(f"  [!] 加载失败: {e}")
                continue

            # 滚动加载
            for _ in range(5):
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(2)

            items = extract_items_from_search(page, args.max_items)
            print(f"  提取到 {len(items)} 条")

            for item in items:
                url = item.get("url") or ""
                if url in seen_urls:
                    continue
                seen_urls.add(url)

                title = item.get("title") or item.get("desc") or ""
                desc = item.get("desc") or ""

                # 路线分析
                text_blob = f"{title} {desc} {' '.join(item.get('tags', []))}"
                place_names = extract_place_names(text_blob)
                route_analysis = analyze_video_route_content(
                    {"title": title}, text_blob, place_names
                ) if title else {}

                all_items.append({
                    "platform": "xiaohongshu",
                    "title": title,
                    "summary": desc[:500],
                    "url": url,
                    "author": item.get("author", ""),
                    "contentTags": item.get("tags", []),
                    "routeAnalysis": route_analysis,
                })

                if len(all_items) >= args.max_items:
                    break

        context.close()
        browser.close()

    qualified = [i for i in all_items if str((i.get("routeAnalysis") or {}).get("qualificationStatus") or "") == "qualified"]
    rejected = [i for i in all_items if i not in qualified]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps({
        "source": "xiaohongshu-route-collector-pw-v3",
        "exported_at": now_iso(),
        "items": all_items,
        "stats": {
            "discovered": len(all_items),
            "matched": len(all_items),
            "qualified": len(qualified),
            "rejected": len(rejected),
            "queued": len(qualified),
        },
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    candidates_path.write_text(json.dumps(qualified, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    queue_sync = sync_pending_candidate_queue(qualified)

    duration = round((datetime.now(timezone.utc) - started_at).total_seconds(), 2)
    run_stats = {"matched": len(all_items), "qualified": len(qualified), "rejected": len(rejected)}

    update_status(
        status_path,
        collector_name="xiaohongshu-route-collector-pw-v3",
        run_mode="once", current_stage="idle",
        current_task="",
        pipeline_status="skipped",
        pipeline_summary=f"pw search collected {len(all_items)} xhs notes -> {len(qualified)} qualified",
        script_command=".venv/bin/python scripts/collect_xiaohongshu_routes_playwright.py",
        output_path=str(output_path),
        raw_candidates_path=str(candidates_path),
        log_path=str(output_path.with_suffix(".log")),
        cycle_count=cycle_index,
        last_heartbeat=now_iso(),
        last_success_at=now_iso(),
        last_duration_seconds=duration,
        items_collected=run_stats["qualified"],
        tasks_completed=run_stats["matched"],
        tasks_total=run_stats["matched"],
        pending_candidates_processed=queue_sync["processed"],
        pending_candidates_added=queue_sync["added"],
        pending_candidates_updated=queue_sync["updated"],
        pending_candidates_total=queue_sync["total"],
        event_message=f"小红书(PW搜索页)采集完成：{run_stats['matched']}条，合格{run_stats['qualified']}条",
        cycle_entry={
            "cycle": cycle_index, "finished_at": now_iso(), "state": "success",
            "items_collected": run_stats["qualified"],
            "tasks_completed": run_stats["matched"],
            "tasks_total": run_stats["matched"],
            "duration_seconds": duration,
        },
    )

    print(f"\n[完成] {run_stats['matched']} matched / {run_stats['qualified']} qualified / {run_stats['rejected']} rejected / {duration}s")


if __name__ == "__main__":
    main()
