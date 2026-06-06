"""
辽宁摩旅数据 Pipeline
- 记录已处理/未处理状态（基于 note_id）
- 防封控制：随机延迟、限速
"""
import json, os, time, random, math, io, sys
from datetime import datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

STATE_FILE = r"D:\摩旅数据采集\pipeline_state.json"
LN_JSONL = r"C:\Users\Administrator\.openclaw\workspace\MediaCrawler\data\xhs\jsonl\search_contents_2026-06-02.jsonl"
COMMENTS_JSONL = r"C:\Users\Administrator\.openclaw\workspace\MediaCrawler\data\xhs\jsonl\search_comments_2026-06-02.jsonl"
OUTPUT_DIR = r"D:\摩旅数据采集"

def load_state():
    """加载处理状态"""
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "processed_note_ids": [],
        "last_batch_time": None,
        "total_notes_seen": 0,
        "batches_processed": 0,
        "keywords_done": []
    }

def save_state(state):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def get_unprocessed_notes(state, max_batch=15):
    """获取未处理的辽宁笔记"""
    ln_keywords = [
        '辽宁省内摩旅路线','辽宁省内自驾游路线','小众辽宁省内摩托路线',
        '辽宁骑行路线推荐','辽宁摩旅攻略','沈阳周边摩旅','大连周边骑行',
        '丹东边境公路自驾','本溪桓仁自驾路线','辽宁最美自驾公路'
    ]
    
    processed = set(state["processed_note_ids"])
    
    unprocessed = []
    if os.path.exists(LN_JSONL):
        with open(LN_JSONL, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line: continue
                try:
                    d = json.loads(line)
                    kw = d.get("source_keyword", "")
                    nid = d.get("note_id", "")
                    if kw in ln_keywords and nid not in processed:
                        unprocessed.append(d)
                except:
                    continue
    
    # 随机打乱（防封检测模式）
    random.shuffle(unprocessed)
    return unprocessed[:max_batch]

def random_delay():
    """随机延迟，防反爬"""
    delay = random.uniform(2, 8)
    time.sleep(delay)
    return delay

# ====== 坐标库 ======
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
    "青山沟": (124.780, 40.880), "凤凰山": (124.110, 40.420),
    "宽甸": (124.780, 40.730), "鸭绿江": (124.300, 39.900),
}

def extract_waypoints(title, desc, comments_text):
    text = f"{title} {desc} {comments_text}".replace("#", " ")
    found = []
    for name in sorted(known_coords.keys(), key=len, reverse=True):
        if name in text:
            found.append(name)
            text = text.replace(name, "")
    return found[:8]

def haversine(lng1, lat1, lng2, lat2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

def parse_count(s):
    s = str(s).strip()
    try:
        if "万" in s:
            return int(float(s.replace("万", "")) * 10000)
        return int(s)
    except:
        return 0

if __name__ == "__main__":
    state = load_state()
    batch = get_unprocessed_notes(state)
    print(f"未处理: {len(batch)} 条（本轮批次）")
    for n in batch:
        print(f"  {n.get('source_keyword','')} | {n.get('title','')[:30]}")
