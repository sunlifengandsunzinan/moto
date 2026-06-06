#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""辽宁摩旅路线 Top10 分析脚本 v2
使用 requests 调用 ollama，解决 GBK 编码问题
"""

import json, os, sys, time, requests

os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.stdout.reconfigure(encoding='utf-8')

INPUT_FILE = r"D:\摩旅数据采集\辽宁摩旅路线_全量分析.json"
OUTPUT_FILE = r"D:\摩旅数据采集\辽宁摩旅路线_精选排名_v2.json"
OLLAMA_URL = "http://localhost:11434/api/generate"

def load_data():
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def ollama_review(title, desc, route_info, engagement):
    """调用 qwen2.5:7b 生成评语"""
    prompt = f"""你是一个专业的摩旅路线分析师。分析以下小红书笔记的路线质量。

标题：{title}
描述：{desc[:200]}
途经点：{route_info.get('waypoint_names', [])}
里程：{route_info.get('distance_km', 0)}km
预估骑行里程：{route_info.get('estimated_motorcycle_km', 0)}km
点赞：{engagement.get('likes', 0)}
收藏：{engagement.get('collects', 0)}
评论：{engagement.get('comments', 0)}

请给出：
1. 路线评分（1-10，参考：相关性3分+合理性2分+热度2分+信息量3分）
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

def hard_filter(notes):
    """硬逻辑初筛"""
    filtered = []
    for n in notes:
        ra = n.get("route_analysis", {})
        dist = ra.get("distance_km", 0) or 0
        waypoints = ra.get("waypoint_names", [])
        eng = n.get("engagement", {})
        likes = int(eng.get("likes", 0) or 0)
        collects = int(eng.get("collects", 0) or 0)
        comments = int(eng.get("comments", 0) or 0)
        total_interact = likes + collects + comments

        if len(waypoints) < 2:
            continue
        if dist < 10 or dist > 1000:
            continue
        if total_interact < 100:
            continue
        filtered.append(n)

    def interact_key(n):
        e = n.get("engagement", {})
        return int(e.get("likes", 0) or 0) + int(e.get("collects", 0) or 0) + int(e.get("comments", 0) or 0)
    filtered.sort(key=interact_key, reverse=True)
    return filtered[:30]

def parse_score(text):
    import re
    m = re.search(r'评分:\s*(\d+(?:\.\d+)?)', text)
    if m:
        return float(m.group(1))
    return 5.0

def main():
    print("=" * 60)
    print("辽宁摩旅路线 Top10 分析 v2 (requests)")
    print("=" * 60)

    data = load_data()
    print(f"[1/4] 加载数据: {len(data)} 条")

    candidates = hard_filter(data)
    print(f"[2/4] 硬逻辑初筛: {len(candidates)} 条合格")

    if not candidates:
        print("无候选条目")
        return

    print("[3/4] Ollama 逐条评分 (qwen2.5:7b)...")
    results = []
    for i, n in enumerate(candidates):
        title = n.get("basic_info", {}).get("title", "")
        desc = n.get("basic_info", {}).get("description", "")
        ra = n.get("route_analysis", {})
        eng = n.get("engagement", {})

        safe_title = title[:30].encode('utf-8', errors='replace').decode('utf-8')
        print(f"  [{i+1}/{len(candidates)}] {safe_title}... ", end="", flush=True)

        review = ollama_review(title, desc, ra, eng)
        score = parse_score(review)
        print(f"评分 {score}")

        ncopy = json.loads(json.dumps(n))
        ncopy["score"] = score
        ncopy["ollama_review"] = {
            "score": score,
            "rating": "推荐" if score >= 7 else ("可参考" if score >= 5 else "一般"),
            "comment": review[:200],
            "riding_advice": ""
        }
        results.append(ncopy)

        if (i + 1) % 5 == 0:
            with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                json.dump({"batch": 1, "total": len(candidates), "routes": results}, f, ensure_ascii=False, indent=2)
            print(f"  -> 已保存 ({(i+1)}/{len(candidates)})")

    results.sort(key=lambda x: x.get("score", 0), reverse=True)
    top10 = results[:10]

    output = {
        "batch": 1,
        "total_analyzed": len(data),
        "candidates": len(candidates),
        "selected_count": 10,
        "analysis_time": time.strftime("%Y-%m-%d %H:%M"),
        "routes": top10
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*60}")
    print(f"完成！保存到 {OUTPUT_FILE}")
    print(f"{'='*60}")
    for i, r in enumerate(top10[:5]):
        bi = r.get("basic_info", {})
        ra = r.get("route_analysis", {})
        print(f"  {i+1}. {bi.get('title','?')[:40]}")
        print(f"     作者: {bi.get('author','?')} | 里程: {ra.get('distance_km','?')}km | 评分: {r.get('score','?')}")

if __name__ == "__main__":
    main()
