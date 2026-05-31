#!/usr/bin/env python3
"""
抖音摩旅路线提取 & GPX 生成器 — 纯本地、零 Token
===================================================
整合入 moto 项目版本。

输出: data/gpx/*.gpx
数据库: data/gpx/processed_videos.db
用户坐标: data/gpx/user_spots.json

用法:
  python scripts/gpx_generator.py "盛京铁骑"
  python scripts/gpx_generator.py --url <douyin_url>
  python scripts/gpx_generator.py --list-db
  python scripts/gpx_generator.py --add-spot "地名,纬度,经度"
  python scripts/gpx_generator.py --export-spots   # 导出途经点为候选点位
"""

import argparse, json, logging, os, re, sqlite3, sys, time, urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("gpx_gen")

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout
except ImportError:
    sync_playwright = None
    PwTimeout = TimeoutError

# ====================================================================
# 路径（适配 moto 项目）
# ====================================================================
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
GPX_DIR = PROJECT_ROOT / "data" / "gpx"
GPX_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = GPX_DIR / "processed_videos.db"
SPOTS_USER_PATH = GPX_DIR / "user_spots.json"
OPENCLAW_ROUTE_WAYPOINTS_PATH = PROJECT_ROOT / "data" / "raw" / "openclaw_route_waypoints.json"

# ====================================================================
# 辽宁摩旅坐标字典（内置 90+ 点）
# ====================================================================
_BUILTIN_SPOTS = {
    "沈阳": (41.8057,123.4315), "沈阳站": (41.7940,123.4058), "沈阳北站": (41.8320,123.4370),
    "沈阳桃仙机场": (41.6335,123.4904), "沈阳故宫": (41.7946,123.4517), "中街": (41.7990,123.4530),
    "太原街": (41.7880,123.4160), "辽阳": (41.2719,123.2399), "弓长岭": (41.1558,123.4314),
    "瓦子沟旅游风景区": (41.1503,123.4407), "瓦子沟": (41.1503,123.4407),
    "下达河乡": (41.0600,123.2700), "下达河": (41.0600,123.2700), "人参谷": (41.1500,123.2800),
    "汤河水库": (41.1000,123.3500), "太子岛": (41.1800,123.2200), "燕州城": (41.2289,123.2425),
    "鸭子沟": (41.0600,123.3700), "辽阳天主堂": (41.2700,123.2350),
    "本溪": (41.3256,123.7686), "本溪县": (41.3015,124.1191), "连山关镇": (40.9700,123.6500),
    "连山关": (40.9700,123.6500), "南芬": (41.1200,123.7800), "南芬区": (41.1200,123.7800),
    "南天门": (41.0900,123.7700), "辽砚博物馆": (41.1318,123.7812), "本溪水洞": (41.3153,123.8512),
    "小市": (41.3015,124.1191), "关门山": (41.2900,123.9500), "大冰沟": (41.1800,123.8500),
    "汤沟": (41.2200,124.0500), "绿石谷": (41.2200,124.0500), "金刚山龙峰寺": (41.1350,123.8050),
    "摩天岭": (41.0600,123.7580), "杜河湿地公园": (41.1200,123.7300),
    "南芬音乐公路": (41.1142,123.7536), "背阴汀铁路断桥": (41.1078,123.7594), "背阴汀": (41.1078,123.7594),
    "下马塘": (41.0389,123.6917), "英雄纪念广场": (41.1128,123.7558), "山有溪露营地": (41.0922,123.7611),
    "冰臼遗迹": (41.1100,123.7550), "溪溪里露营": (41.1000,123.7600), "财神庙": (41.1100,123.7500),
    "大峡谷进口": (41.1050,123.7600), "一面山": (41.1000,123.7700), "小峡谷": (41.0950,123.7650),
    "南虹大桥停车场": (41.1000,123.7450),
    "抚顺": (41.8820,123.9570), "大伙房水库": (41.8583,124.1667), "大伙房水库湿地公园": (41.8500,124.1500),
    "温道大桥": (41.8286,124.1083), "温道村": (41.8264,124.1056), "老五驴肉馆": (41.8250,124.1100),
    "碾三线": (41.8100,124.0800), "社河": (41.8400,124.1300), "萨尔浒": (41.8333,124.2000),
    "萨尔浒风景名胜区": (41.8333,124.2000), "三块石": (41.6200,124.3200), "猴石": (41.6500,124.2800),
    "岗山": (41.7500,124.4500), "鸦鹘关": (41.8500,124.3500),
    "鞍山": (41.1078,123.0000), "千山": (41.0350,123.0680), "千山风景区": (41.0350,123.0680),
    "汤岗子": (40.9900,122.8500), "海城": (40.8520,122.6850),
    "丹东": (40.1290,124.3830), "鸭绿江断桥": (40.1190,124.3880), "虎山长城": (40.2280,124.5140),
    "凤凰山": (40.4250,124.0680), "宽甸": (40.7310,124.7840), "绿江村": (40.8000,125.5000),
    "青山沟": (40.6800,124.8800), "天桥沟": (40.7100,125.0500),
    "铁岭": (42.2900,123.8440), "铁岭玉皇阁": (42.2870,123.8430), "象牙山": (42.3500,124.0200),
    "阜新": (42.0100,121.6700), "海棠山": (41.9600,121.6500), "朝阳": (41.5500,120.4500),
    "牛河梁": (41.3500,119.5500), "锦州": (41.0950,121.1270), "笔架山": (40.8500,121.0800),
    "青岩寺": (41.5600,121.1900), "医巫闾山": (41.6000,121.4700), "北镇": (41.5500,121.7700),
    "盘锦": (41.1210,122.0700), "红海滩": (40.9100,121.9700), "葫芦岛": (40.7110,120.8370),
    "兴城": (40.6200,120.6900), "东戴河": (40.0100,119.8900), "九门口长城": (40.1100,119.7100),
    "营口": (40.6670,122.2350), "鲅鱼圈": (40.2700,122.1600), "山海广场": (40.2600,122.1400),
    "望儿山": (40.2300,122.1300), "盖州": (40.4000,122.3500), "大连": (38.9140,121.6150),
    "旅顺": (38.8000,121.2680), "金石滩": (39.0800,122.0000),
    "法库": (42.5000,123.4000), "法库古镇": (42.5000,123.4000),
    "山海关": (39.9900,119.7500), "秦皇岛": (39.9300,119.6000), "北戴河": (39.8300,119.4900),
    "承德": (40.9500,117.9600), "赤峰": (42.2800,118.9500), "通辽": (43.6200,122.2400),
    "四平": (43.1700,124.3500), "长春": (43.9000,125.3200), "吉林": (43.8500,126.5500),
    "沈丹高速": (41.4000,123.5600), "沈大高速": (41.1500,123.0000), "沈吉高速": (41.8800,124.0000),
}

_PLACE_ALIASES = {
    "大伙房": "大伙房水库", "温道": "温道村", "鞍山站": "鞍山", "本溪站": "本溪",
    "丹东站": "丹东", "南芬站": "南芬", "沈阳站": "沈阳", "千山": "千山风景区",
    "萨尔浒": "萨尔浒风景名胜区",
}

def _load_spots():
    spots = dict(_BUILTIN_SPOTS)
    if SPOTS_USER_PATH.exists():
        try:
            with open(SPOTS_USER_PATH, "r", encoding="utf-8") as f:
                spots.update(json.load(f))
        except Exception:
            pass
    # 尝试加载 moto 已审批的景点库坐标
    approved_path = PROJECT_ROOT / "data" / "reviewed" / "approved_spots.json"
    if approved_path.exists():
        try:
            with open(approved_path, "r", encoding="utf-8") as f:
                approved = json.load(f)
            if isinstance(approved, list):
                for s in approved:
                    c = s.get("coordinates", {}); n = s.get("name") or ""; lat=c.get("lat"); lng=c.get("lng")
                    if n and lat and lng: spots[n] = (lat, lng)
            elif isinstance(approved, dict):
                for slug, s in approved.items():
                    c = s.get("coordinates", {}); n = s.get("name") or slug; lat=c.get("lat"); lng=c.get("lng")
                    if n and lat and lng: spots[n] = (lat, lng)
        except Exception:
            pass
    return spots

# ====================================================================
# 数据库
# ====================================================================
def init_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""CREATE TABLE IF NOT EXISTS processed_videos (
        video_id TEXT PRIMARY KEY, title TEXT, author TEXT, processed_at TEXT,
        gpx_path TEXT, spots_count INTEGER, spots_json TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS search_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT, keyword TEXT, searched_at TEXT,
        found_count INTEGER, processed_count INTEGER)""")
    _ensure_processed_video_columns(conn)
    conn.commit()
    return conn

def _ensure_processed_video_columns(conn):
    existing = {row[1] for row in conn.execute("PRAGMA table_info(processed_videos)").fetchall()}
    extra_columns = {
        "record_type": "TEXT DEFAULT 'video'",
        "route_slug": "TEXT",
        "route_days": "INTEGER",
        "distance_km": "REAL",
        "amap_href": "TEXT",
        "navigation_mode": "TEXT",
        "qualification_status": "TEXT",
        "qualification_reason": "TEXT",
        "source_channel": "TEXT",
        "waypoints_json": "TEXT",
        "evidence_json": "TEXT",
    }
    for column_name, column_type in extra_columns.items():
        if column_name not in existing:
            conn.execute(f"ALTER TABLE processed_videos ADD COLUMN {column_name} {column_type}")

def is_processed(conn, vid):
    return conn.execute("SELECT 1 FROM processed_videos WHERE video_id=?", (vid,)).fetchone() is not None

def mark_processed(conn, vid, title, author, gpx_path, spots):
    conn.execute(
        """
        INSERT OR REPLACE INTO processed_videos (
            video_id, title, author, processed_at, gpx_path, spots_count, spots_json,
            record_type, route_slug, route_days, distance_km, amap_href,
            navigation_mode, qualification_status, qualification_reason,
            source_channel, waypoints_json, evidence_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            vid,
            title,
            author,
            datetime.now(timezone.utc).isoformat(),
            gpx_path,
            len(spots),
            json.dumps(spots, ensure_ascii=False),
            "video",
            None,
            None,
            None,
            None,
            None,
            "video" if spots else "rejected",
            "",
            "douyin-gpx-generator",
            json.dumps(spots, ensure_ascii=False),
            json.dumps([], ensure_ascii=False),
        ),
    )
    conn.commit()

def upsert_route_record(conn, route_item, gpx_path, spots):
    route_slug = str(route_item.get("route_slug") or "").strip()
    route_title = str(route_item.get("route_title") or route_slug or "OpenClaw route").strip()
    reference_url = ((route_item.get("source") or {}).get("reference_url") if isinstance(route_item.get("source"), dict) else "") or ""
    record_id = f"route::{route_slug or re.sub(r'[^a-z0-9]+', '-', route_title.lower())}"
    conn.execute(
        """
        INSERT OR REPLACE INTO processed_videos (
            video_id, title, author, processed_at, gpx_path, spots_count, spots_json,
            record_type, route_slug, route_days, distance_km, amap_href,
            navigation_mode, qualification_status, qualification_reason,
            source_channel, waypoints_json, evidence_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            record_id,
            route_title,
            "openclaw-scheduled-task",
            datetime.now(timezone.utc).isoformat(),
            gpx_path,
            len(spots),
            json.dumps(spots, ensure_ascii=False),
            "route",
            route_slug,
            route_item.get("route_days"),
            route_item.get("route_distance_km"),
            ((route_item.get("amap_export") or {}).get("href") if isinstance(route_item.get("amap_export"), dict) else "") or reference_url,
            ((route_item.get("amap_export") or {}).get("navigation_mode") if isinstance(route_item.get("amap_export"), dict) else "") or "coordinates",
            route_item.get("qualification_status") or "qualified",
            route_item.get("qualification_reason") or "",
            ((route_item.get("source") or {}).get("channel") if isinstance(route_item.get("source"), dict) else "") or "openclaw-route-waypoints",
            json.dumps(route_item.get("navigation", {}).get("waypoints", []), ensure_ascii=False),
            json.dumps(route_item.get("evidence_items", []), ensure_ascii=False),
        ),
    )
    conn.commit()

# ====================================================================
# 地名提取引擎
# ====================================================================
TERRAIN_WORDS = "桥 乡 镇 村 屯 水库 湖 河 江 海 山 岭 峰 崖 沟 峪 洼 坡 岗 景区 公园 湿地 遗址 旧址 古迹 博物馆 纪念馆 广场 营地 度假村 路 大道 大街 街道 驿站 服务区 加油站 观景台 寺 庙 观 塔 岛 滩 湾 港 码头 堡 城 关 门".split()

STOP_WORDS = {"提示","注意","推荐","总结","说明","欢迎","关注","点赞","收藏","评论","转发","分享","链接","作者","来源","视频","封面","文案","话题","标签","粉丝","作品","主页","全部","最新","热门","相关","更多","其他","以上","公里","分钟","小时","时速","上午","下午","中午","晚上","今日","明天","昨天","天气","温度","大约","左右","全程","安全","小心","注意","谨慎","建议","适合","油耗","油费","过路费","费用","第一条","第二条","第一个","第二个","地址","位置","导航","东北","华北","华东","华南","西北","西南","沈阳摩友","同城","附近"}

def _valid_place(name):
    if not name or len(name)<2 or len(name)>15: return False
    if name in STOP_WORDS or not re.search(r'[\u4e00-\u9fff]',name): return False
    if re.match(r'^[\d#@·,.\-—/\\()（）\[\]【】]+$',name) or name.isdigit(): return False
    if re.match(r'^第[一二三四五六七八九十\d]',name): return False
    return True

def extract_place_names(text):
    if not text: return []
    spots = _load_spots(); found=[]; seen=set()
    t = text.replace("\n"," ").replace("｜","|").replace("、"," ")
    for name in sorted(spots, key=len, reverse=True):
        if name in t and name not in seen: seen.add(name); found.append(name)
    for m in re.finditer(r'[①②③④⑤⑥⑦⑧⑨⑩]\s*[：:]?\s*([\u4e00-\u9fff][\u4e00-\u9fff\w]{1,14})', t):
        n = m.group(1).strip()
        if _valid_place(n) and n not in seen: seen.add(n); found.append(n)
    for m in re.finditer(r'(?:(?<=\n)|^)\s*\d+[\.、．]\s*([\u4e00-\u9fff][\u4e00-\u9fff\w]{1,14})', text):
        n = m.group(1).strip()
        if _valid_place(n) and n not in seen: seen.add(n); found.append(n)
    for tw in TERRAIN_WORDS:
        for m in re.finditer(rf'([\u4e00-\u9fff][\u4e00-\u9fff\w]{{0,10}}{re.escape(tw)})', t):
            n = m.group(1).strip()
            if _valid_place(n) and n not in seen: seen.add(n); found.append(n)
    return found

def ensure_playwright_available():
    if sync_playwright is None:
        raise RuntimeError("缺少 playwright: pip install playwright && python -m playwright install chromium")

def find_coords(name):
    spots = _load_spots()
    if name in spots: lat,lng=spots[name]; return {"lat":lat,"lng":lng,"source":"精确"}
    if name in _PLACE_ALIASES:
        r=_PLACE_ALIASES[name]
        if r in spots: lat,lng=spots[r]; return {"lat":lat,"lng":lng,"source":f"别名→{r}"}
    for k,(lat,lng) in spots.items():
        if name in k or k in name: return {"lat":lat,"lng":lng,"source":f"近似→{k}"}
    return None

# ====================================================================
# GPX 生成
# ====================================================================
def _x(s):
    return s.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;").replace("'","&apos;")

def generate_gpx(spots, title, url):
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<gpx version="1.1" creator="douyin-route-gpx"',
        '  xmlns="http://www.topografix.com/GPX/1/1"',
        '  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"',
        '  xsi:schemaLocation="http://www.topografix.com/GPX/1/1 http://www.topografix.com/GPX/1/1/gpx.xsd">',
        f"  <trk>",
        f"    <name>{_x(title)}</name>",
        f"    <desc>{_x(f'来源: {url}')}</desc>",
        "    <trkseg>",
    ]
    for s in spots:
        n = _x(s["name"]);
        d = n + (f" ({s.get('note','')})" if s.get("note") else "")
        lines.append(f'      <trkpt lat="{s["lat"]}" lon="{s["lng"]}">')
        lines.append(f"        <name>{n}</name>")
        lines.append(f"        <desc>{_x(d)}</desc>")
        lines.append("      </trkpt>")
    lines += ["    </trkseg>","  </trk>","</gpx>"]
    return "\n".join(lines)

def write_gpx_file(file_stem, title, url, spots):
    safe = re.sub(r'[\\/:*?"<>|#@!]', '', file_stem)[:80].strip('_ ')
    if not safe:
        safe = f"route_{int(time.time())}"
    safe = safe.replace(' ', '_')[:80]
    gpx_path = GPX_DIR / f"{safe}.gpx"
    with open(gpx_path, "w", encoding="utf-8") as f:
        f.write(generate_gpx(spots, title, url))
    return str(gpx_path)

# ====================================================================
# 抖音视频提取（Playwright）
# ====================================================================
def extract_video_info(url):
    ensure_playwright_available()
    m = re.search(r'/video/(\d+)',url)
    if not m: log.error(f"无效URL: {url}"); return None
    video_id = m.group(1)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True,args=["--no-sandbox","--disable-blink-features=AutomationControlled"])
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            viewport={"width":1280,"height":800}, locale="zh-CN")
        page = ctx.new_page()
        try:
            log.info(f"打开: {url}")
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(5000)
            title = ""
            for sel in ['h1[data-testid="videoTitle"]','h1','meta[property="og:title"]','meta[name="description"]','title']:
                try:
                    el = page.query_selector(sel)
                    if el:
                        t = el.get_attribute("content") or el.inner_text()
                        if t and len(t)>5: title=t.strip(); break
                except: continue
            title = re.sub(r'\s*[-–—]\s*抖音.*$','',title).strip()
            if not title: title = f"抖音视频_{video_id}"
            author = ""
            for sel in ['[data-testid="videoAuthor"]','.author-name','.nickname','[class*="author"]','[class*="nickname"]']:
                try:
                    el=page.query_selector(sel)
                    if el: a=el.inner_text().strip()
                    if a: author=a; break
                except: continue
            text_content = ""
            try:
                body = page.query_selector("body")
                if body: text_content = body.inner_text()
            except: pass
            for _ in range(5):
                try: page.evaluate("window.scrollBy(0,600)"); page.wait_for_timeout(1000)
                except: break
            comments_text = ""
            idx = text_content.find("评论")
            comments_text = text_content[idx:idx+5000] if idx>0 else (text_content[-3000:] if len(text_content)>3000 else text_content)
            browser.close()
            log.info(f"标题: {title[:60]} | 作者: {author or '未知'} | 文本: {len(text_content)}字")
            return {"video_id":video_id,"url":url,"title":title,"author":author,"text_content":text_content,"comments_text":comments_text}
        except PwTimeout: log.error(f"超时: {url}"); browser.close(); return None
        except Exception as e: log.error(f"提取失败: {e}"); browser.close(); return None

# ====================================================================
# 抖音搜索
# ====================================================================
def search_douyin(keyword, max_results=10):
    ensure_playwright_available()
    url = f"https://www.douyin.com/search/{urllib.parse.quote(keyword)}?type=general"
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True,args=["--no-sandbox","--disable-blink-features=AutomationControlled"])
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            viewport={"width":1280,"height":800}, locale="zh-CN")
        page = ctx.new_page(); results=[]
        try:
            log.info(f"搜索: {keyword}")
            page.goto(url, wait_until="domcontentloaded", timeout=30000); page.wait_for_timeout(8000)
            seen=set(); html=page.content()
            for m in re.finditer(r'/video/(\d{19})',html):
                v=m.group(1)
                if v not in seen: seen.add(v); results.append({"url":f"https://www.douyin.com/video/{v}","video_id":v})
                if len(results)>=max_results: break
            browser.close(); log.info(f"结果: {len(results)}个"); return results[:max_results]
        except PwTimeout: browser.close(); return results
        except Exception as e: log.error(f"搜索失败: {e}"); browser.close(); return results

# ====================================================================
# 核心处理
# ====================================================================
def process_video(url, conn=None):
    info = extract_video_info(url)
    if not info: return None
    close = False
    if conn is None: conn=init_db(); close=True
    vid,title,author=info["video_id"],info["title"],info["author"]
    if is_processed(conn,vid): log.info(f"已处理: {title[:40]}"); return None
    log.info(f"处理: {title[:60]}")
    all_text = "\n".join(filter(None,[info.get("text_content",""),info.get("comments_text","")]))
    places = extract_place_names(all_text)
    if not places: log.warning("未提取到地名"); mark_processed(conn,vid,title,author,"",[]); return None
    spots = []
    for p in places:
        c=find_coords(p)
        if c: spots.append({"name":p,"lat":c["lat"],"lng":c["lng"],"note":c["source"]})
    if not spots: log.warning("未匹配坐标"); mark_processed(conn,vid,title,author,"",[]); return None
    seen_pts=set(); unique=[]
    for s in spots:
        k=(round(s["lat"],4),round(s["lng"],4))
        if k not in seen_pts: seen_pts.add(k); unique.append(s)
    safe = re.sub(r'[\\/:*?"<>|#@!]','',title)[:80].strip('_ ')
    if not safe or not re.search(r'[\u4e00-\u9fff]',safe): safe=f"douyin_{vid}"
    gpx_path = write_gpx_file(safe, title, url, unique)
    log.info(f"✓ GPX: {gpx_path} ({len(unique)}途经点)")
    mark_processed(conn,vid,title,author,gpx_path,unique)
    if close: conn.close()
    return gpx_path

def import_openclaw_route_waypoints(conn=None, source_path: Path = OPENCLAW_ROUTE_WAYPOINTS_PATH):
    if not source_path.exists():
        log.warning(f"OpenClaw route output not found: {source_path}")
        return {"ok": False, "imported": 0, "skipped": 0, "error": "openclaw route output not found"}

    payload = json.loads(source_path.read_text(encoding="utf-8"))
    items = payload.get("items", []) if isinstance(payload, dict) else []
    close = False
    if conn is None:
        conn = init_db()
        close = True

    imported = 0
    skipped = 0
    for item in items:
        if not isinstance(item, dict):
            skipped += 1
            continue
        if item.get("qualification_status") != "qualified":
            skipped += 1
            continue
        navigation = item.get("navigation") if isinstance(item.get("navigation"), dict) else {}
        raw_waypoints = navigation.get("waypoints", []) if isinstance(navigation.get("waypoints"), list) else []
        spots = []
        for point in raw_waypoints:
            if not isinstance(point, dict):
                continue
            lat = point.get("lat")
            lng = point.get("lng")
            name = str(point.get("name") or "").strip()
            if name and lat not in {None, ""} and lng not in {None, ""}:
                spots.append({"name": name, "lat": float(lat), "lng": float(lng), "note": point.get("source") or "openclaw"})
        if len(spots) < 2:
            skipped += 1
            continue

        route_slug = str(item.get("route_slug") or "route").strip()
        route_title = str(item.get("route_title") or route_slug).strip()
        reference_url = ((item.get("source") or {}).get("reference_url") if isinstance(item.get("source"), dict) else "") or "https://www.douyin.com/"
        gpx_path = write_gpx_file(f"openclaw_{route_slug}", route_title, reference_url, spots)
        upsert_route_record(conn, item, gpx_path, spots)
        imported += 1

    if close:
        conn.close()
    return {"ok": True, "imported": imported, "skipped": skipped, "source_path": str(source_path)}

def batch_process(keywords, max_results):
    conn = init_db()
    for keyword in keywords:
        results = search_douyin(keyword, max_results=max_results)
        processed_count = 0
        for item in results:
            if process_video(item["url"], conn):
                processed_count += 1
        conn.execute(
            "INSERT INTO search_log(keyword, searched_at, found_count, processed_count) VALUES (?,?,?,?)",
            (keyword, datetime.now(timezone.utc).isoformat(), len(results), processed_count),
        )
        conn.commit()
    conn.close()

def export_gpx_to_candidates():
    """将已处理的途经点导出为 normalized/candidate_spots.json 格式"""
    conn=init_db()
    cur=conn.execute("SELECT video_id,title,author,spots_json FROM processed_videos WHERE spots_json!=''")
    rows=cur.fetchall(); conn.close()
    if not rows: log.info("没有数据可导出"); return
    spot_names=set(); candidates=[]
    for r in rows:
        vid,title,author,spots_json=r
        try: spots=json.loads(spots_json)
        except: continue
        for s in spots:
            name=s.get("name","")
            if name and name not in spot_names:
                spot_names.add(name)
                candidates.append({
                    "source":"douyin-gpx", "video_id":vid, "video_title":title or "",
                    "data":{
                        "name":name, "coordinates":{"lat":s["lat"],"lng":s["lng"]},
                        "spot_type":"scenic-spot", "city":"(待确定)", "region":"辽宁",
                        "summary":f"从抖音视频\"{title}\"提取", "confidence_score":"B",
                        "sources":[{"type":"douyin-video","url":f"https://www.douyin.com/video/{vid}"}]
                    }
                })
    out_path=PROJECT_ROOT/"data"/"raw"/"gpx_candidate_spots.json"
    with open(out_path,"w",encoding="utf-8") as f: json.dump(candidates,f,ensure_ascii=False,indent=2)
    log.info(f"导出 {len(candidates)} 个候选点到 {out_path}")
    # 也写入 normalized 目录，方便后续管线
    norm_path=PROJECT_ROOT/"data"/"normalized"/"candidate_spots.json"
    with open(norm_path,"w",encoding="utf-8") as f: json.dump(candidates,f,ensure_ascii=False,indent=2)
    log.info(f"同步到 {norm_path}")

# ====================================================================
# 主入口
# ====================================================================
def main():
    ap=argparse.ArgumentParser(description="抖音摩旅路线提取 & GPX (moto版)")
    ap.add_argument("keyword",nargs="?",help="搜索关键词")
    ap.add_argument("--url",help="直接处理指定视频")
    ap.add_argument("--batch",help="从文件读取关键词")
    ap.add_argument("--list-db",action="store_true",help="查看已处理视频")
    ap.add_argument("--reset-db",action="store_true",help="重置数据库")
    ap.add_argument("--add-spot",help="扩充坐标: '地名,纬度,经度'")
    ap.add_argument("--export-spots",action="store_true",help="导出途经点为候选点")
    ap.add_argument("--import-openclaw-routes", action="store_true", help="将 OpenClaw 路线结果导入 GPX 数据库")
    ap.add_argument("--max",type=int,default=5,help="每关键词最多处理视频数")
    args=ap.parse_args()
    if args.add_spot:
        parts=[x.strip() for x in args.add_spot.split(",")]
        if len(parts)<3: print("格式: --add-spot '地名,纬度,经度'"); return
        name,lat,lng=parts[0],float(parts[1]),float(parts[2])
        spots={}
        if SPOTS_USER_PATH.exists():
            with open(SPOTS_USER_PATH,"r",encoding="utf-8") as f: spots=json.load(f)
        spots[name]=[lat,lng]
        with open(SPOTS_USER_PATH,"w",encoding="utf-8") as f: json.dump(spots,f,ensure_ascii=False,indent=2)
        print(f"已添加: {name} ({lat},{lng})"); return
    if args.reset_db:
        if DB_PATH.exists(): DB_PATH.unlink(); print("数据库已重置")
        else: print("数据库不存在"); return
    if args.list_db:
        conn=init_db()
        cur=conn.execute("SELECT video_id,title,record_type,processed_at,spots_count,gpx_path FROM processed_videos ORDER BY processed_at DESC LIMIT 50")
        rows=cur.fetchall(); conn.close()
        if not rows: print("数据库为空"); return
        print(f"{'记录ID':>20} {'标题':<30} {'类型':<8} {'途经点':>5} {'处理时间':<20}"); print("-"*96)
        for r in rows: print(f"{r[0]:>20} {(r[1] or '')[:28]:<30} {(r[2] or ''):<8} {r[4]:>5} {r[3][:19]:<20}")
        print(f"\n共{len(rows)}条记录"); return
    if args.export_spots: export_gpx_to_candidates(); return
    if args.import_openclaw_routes:
        result = import_openclaw_route_waypoints()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    if args.url or args.keyword or args.batch:
        from scripts.gpx_generator import batch_process
        if args.batch:
            with open(args.batch,"r",encoding="utf-8") as f: kws=[l.strip() for l in f if l.strip()]
        elif args.url:
            url=args.url
            m=re.search(r'modal_id=(\d{19})',url)
            if m: url=f"https://www.douyin.com/video/{m.group(1)}"
            conn=init_db(); process_video(url,conn); conn.close(); return
        else: kws=[args.keyword]
        batch_process(kws,args.max)

if __name__=="__main__":
    main()
