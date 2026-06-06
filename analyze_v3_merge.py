#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""辽宁摩旅路线 - 全量合并分析 v3
合并旧60条 + 新252条 → 提取路线信息 → 硬逻辑筛选 → qwen2.5:7b评分 → Top10
"""

import json, os, sys, time, requests, re
from collections import Counter

os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.stdout.reconfigure(encoding='utf-8')

# 辽宁主要城市坐标参考
CITY_COORDS = {
    "沈阳": [123.431, 41.808], "大连": [121.615, 38.914], "鞍山": [122.998, 41.108],
    "抚顺": [123.957, 41.881], "本溪": [123.766, 41.33], "丹东": [124.356, 40.0],
    "锦州": [121.13, 41.1], "营口": [122.23, 40.67], "阜新": [121.67, 42.02],
    "辽阳": [123.17, 41.27], "盘锦": [121.97, 40.72], "铁岭": [123.84, 42.29],
    "朝阳": [120.45, 41.58], "葫芦岛": [120.84, 40.71], "兴城": [120.69, 40.62],
    "盖州": [122.35, 40.4], "庄河": [122.97, 39.68], "宽甸": [124.78, 40.73],
    "桓仁": [125.36, 41.27], "彰武": [122.54, 42.39], "喀左": [119.74, 41.13],
    "建平": [119.64, 41.4], "北镇": [121.78, 41.59], "凌源": [119.4, 41.25],
    "青山沟": [124.78, 40.88], "绿江村": [125.38, 40.72], "虎谷峡": [125.46, 41.26],
    "回龙湖": [125.41, 41.21], "七星山": [123.47, 42.03], "七星湖": [123.48, 42.02],
    "辽河": [123.0, 41.5], "红海滩": [121.97, 40.87], "笔架山": [121.11, 40.83],
    "鲅鱼圈": [122.12, 40.26], "旅顺": [121.26, 38.82], "冰峪沟": [122.97, 39.95],
    "天门山": [122.91, 39.73], "大黑山": [121.81, 39.06], "老帽山": [122.38, 39.79],
    "排石": [121.44, 39.7], "瓦房店": [122.0, 39.63], "普兰店": [121.97, 39.39],
    "仙浴湾": [121.53, 39.57], "星海广场": [121.59, 38.88], "滨海路": [121.62, 38.87],
    "回龙岗": [123.51, 41.8], "关门山": [124.11, 41.21], "老秃顶": [125.0, 41.33],
    "五女山": [125.41, 41.3], "望天洞": [125.33, 40.79], "青山湖": [124.75, 40.86],
    "黄椅山": [124.78, 40.73], "飞瀑涧": [124.78, 40.88], "抚远": [134.29, 48.36],
    "黑瞎子岛": [134.82, 48.37]
}

LIAONING_CITIES = set(CITY_COORDS.keys())

OLLAMA_URL = "http://localhost:11434/api/generate"
INPUT_OLD = r"D:\摩旅数据采集\辽宁摩旅路线_全量分析.json"
INPUT_NEW = r"C:\Users\Administrator\.openclaw\workspace\MediaCrawler\data\xhs\jsonl\search_contents_2026-06-03.jsonl"
OUTPUT = r"D:\摩旅数据采集\辽宁摩旅路线_精选排名_v3.json"

def load_old_data():
    with open(INPUT_OLD, "r", encoding="utf-8") as f:
        return json.load(f)

def load_new_data():
    with open(INPUT_NEW, "r", encoding="utf-8") as f:
        lines = f.readlines()
    seen = set()
    unique = []
    for line in lines:
        n = json.loads(line)
        nid = n.get('note_id', '')
        if nid not in seen:
            seen.add(nid)
            unique.append(n)
    return unique

def extract_waypoints(title, desc, tag_list):
    """从标题/描述/标签中提取辽宁途经点"""
    text = f"{title} {desc} {tag_list}"
    found = []
    for city in sorted(LIAONING_CITIES, key=len, reverse=True):
        if city in text:
            found.append(city)
    return found

def guess_distance(waypoints):
    """根据途经点估算总里程"""
    if len(waypoints) < 2:
        return 0
    total = 0
    for i in range(len(waypoints) - 1):
        a = CITY_COORDS.get(waypoints[i])
        b = CITY_COORDS.get(waypoints[i+1])
        if a and b:
            # 简易经纬度距离估算
            lat_diff = (a[1] - b[1]) * 111
            lng_diff = (a[0] - b[0]) * 111 * 0.75
            total += (lat_diff**2 + lng_diff**2)**0.5
    return round(total, 1)

def is_liaoning_related(title, desc, tag_list, waypoints):
    """判断是否辽宁相关"""
    text = f"{title} {desc} {tag_list}"
    if waypoints:
        return True
    # 辽宁相关关键词
    keywords = ["辽宁", "沈阳", "大连", "鞍山", "本溪", "丹东", "锦州", "营口", "盘锦",
                 "辽河", "辽东", "辽西", "辽南", "渤海", "东北", "盛京", "奉天"]
    return any(k in text for k in keywords)

def is_moto_related(title, desc, tag_list):
    """判断是否摩旅/骑行相关"""
    text = f"{title} {desc} {tag_list}".lower()
    keywords = ["摩旅", "摩托车", "摩托", "骑行", "骑车", "机车", "压弯", "跑山", "巡航",
                "adv", "拉力", "复古车", "踏板", "摩托车旅", "摩托旅行", "环海骑行",
                "骑行路线", "摩托路线", "山路", "自驾"]
    return any(k in text for k in keywords)

def hard_filter(notes):
    """硬逻辑筛选"""
    filtered = []
    for n in notes:
        title = n.get('title', '') or n.get('display_title', '') or ''
        desc = n.get('desc', '') or n.get('description', '') or ''
        tag_list = n.get('tag_list', '') or ''
        
        # 提取途经点
        waypoints = extract_waypoints(title, desc, tag_list)
        distance = guess_distance(waypoints)
        
        # 互动量
        try:
            likes = int(str(n.get('liked_count', 0)).replace('+','').replace('万','0000'))
            collects = int(str(n.get('collected_count', 0)).replace('+','').replace('万','0000'))
            comments = int(str(n.get('comment_count', 0)).replace('+','').replace('万','0000'))
        except:
            likes, collects, comments = 0, 0, 0
        interact = likes + collects + comments
        
        # 判断
        if not is_liaoning_related(title, desc, tag_list, waypoints):
            continue
        if not is_moto_related(title, desc, tag_list):
            continue
        if len(waypoints) < 2:
            continue
        if distance < 10:
            continue
        if interact < 50:
            continue
        
        # 包装成统一格式
        entry = {
            "note_id": n.get('note_id', ''),
            "platform": "小红书",
            "basic_info": {
                "title": title,
                "author": n.get('nickname', '') or n.get('basic_info', {}).get('author', ''),
                "source_keyword": n.get('source_keyword', ''),
                "description": desc,
                "tag_list": tag_list,
                "cover_images": [],
                "video_url": n.get('video_url', '')
            },
            "engagement": {
                "likes": likes,
                "collects": collects,
                "comments": comments,
                "shares": int(str(n.get('share_count', 0)).replace('+','').replace('万','0000'))
            },
            "route_analysis": {
                "waypoint_names": waypoints,
                "distance_km": distance,
                "has_route_info": len(waypoints) >= 2
            },
            "data_source": {
                "source_keyword": n.get('source_keyword', ''),
                "crawl_time": "2026-06-03"
            }
        }
        entry["_interact"] = interact
        entry["_is_liaoning_ip"] = n.get('ip_location') == '辽宁'
        filtered.append(entry)
    
    # 按互动量排序取前30
    filtered.sort(key=lambda x: x["_interact"], reverse=True)
    return filtered[:30]

def ollama_review(entry):
    """调用 qwen2.5:7b 生成评语"""
    bi = entry["basic_info"]
    ra = entry["route_analysis"]
    eng = entry["engagement"]
    
    prompt = f"""你是一个专业的摩旅路线分析师。分析以下辽宁摩旅笔记的路线质量。

标题：{bi['title']}
描述：{bi['description'][:200]}
途经点：{ra['waypoint_names']}
里程：{ra['distance_km']}km
点赞：{eng['likes']}  收藏：{eng['collects']}  评论：{eng['comments']}

请给出：
1. 路线评分（1-10分）
   评分标准：路线相关性3分(是否真的涉及辽宁摩旅)+里程合理性2分(50-400km最佳)+热度2分+信息量3分(有无具体途经点、路况、骑行建议)
2. 一句话专业评语（30字内）
3. 骑行建议（车型推荐、路况提示等，50字内）

格式：
评分: X
评语: ...
建议: ..."""

    try:
        r = requests.post(OLLAMA_URL, json={
            "model": "qwen2.5:7b",
            "prompt": prompt,
            "stream": False,
            "options": {"num_predict": 300}
        }, timeout=120)
        if r.status_code == 200:
            return r.json().get("response", "")
        else:
            return f"ollama error: {r.status_code}"
    except Exception as e:
        return f"评分失败: {str(e)}"

def parse_score(text):
    m = re.search(r'评分:\s*(\d+(?:\.\d+)?)', text)
    if m:
        return float(m.group(1))
    return 5.0

def save_progress(results, total):
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump({
            "batch": 3,
            "status": "in_progress",
            "total_candidates": total,
            "scored": len(results),
            "routes": results
        }, f, ensure_ascii=False, indent=2)

def main():
    print("=" * 60)
    print("辽宁摩旅路线 全量合并分析 v3")
    print("=" * 60)
    
    # 加载数据
    print("[1/5] 加载旧数据...")
    old = load_old_data()
    old_ids = set(n.get('note_id') for n in old)
    print(f"  旧全量分析: {len(old)} 条 (含 {len(old_ids)} 个唯一note_id)")
    
    print("[2/5] 加载新爬数据...")
    new = load_new_data()
    print(f"  新数据去重后: {len(new)} 条")
    
    # 合并（旧数据有结构化 route_analysis 优先保留）
    print("[3/5] 合并+硬逻辑筛选...")
    # 先把旧数据中的注记map一下
    old_notes_map = {}
    for n in old:
        nid = n.get('note_id', '')
        if nid:
            old_notes_map[nid] = n
    
    # 转换新数据为标准格式，并标记哪些旧分析已有
    combined = []
    seen_ids = set()
    for n in old:
        nid = n.get('note_id', '')
        if nid not in seen_ids:
            # 给旧条目增加互动量字段（有些旧条目可能没有）
            combined.append(n)
            seen_ids.add(nid)
    
    # 补全新的笔记（不在旧分析中的）
    for n in new:
        nid = n.get('note_id', '')
        if nid not in seen_ids:
            seen_ids.add(nid)
            # 用新数据格式构建一个类似旧分析的条目
            title = n.get('title', '') or ''
            desc = n.get('desc', '') or ''
            tag = n.get('tag_list', '') or ''
            waypoints = extract_waypoints(title, desc, tag)
            dist = guess_distance(waypoints)
            
            try:
                likes = int(str(n.get('liked_count', 0)).replace('+','').replace('万','0000'))
                collects = int(str(n.get('collected_count', 0)).replace('+','').replace('万','0000'))
                comments = int(str(n.get('comment_count', 0)).replace('+','').replace('万','0000'))
            except:
                likes, collects, comments = 0, 0, 0
            
            entry = {
                "note_id": nid,
                "platform": "小红书",
                "basic_info": {
                    "title": title,
                    "author": n.get('nickname', ''),
                    "source_keyword": n.get('source_keyword', ''),
                    "description": desc,
                    "tag_list": tag,
                    "cover_images": [],
                    "video_url": n.get('video_url', '')
                },
                "engagement": {"likes": likes, "collects": collects, "comments": comments},
                "route_analysis": {
                    "waypoint_names": waypoints,
                    "distance_km": dist,
                    "has_route_info": len(waypoints) >= 2
                },
                "data_source": {"source_keyword": n.get('source_keyword', ''), "crawl_time": "2026-06-03"}
            }
            combined.append(entry)
    
    print(f"  合并后总计: {len(combined)} 条")
    
    # 硬逻辑筛选
    candidates = []
    for n in combined:
        ra = n.get("route_analysis", {})
        eng = n.get("engagement", {})
        bi = n.get("basic_info", {})
        
        title = bi.get("title", "")
        desc = bi.get("description", "")
        tag = bi.get("tag_list", "")
        
        waypoints = ra.get("waypoint_names", [])
        distance = ra.get("distance_km", 0) or 0
        likes = int(eng.get("likes", 0) or 0)
        collects = int(eng.get("collects", 0) or 0)
        comments = int(eng.get("comments", 0) or 0)
        interact = likes + collects + comments
        
        if not is_liaoning_related(title, desc, tag, waypoints):
            continue
        if not is_moto_related(title, desc, tag):
            continue
        if len(waypoints) < 2:
            continue
        if distance < 10 or distance > 2000:
            continue
        if interact < 50:
            continue
        
        n["_interact"] = interact
        candidates.append(n)
    
    candidates.sort(key=lambda x: x["_interact"], reverse=True)
    candidates = candidates[:30]
    print(f"  初筛合格: {len(candidates)} 条 (按互动取前30)")
    
    if not candidates:
        print("无候选条目")
        return
    
    # Ollama 评分
    print("[4/5] Ollama 逐条评分 (qwen2.5:7b)...")
    results = []
    for i, n in enumerate(candidates):
        bi = n["basic_info"]
        ra = n["route_analysis"]
        eng = n["engagement"]
        
        safe_title = bi.get('title','?')[:30].encode('utf-8', errors='replace').decode('utf-8', errors='replace')
        print(f"  [{i+1}/{len(candidates)}] {safe_title}... ", end="", flush=True)
        
        review = ollama_review(n)
        score = parse_score(review)
        print(f"评分 {score}")
        
        n["score"] = score
        n["ollama_review"] = {
            "score": score,
            "rating": "推荐" if score >= 7 else ("可参考" if score >= 5 else "一般"),
            "comment": review[:300],
            "riding_advice": ""
        }
        # 去掉内部字段
        if "_interact" in n:
            del n["_interact"]
        results.append(n)
        
        if (i + 1) % 5 == 0:
            save_progress(results, len(candidates))
            print(f"  -> 已保存中间进度 ({i+1}/{len(candidates)})")
    
    # 排序取Top10
    print("[5/5] 排序输出...")
    results.sort(key=lambda x: x.get("score", 0), reverse=True)
    
    # 去重（同一条笔记只保留最高分的）
    seen_titles = set()
    deduped = []
    for r in results:
        title_key = r.get("basic_info", {}).get("title", "")[:20]
        if title_key not in seen_titles:
            seen_titles.add(title_key)
            deduped.append(r)
    
    top10 = deduped[:10]
    
    output = {
        "batch": 3,
        "total_merged": len(combined),
        "total_analyzed": len(results),
        "candidates": len(candidates),
        "selected_count": len(top10),
        "analysis_time": time.strftime("%Y-%m-%d %H:%M"),
        "_notes": {
            "old_data_count": len(old),
            "new_data_count": len(new),
            "hard_filter_pass": len(candidates),
            "ollama_scored": len(results),
            "deduped_to": len(deduped)
        },
        "routes": top10
    }
    
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f"\n{'='*60}")
    print(f"完成！保存到 {OUTPUT}")
    print(f"{'='*60}")
    for i, r in enumerate(top10):
        bi = r.get("basic_info", {})
        ra = r.get("route_analysis", {})
        score = r.get("score", "?")
        print(f"  {i+1}. [{score}分] {bi.get('title','?')[:40]}")
        print(f"     作者: {bi.get('author','?')} | 里程: {ra.get('distance_km','?')}km | 途经: {ra.get('waypoint_names',[])}")

if __name__ == "__main__":
    main()
