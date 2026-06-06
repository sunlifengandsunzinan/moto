import json, os, math, random, io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# ===== 初始化Pipeline状态 =====
state = {
    "processed_note_ids": [],
    "last_batch_time": None,
    "total_notes_seen": 0,
    "batches_processed": 0,
    "keywords_done": []
}
out_dir = r'D:\摩旅数据采集'
os.makedirs(out_dir, exist_ok=True)
with open(os.path.join(out_dir, 'pipeline_state.json'), 'w', encoding='utf-8') as f:
    json.dump(state, f, ensure_ascii=False, indent=2)
print('Pipeline 已初始化')

# ===== 坐标库 =====
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
    "七星山": (123.480, 42.100), "七星湖": (122.900, 42.080),
    "枫林谷": (125.140, 41.210), "虎谷峡": (125.290, 41.240),
    "大梨树": (124.080, 40.810), "回龙湖": (125.240, 41.210),
    "鲅鱼圈": (122.130, 40.230), "仙人岛": (122.010, 40.080),
    "金州": (121.730, 39.110), "旅顺": (121.270, 38.820),
}
with open(os.path.join(out_dir, 'liaoning_coords_reference.json'), 'w', encoding='utf-8') as f:
    json.dump(known_coords, f, ensure_ascii=False, indent=2)
print(f'坐标库: {len(known_coords)} 个点已保存')

# ===== 读取未处理笔记 =====
jsonl = r'C:\Users\Administrator\.openclaw\workspace\MediaCrawler\data\xhs\jsonl\search_contents_2026-06-02.jsonl'
comments_file = r'C:\Users\Administrator\.openclaw\workspace\MediaCrawler\data\xhs\jsonl\search_comments_2026-06-02.jsonl'

# 加载评论
comments_by_note = {}
if os.path.exists(comments_file):
    with open(comments_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line: continue
            try:
                c = json.loads(line)
                nid = c.get('note_id', '')
                text = c.get('content', c.get('comment_text', ''))
                if nid and text:
                    if nid not in comments_by_note:
                        comments_by_note[nid] = []
                    comments_by_note[nid].append(text)
            except:
                pass
print(f'加载评论: {len(comments_by_note)} 个笔记有评论')

# 读取所有笔记
notes = []
with open(jsonl, 'r', encoding='utf-8') as f:
    for line in f:
        line = line.strip()
        if not line: continue
        try:
            d = json.loads(line)
            notes.append(d)
        except:
            pass

print(f'总笔记: {len(notes)} 条')

# ===== 自动分析函数 =====
def haversine(lng1, lat1, lng2, lat2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

def extract_waypoints(title, desc):
    text = f"{title} {desc}".replace("#", " ")
    for t in text.split('#'):
        text += ' ' + t
    found = []
    used_names = set()
    for name in sorted(known_coords.keys(), key=len, reverse=True):
        if name in text and name not in used_names:
            found.append(name)
            used_names.add(name)
    return found[:8]

def analyze_note(note, comments_text):
    title = note.get('title', '')
    desc = note.get('desc', '')
    waypoints = extract_waypoints(title, desc)
    
    # 计算距离
    total_km = 0
    segments = []
    coords = {}
    for wp in waypoints:
        if wp in known_coords:
            coords[wp] = known_coords[wp]
    
    route_order = []
    for wp in waypoints:
        if wp in coords:
            route_order.append(wp)
    
    if len(route_order) >= 2:
        for i in range(len(route_order) - 1):
            a = coords[route_order[i]]
            b = coords[route_order[i+1]]
            km = round(haversine(a[1], a[0], b[1], b[0]), 1)
            segments.append(f"{route_order[i]}→{route_order[i+1]}: {km}km")
            total_km += km
        estimated = round(total_km * 1.3, 1)
    else:
        estimated = 0
    
    likes = note.get('liked_count', '0')
    try:
        likes_int = int(float(str(likes).replace('万','')) * 10000) if '万' in str(likes) else int(likes)
    except:
        likes_int = 0
    try:
        collects_int = int(note.get('collected_count', 0))
    except:
        collects_int = 0
    try:
        comments_int = int(note.get('comment_count', 0))
    except:
        comments_int = 0
    try:
        shares_int = int(note.get('share_count', 0))
    except:
        shares_int = 0
    
    image_list = note.get('image_list', '')
    cover_images = image_list.split(',') if image_list else []
    
    result = {
        "note_id": note.get('note_id', ''),
        "platform": "小红书",
        "basic_info": {
            "title": title[:80],
            "media_type": note.get('type', 'normal'),
            "author": note.get('nickname', ''),
            "publish_time": note.get('time', ''),
            "source_keyword": note.get('source_keyword', ''),
            "cover_images": cover_images[:5],
            "cover_image_count": len(cover_images),
            "video_url": note.get('video_url', ''),
            "description": desc[:200],
            "tag_list": note.get('tag_list', '')
        },
        "engagement": {
            "likes": likes_int,
            "collects": collects_int,
            "comments": comments_int,
            "shares": shares_int
        },
        "route_analysis": {
            "has_route_info": len(waypoints) >= 2,
            "waypoint_names": waypoints,
            "waypoint_coords": {k: list(v) for k, v in coords.items()},
            "route_order": route_order,
            "distance_km": round(total_km, 1),
            "estimated_motorcycle_km": estimated,
            "segments": segments,
            "estimated_days": "1天" if estimated < 300 else "2天" if estimated < 600 else "3天+"
        },
        "data_source": {
            "source_keyword": note.get('source_keyword', ''),
            "crawl_time": "2026-06-02",
            "note_url": note.get('note_url', '')
        }
    }
    return result

# ===== 批量分析 =====
results = []
for i, note in enumerate(notes):
    nid = note.get('note_id', '')
    title = note.get('title', '')
    
    # 收集该笔记的评论摘要
    note_comments = comments_by_note.get(nid, [])
    comment_text = ' '.join(note_comments[:10])
    
    r = analyze_note(note, comment_text)
    
    # 附上最有代表性的3条评论
    r['sample_comments'] = note_comments[:3]
    
    results.append(r)
    
    if (i+1) % 20 == 0:
        print(f'  分析进度: {i+1}/{len(notes)}')

# 保存全量分析
output = os.path.join(out_dir, '辽宁摩旅路线_全量分析.json')
with open(output, 'w', encoding='utf-8') as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print(f'\n分析完成!')
print(f'总分析: {len(results)} 条')
print(f'有路线信息: {sum(1 for r in results if r["route_analysis"]["has_route_info"])} 条')
print(f'保存到: {output}')
print(f'大小: {round(os.path.getsize(output)/1024, 1)} KB')

# 更新pipeline状态
state["processed_note_ids"] = [r["note_id"] for r in results]
state["total_notes_seen"] = len(results)
state["batches_processed"] = 1
state["last_batch_time"] = "2026-06-03 00:03"
with open(os.path.join(out_dir, 'pipeline_state.json'), 'w', encoding='utf-8') as f:
    json.dump(state, f, ensure_ascii=False, indent=2)
print(f'\nPipeline状态已更新: 已处理 {len(state["processed_note_ids"])} 条')
