"""Show top routes with ollama review"""
import json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

with open(r"D:\摩旅数据采集\辽宁摩旅路线_精选排名.json", "r", encoding="utf-8") as f:
    data = json.load(f)

routes = data.get("routes", data)

print(f"精选路线总数: {len(routes)} 条")
print("=" * 60)

for r in routes[:5]:
    bi = r["basic_info"]
    ra = r["route_analysis"]
    ol = r.get("ollama_review", "")
    rank = r.get("rank", r.get("score", "?"))
    score = r.get("score", "?")
    
    print(f"\n#{rank} [{score}/10] {bi['title'][:40]}")
    print(f"  作者: {bi['author']}")
    print(f"  里程: {ra.get('distance_km', 0)} km")
    if ol:
        # Parse ollama output
        lines = ol.strip().split('\n')
        print(f"  Ollama点评:")
        for line in lines:
            print(f"    {line.strip()}")

# Show the actual ollama_review field
print("\n\n=== RAW OLLAMA_REVIEW TOP1 ===")
if routes:
    print(routes[0].get("ollama_review", "(无)"))
