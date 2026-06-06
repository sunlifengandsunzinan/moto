import json, os, sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

jsonl = r'C:\Users\Administrator\.openclaw\workspace\MediaCrawler\data\xhs\jsonl\search_contents_2026-06-02.jsonl'
comments = r'C:\Users\Administrator\.openclaw\workspace\MediaCrawler\data\xhs\jsonl\search_comments_2026-06-02.jsonl'
state_file = r'D:\摩旅数据采集\pipeline_state.json'

if os.path.exists(jsonl):
    kws = {}
    notes = []
    with open(jsonl, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line: continue
            d = json.loads(line)
            kw = d.get('source_keyword', '?')
            kws[kw] = kws.get(kw, 0) + 1
            notes.append(d)
    
    print(f'总笔记: {len(notes)} 条')
    print('关键词分布:')
    for kw, cnt in sorted(kws.items(), key=lambda x: -x[1]):
        print(f'  {kw}: {cnt}')
else:
    print('contents.jsonl 不存在')

if os.path.exists(comments):
    with open(comments, 'r', encoding='utf-8') as f:
        c = sum(1 for line in f if line.strip())
    print(f'评论: {c} 条')
else:
    print('comments 不存在')

if os.path.exists(state_file):
    with open(state_file, 'r', encoding='utf-8') as f:
        s = json.load(f)
    print(f'Pipeline: 已处理 {len(s["processed_note_ids"])} 条, 批次 {s["batches_processed"]}')
else:
    print('Pipeline 状态: 无')

out = r'D:\摩旅数据采集'
if os.path.isdir(out):
    fs = os.listdir(out)
    print(f'D盘产出: {len(fs)} 个文件')
