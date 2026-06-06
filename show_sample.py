"""Show a sample note from the jsonl file to understand its structure"""
import json, sys, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

path = r"C:\Users\Administrator\.openclaw\workspace\MediaCrawler\data\xhs\jsonl\search_contents_2026-06-02.jsonl"
max_items = int(sys.argv[1]) if len(sys.argv) > 1 else 1

with open(path, "r", encoding="utf-8") as f:
    for i, line in enumerate(f):
        if i >= max_items:
            break
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
            if i == 0:
                for k, v in d.items():
                    if isinstance(v, dict):
                        print(f"  {k}: dict ({len(v)} keys)")
                    elif isinstance(v, list):
                        print(f"  {k}: list[{len(v)}]")
                    elif isinstance(v, str):
                        print(f"  {k}: str ({len(v)} chars)")
                    else:
                        print(f"  {k}: {type(v).__name__} = {v}")
                print("\n--- RAW DATA ---")
                print(json.dumps(d, ensure_ascii=False, indent=2)[:3000])
        except json.JSONDecodeError as e:
            print(f"Line {i+1}: JSON error: {e}")
