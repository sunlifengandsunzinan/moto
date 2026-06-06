import json, os, sys, io, subprocess
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

infile = r'D:\摩旅数据采集\辽宁摩旅路线_全量分析.json'
outfile = r'D:\摩旅数据采集\辽宁摩旅路线_精选排名_v2.json'

with open(infile, 'r', encoding='utf-8') as f:
    data = json.load(f)

print(f'读取 {len(data)} 条数据')

# 按rules评分
def auto_score(item):
    ba = item.get('basic_info', {})
    ra = item.get('route_analysis', {})
    eg = item.get('engagement', {})
    
    title = (ba.get('title', '') + ' ' + ba.get('description', '')).lower()
    
    # 1. 路线相关性 (3分)
    liao_keywords = ['辽宁', '沈阳', '大连', '丹东', '本溪', '锦州', '鞍山', '抚顺', 
                     '营口', '盘锦', '葫芦岛', '铁岭', '朝阳', '阜新', '辽阳',
                     '摩旅', '骑行', '自驾', '摩托', '机车', '公路', '路线', '风景',
                     '攻略', '环海', '边境', '山路', '帅']
    relevant = sum(1 for kw in liao_keywords if kw in title)
    route_score = min(3, relevant * 0.5)
    
    # 2. 里程合理性 (2分)
    km = ra.get('distance_km', 0)
    engery_score = 0
    if 50 < km < 600:
        engery_score = 2
    elif km > 0:
        engery_score = 1
    
    # 3. 互动热度 (2分)
    likes = eg.get('likes', 0)
    collects = eg.get('collects', 0)
    comments = eg.get('comments', 0)
    total_interact = likes + collects * 2 + comments * 3
    if total_interact > 5000:
        interact_score = 2
    elif total_interact > 2000:
        interact_score = 1.5
    elif total_interact > 500:
        interact_score = 1
    else:
        interact_score = 0.5
    
    # 4. 内容信息量 (3分)
    wp = ra.get('waypoint_names', [])
    route_order = ra.get('route_order', [])
    segments = ra.get('segments', [])
    desc = ba.get('description', '')
    info_score = 0
    if len(wp) >= 3: info_score += 1.5
    elif len(wp) >= 1: info_score += 0.5
    if len(segments) >= 2: info_score += 1
    if len(desc) > 100: info_score += 0.5
    
    total = route_score + engery_score + interact_score + info_score
    return round(total, 1)

# 评分
for item in data:
    item['_score'] = auto_score(item)

# 排序取前15 让qwen再精选
sorted_data = sorted(data, key=lambda x: x['_score'], reverse=True)
top_n = sorted_data[:15]

print(f'评分完成，TOP15 分数范围: {top_n[-1]["_score"]:.1f} - {top_n[0]["_score"]:.1f}')

# 调用Ollama qwen2.5:7b 逐条点评
def call_ollama(prompt, model="qwen2.5:7b"):
    result = subprocess.run(
        ['ollama', 'run', model, prompt],
        capture_output=True, text=True,
        timeout=120,
        encoding='utf-8', errors='replace'
    )
    return result.stdout.strip()

def generate_review(item):
    ba = item['basic_info']
    ra = item['route_analysis']
    eg = item['engagement']
    
    title = ba.get('title', '无')
    route = ' → '.join(ra.get('route_order', [])) or '无'
    km = ra.get('distance_km', 0)
    likes = eg.get('likes', 0)
    collects = eg.get('collects', 0)
    comments = eg.get('comments', 0)
    score = item['_score']
    
    prompt = f"""请用中文对以下辽宁摩旅路线进行简评（30字以内）+ 骑行建议（40字以内）。

路线：{title}
途经点：{route}
里程：{km}km
热度：{likes}赞/{collects}收藏/{comments}评论
系统评分：{score}/10

格式：评分|评语|骑行建议"""
    
    try:
        resp = call_ollama(prompt)
        parts = resp.split('|')
        return {
            "score": score,
            "rating": "推荐" if score >= 6 else "还行" if score >= 4 else "一般",
            "comment": parts[1].strip() if len(parts) > 1 else "",
            "riding_advice": parts[2].strip() if len(parts) > 2 else ""
        }
    except Exception as e:
        print(f'  Ollama调用失败: {e}')
        return {"score": score, "rating": "推荐", "comment": "", "riding_advice": ""}

reviews = []
for i, item in enumerate(top_n):
    print(f'Ollama点评 {i+1}/15: {item["basic_info"]["title"][:30]}...')
    rev = generate_review(item)
    item['ollama_review'] = rev
    reviews.append({
        "note_id": item.get('note_id', ''),
        "basic_info": item.get('basic_info', {}),
        "engagement": item.get('engagement', {}),
        "route_analysis": item.get('route_analysis', {}),
        "score": item['_score'],
        "ollama_review": rev
    })
    if i < 4:
        print(f'  → {rev["comment"][:50]}')
    if i < 10:  # 只取前10写入精选
        pass

# 取前10
final_top10 = reviews[:10]

output = {
    "batch": 1,
    "total_analyzed": len(data),
    "selected_count": 10,
    "analysis_time": "2026-06-03 00:03",
    "routes": final_top10
}

with open(outfile, 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f'\n精选TOP10 已保存到 {outfile}')
print(f'文件大小: {round(os.path.getsize(outfile)/1024, 1)} KB')
print('\n====== TOP5 摘要 ======')
for i, r in enumerate(final_top10[:5]):
    ba = r['basic_info']
    ra = r['route_analysis']
    rv = r['ollama_review']
    print(f'{i+1}. [{rv["score"]}] {ba["title"][:35]}')
    print(f'   途经: {ra["route_order"]} | {ra["distance_km"]}km')
    if rv.get('comment'):
        print(f'   点评: {rv["comment"][:50]}')
    print()
