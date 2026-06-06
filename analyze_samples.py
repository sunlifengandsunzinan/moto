"""Sample 5 Liaoning notes and save structured analysis to D drive"""
import json, sys, io, os
from datetime import datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

def parse_count(s):
    """Parse counts like '1.6万' or '5125' to int"""
    s = str(s).strip()
    try:
        if '万' in s:
            return int(float(s.replace('万', '')) * 10000)
        return int(s)
    except:
        return 0

ln_keywords = ['辽宁摩旅路线', '辽宁自驾游路线推荐', '辽宁骑行路线', '大连摩旅', '沈阳周边自驾游']

path = r"C:\Users\Administrator\.openclaw\workspace\MediaCrawler\data\xhs\jsonl\search_contents_2026-06-02.jsonl"
comments_path = r"C:\Users\Administrator\.openclaw\workspace\MediaCrawler\data\xhs\jsonl\search_comments_2026-06-02.jsonl"

# Load all comments for lookup
comments_by_note = {}
with open(comments_path, "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        c = json.loads(line)
        nid = c.get("note_id", "")
        if nid not in comments_by_note:
            comments_by_note[nid] = []
        comments_by_note[nid].append(c)

# Sample 5 notes from different keywords (one per keyword)
notes = []
seen_kw = set()
with open(path, "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        kw = d.get("source_keyword", "")
        if kw in ln_keywords and kw not in seen_kw:
            notes.append(d)
            seen_kw.add(kw)
            if len(notes) >= 5:
                break

# Build structured analysis for each note
analyses = []
for n in notes:
    nid = n["note_id"]
    cmts = comments_by_note.get(nid, [])

    sample_comments = []
    for c in cmts[:6]:
        ts = datetime.fromtimestamp(c["create_time"] / 1000).strftime("%Y-%m-%d")
        sample_comments.append({
            "user": c["nickname"],
            "ip_location": c.get("ip_location", ""),
            "content": c["content"],
            "time": ts,
            "likes": parse_count(c.get("like_count", "0"))
        })

    analysis = {
        "note_id": nid,
        "platform": "小红书",
        "data_type": "note",
        "basic_info": {
            "title": n.get("title", ""),
            "media_type": n.get("type", ""),
            "author": n.get("nickname", ""),
            "publish_time": datetime.fromtimestamp(n["time"] / 1000).strftime("%Y-%m-%d %H:%M") if n.get("time") else "",
            "description": n.get("desc", ""),
            "url": n.get("note_url", ""),
            "source_keyword": n.get("source_keyword", "")
        },
        "engagement": {
            "likes": parse_count(n.get("liked_count", "0")),
            "collects": parse_count(n.get("collected_count", "0")),
            "comments": parse_count(n.get("comment_count", "0")),
            "shares": parse_count(n.get("share_count", "0"))
        },
        "topic_classification": {
            "category": "待分析",
            "subcategory": "待分析",
            "keywords_extracted": []
        },
        "route_analysis": {
            "has_route_info": False,
            "route_type": "",
            "mentions": {
                "roads": [],
                "cities_or_regions": [],
                "scenic_spots": []
            },
            "source_comment_insights": []
        },
        "qualification_assessment": {
            "qualified": False,
            "confidence": "low",
            "notes": ""
        },
        "sample_comments": sample_comments,
        "source_keyword": n.get("source_keyword", "")
    }
    analyses.append(analysis)

# Save to D drive
output_dir = r"D:\摩旅数据采集"
os.makedirs(output_dir, exist_ok=True)
output_path = os.path.join(output_dir, "辽宁采样分析.json")
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(analyses, f, ensure_ascii=False, indent=2)

print(f"✅ 已保存到: {output_path}")
print(f"共 {len(analyses)} 条分析结果\n")
for a in analyses:
    bi = a["basic_info"]
    eng = a["engagement"]
    kw = bi["source_keyword"]
    print(f"--- {bi['title'][:30]} ---")
    print(f"  来源: {kw} | 作者: {bi['author']}")
    print(f"  点赞{eng['likes']} 收藏{eng['collects']} 评论{eng['comments']} 分享{eng['shares']}")
    print(f"  评论样本: {len(a['sample_comments'])}条")
    desc = bi.get('description', '')
    if desc:
        print(f"  描述: {desc[:80]}")
    print()
