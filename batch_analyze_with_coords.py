"""Batch analyze all Liaoning motorcycle route notes with coordinate and distance"""
import json, sys, io, os, math
from datetime import datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# ===== Coordinate Library (GCJ-02) =====
known_coords = {
    "沈阳": (123.431, 41.808),
    "大连": (121.615, 38.914),
    "丹东": (124.356, 40.000),
    "本溪": (123.766, 41.330),
    "桓仁": (125.360, 41.270),
    "庄河": (122.980, 39.690),
    "盖州": (122.350, 40.410),
    "绿江村": (125.380, 40.720),
    "崔桂线": (122.850, 39.720),
    "本桓公路": (124.120, 41.300),
    "锦州": (121.130, 41.100),
    "盘锦": (121.970, 40.720),
    "鞍山": (122.980, 41.120),
    "抚顺": (123.930, 41.880),
    "营口": (122.230, 40.670),
    "葫芦岛": (120.830, 40.720),
    "大连滨海路": (121.620, 38.880),
    "滨江公路": (124.350, 40.050),
    "红海滩": (121.970, 40.720),
    "笔架山": (121.120, 40.850),
    "冰峪沟": (122.940, 39.870),
    "步云山": (122.540, 39.870),
    "青山沟": (124.780, 40.880),
    "凤凰山": (124.110, 40.420),
    "宽甸": (124.780, 40.730),
    "辽河": (122.000, 41.200),
    "鸭绿江": (124.300, 39.900),
    "老秃顶子": (125.020, 41.320),
    "天桥沟": (124.780, 40.980),
    "关门山": (124.020, 41.160),
    "本溪水洞": (124.080, 41.320),
}

def haversine(lng1, lat1, lng2, lat2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

def calc_distance(coords_list):
    """list of (lng, lat) tuples"""
    total = 0
    segments = []
    for i in range(len(coords_list) - 1):
        d = haversine(coords_list[i][0], coords_list[i][1], coords_list[i+1][0], coords_list[i+1][1])
        total += d
        segments.append(d)
    return total, segments

def parse_count(s):
    s = str(s).strip()
    try:
        if '万' in s:
            return int(float(s.replace('万', '')) * 10000)
        return int(s)
    except:
        return 0

def extract_waypoints(title, desc, comments_text):
    """Extract place/road names from text that match known coords"""
    text = (title + ' ' + desc + ' ' + comments_text).replace('#', ' ')
    found = []
    for name in sorted(known_coords.keys(), key=len, reverse=True):
        if name in text:
            found.append(name)
            text = text.replace(name, '')
    return found[:8]  # max 8 waypoints

def match_route_order(waypoints):
    """Try to put waypoints in a sensible driving order"""
    if not waypoints:
        return waypoints
    ordered = []
    remaining = list(waypoints)
    # Start with the most likely start city
    start_priorities = {"沈阳": 0, "大连": 1, "丹东": 2, "本溪": 3}
    remaining.sort(key=lambda x: start_priorities.get(x, 99))
    ordered = remaining
    return ordered

# ===== Load data =====
ln_keywords = ['辽宁摩旅路线','辽宁自驾游路线推荐','辽宁骑行路线','大连摩旅','沈阳周边自驾游',
               '丹东骑行路线','本桓公路自驾','辽宁沿海公路自驾']

data_path = r"C:\Users\Administrator\.openclaw\workspace\MediaCrawler\data\xhs\jsonl\search_contents_2026-06-02.jsonl"
comments_path = r"C:\Users\Administrator\.openclaw\workspace\MediaCrawler\data\xhs\jsonl\search_comments_2026-06-02.jsonl"

# Load comments
comments_by_note = {}
with open(comments_path, "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line: continue
        c = json.loads(line)
        nid = c.get("note_id", "")
        if nid not in comments_by_note:
            comments_by_note[nid] = []
        comments_by_note[nid].append(c)

# Load notes (all Liaoning)
ln_notes = []
with open(data_path, "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line: continue
        d = json.loads(line)
        if d.get("source_keyword", "") in ln_keywords:
            ln_notes.append(d)

print(f"📊 共 {len(ln_notes)} 条辽宁笔记待分析")
print(f"📊 共 {sum(len(comments_by_note.get(n['note_id'],[])) for n in ln_notes)} 条相关评论")

# ===== Process each note =====
results = []
has_route_count = 0
liaoning_count = 0

for n in ln_notes:
    nid = n["note_id"]
    cmts = comments_by_note.get(nid, [])
    all_comment_text = ' '.join(c.get("content", "") for c in cmts)

    # Extract waypoints
    waypoints = extract_waypoints(n.get("title",""), n.get("desc",""), all_comment_text)
    waypoints = match_route_order(waypoints)

    # Get coords
    coords = {}
    for wp in waypoints:
        if wp in known_coords:
            coords[wp] = {"lng": known_coords[wp][0], "lat": known_coords[wp][1]}

    # Calc distance
    total_km = 0
    segments_info = []
    route_coords = []
    for wp in waypoints:
        if wp in known_coords:
            route_coords.append(known_coords[wp])

    if len(route_coords) >= 2:
        total, segs = calc_distance(route_coords)
        total_km = round(total, 1)
        for i in range(len(segs)):
            segments_info.append(f"{waypoints[i]}→{waypoints[i+1]}: {round(segs[i], 1)}km")

    # Route type estimation
    route_type = "未识别"
    ## Get regions from waypoints
    regions = []
    for wp in waypoints:
        cities_map = {"沈阳":"沈阳","大连":"大连","丹东":"丹东","本溪":"本溪","锦州":"锦州","鞍山":"鞍山",
                      "抚顺":"抚顺","营口":"营口","葫芦岛":"葫芦岛","庄河":"大连","盖州":"营口",
                      "桓仁":"本溪","宽甸":"丹东","绿江村":"丹东"}
        if wp in cities_map:
            regions.append(cities_map[wp])

    unique_regions = list(set(regions))
    if len(unique_regions) >= 3 and total_km > 200:
        route_type = "跨市长途"
    elif len(unique_regions) >= 2 and total_km > 50:
        route_type = "跨区短途"
    elif len(waypoints) >= 2 and total_km < 50:
        route_type = "城市周边"
    
    # Check is_liaoning
    is_ln = any(
        kw in n.get("source_keyword","") or 
        name in n.get("title","") + n.get("desc","")
        for kw in ln_keywords[:5]
        for name in ["辽宁","沈阳","大连","丹东","本溪","锦州","盘锦","鞍山","抚顺","营口","葫芦岛","庄河","盖州","桓仁","宽甸","绿江村"]
    )
    if is_ln:
        liaoning_count += 1

    has_route = len(waypoints) >= 2 or total_km > 20
    if has_route:
        has_route_count += 1

    # Build sample_comments
    sample_cmts = []
    for c in cmts[:5]:
        ts = datetime.fromtimestamp(c["create_time"]/1000).strftime("%Y-%m-%d") if c.get("create_time") else ""
        sample_cmts.append({
            "user": c["nickname"],
            "ip_location": c.get("ip_location", ""),
            "content": c["content"],
            "time": ts,
            "likes": parse_count(c.get("like_count", "0"))
        })

    # Key comment insights
    insights = []
    for c in cmts[:10]:
        txt = c.get("content", "")
        if len(txt) > 4 and parse_count(c.get("like_count", 0)) >= 2:
            insights.append(f"{c['nickname']}（{c.get('ip_location','')}）: {txt}")

    result = {
        "note_id": nid,
        "platform": "小红书",
        "basic_info": {
            "title": n.get("title", ""),
            "media_type": n.get("type", ""),
            "author": n.get("nickname", ""),
            "publish_time": datetime.fromtimestamp(n["time"]/1000).strftime("%Y-%m-%d") if n.get("time") else "",
            "description": n.get("desc", "")[:200],
            "source_keyword": n.get("source_keyword", ""),
            "url": n.get("note_url", "")
        },
        "engagement": {
            "likes": parse_count(n.get("liked_count", "0")),
            "collects": parse_count(n.get("collected_count", "0")),
            "comments": parse_count(n.get("comment_count", "0")),
            "shares": parse_count(n.get("share_count", "0"))
        },
        "route_analysis": {
            "has_route_info": has_route,
            "route_type": route_type,
            "waypoint_names": waypoints,
            "waypoint_coords": coords,
            "route_order": waypoints,
            "distance_km": total_km,
            "segments": segments_info,
            "estimated_motorcycle_km": round(total_km * 1.3) if total_km > 0 else 0,
            "mentions": {
                "roads": [],
                "cities_or_regions": unique_regions,
                "scenic_spots": []
            }
        },
        "qualification_assessment": {
            "is_liaoning_related": is_ln,
            "has_route_info": has_route,
            "confidence": "high" if is_ln and has_route else "medium" if is_ln else "low",
            "notes": ""
        },
        "sample_comments": sample_cmts[:5],
        "key_comment_insights": insights[:5]
    }
    results.append(result)

# ===== Summary stats =====
print(f"\n{'='*60}")
print(f"📊 分析汇总")
print(f"{'='*60}")
print(f"  总笔记数: {len(results)}")
print(f"  辽宁相关: {liaoning_count}")
print(f"  含路线信息: {has_route_count}")
print(f"  路线类型分布:")
type_counts = {}
for r in results:
    t = r["route_analysis"]["route_type"]
    type_counts[t] = type_counts.get(t, 0) + 1
for t, c in sorted(type_counts.items(), key=lambda x: -x[1]):
    print(f"    {t}: {c}")

# ===== Save =====
output_dir = r"D:\摩旅数据采集"
os.makedirs(output_dir, exist_ok=True)

full_path = os.path.join(output_dir, "辽宁摩旅路线_全量分析.json")
with open(full_path, "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print(f"\n✅ 全量分析已保存: {full_path}")
print(f"   文件大小: {os.path.getsize(full_path)/1024:.0f} KB")
