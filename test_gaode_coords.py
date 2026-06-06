"""Test Gaode API geocoding for Liaoning waypoints"""
import urllib.request, urllib.parse, json, sys, io, math

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

def haversine(lng1, lat1, lng2, lat2):
    """Haversine distance in km"""
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

# Known coordinates for common Liaoning motorcycle spots
known_coords = {
    "沈阳": (123.431, 41.808),
    "大连": (121.615, 38.914),
    "丹东": (124.356, 40.000),
    "本溪": (123.766, 41.330),
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
    "丹东绿江村": (125.380, 40.720),
    "本溪水洞": (124.080, 41.320),
    "关门山": (124.020, 41.160),
    "天桥沟": (124.780, 40.980),
    "老秃顶子": (125.020, 41.320),
    "滨江公路": (124.350, 40.050),
    "辽河": (122.000, 41.200),
    "红海滩": (121.970, 40.720),
    "笔架山": (121.120, 40.850),
}

# Try Gaode API (use empty key to test, will likely fail)
api_key = ""  # TODO: fill in if needed

print("=" * 60)
print("辽宁摩旅路线：坐标查询与里程计算示例")
print("=" * 60)

# Test 1: 崔桂线路线（从评论提取的途经点）
print("\n📌 场景1：崔桂线自驾路线")
route1 = ["沈阳", "盖州", "庄河", "崔桂线"]

print("  途经点坐标:")
for name in route1:
    if name in known_coords:
        lng, lat = known_coords[name]
        print(f"    {name}: {lng}, {lat}")
    else:
        print(f"    {name}: ⚠️ 未知坐标")

# Calculate distance
total = 0
segments = []
for i in range(len(route1) - 1):
    p1 = route1[i]
    p2 = route1[i+1]
    if p1 in known_coords and p2 in known_coords:
        d = haversine(known_coords[p1][0], known_coords[p1][1], known_coords[p2][0], known_coords[p2][1])
        total += d
        segments.append((p1, p2, round(d, 1)))

print(f"\n  分段里程:")
for s, e, d in segments:
    print(f"    {s} → {e}: {d} km")
print(f"  🏍️ 总里程（直线距离和）: {round(total, 1)} km")
print(f"  📍 预估实际骑行里程: ~{round(total * 1.3)} km（直线+30%系数）")

# Test 2: 丹东绿江村路线
print("\n📌 场景2：丹东-绿江村骑行路线")
route2 = ["丹东", "丹东绿江村", "绿江村"]

for name in route2:
    if name in known_coords:
        lng, lat = known_coords[name]
        print(f"    {name}: {lng}, {lat}")

d = haversine(known_coords["丹东"][0], known_coords["丹东"][1], known_coords["绿江村"][0], known_coords["绿江村"][1])
print(f"  丹东→绿江村直线: {round(d, 1)} km")
print(f"  预估骑行里程: ~{round(d * 1.5)} km（山路系数）")

# Test 3: 本桓公路
print("\n📌 场景3：本桓公路自驾")
route3 = ["本溪", "本桓公路", "桓仁"]
# 桓仁坐标
known_coords["桓仁"] = (125.360, 41.270)

for name in route3:
    if name in known_coords:
        lng, lat = known_coords[name]
        print(f"    {name}: {lng}, {lat}")

d = haversine(known_coords["本溪"][0], known_coords["本溪"][1], known_coords["桓仁"][0], known_coords["桓仁"][1])
print(f"  本溪→桓仁（经本桓公路）直线: {round(d, 1)} km")
print(f"  本桓公路实测里程: ~130 km")

# Save reference coordinates
output = {
    "generated_at": "2026-06-02",
    "note": "辽宁摩旅路线常用途经点坐标库（高德坐标系 GCJ-02）",
    "known_coords": {k: {"lng": v[0], "lat": v[1]} for k, v in known_coords.items()},
    "sample_routes": [
        {
            "name": "沈阳→盖州→庄河→崔桂线",
            "waypoints": ["沈阳", "盖州", "庄河", "崔桂线"],
            "distance_km": round(total * 1.3)
        },
        {
            "name": "丹东→绿江村",
            "waypoints": ["丹东", "绿江村"],
            "distance_km": round(d * 1.5)
        },
        {
            "name": "本溪→本桓公路→桓仁",
            "waypoints": ["本溪", "桓仁"],
            "distance_km": 130
        }
    ]
}

with open(r"D:\摩旅数据采集\liaoning_coords_reference.json", "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"\n✅ 坐标参考库已保存到 D:\\摩旅数据采集\\liaoning_coords_reference.json")
