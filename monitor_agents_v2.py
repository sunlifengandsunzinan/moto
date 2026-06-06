"""Agent 工作状态监控器 v2 - 含TOP5路线 + 自动推送到阿里云"""
import json, os, time, subprocess, sys, io
from datetime import datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

MONITOR_FILE = r"D:\摩旅数据采集\agent_status.json"
ALIYUN_SSH = "root@8.141.4.69"
ALIYUN_PATH = "/opt/moto-monitor/agent_status.json"

def get_file_size(path):
    try:
        return os.path.getsize(path)
    except:
        return 0

def get_data_stats():
    data_dir = r"C:\Users\Administrator\.openclaw\workspace\MediaCrawler\data\xhs\jsonl"
    ln_keywords = ['辽宁摩旅路线','辽宁自驾游路线推荐','辽宁骑行路线','大连摩旅','沈阳周边自驾游',
                   '丹东骑行路线','本桓公路自驾','辽宁沿海公路自驾','丹东绿江村骑行','锦州海滨自驾',
                   '辽东山水自驾路线','本桓公路']
    
    contents_file = os.path.join(data_dir, "search_contents_2026-06-02.jsonl")
    comments_file = os.path.join(data_dir, "search_comments_2026-06-02.jsonl")
    
    contents_size = get_file_size(contents_file)
    comments_size = get_file_size(comments_file)
    
    total_notes = 0
    ln_notes = 0
    try:
        with open(contents_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line: continue
                total_notes += 1
                d = json.loads(line)
                if d.get("source_keyword","") in ln_keywords:
                    ln_notes += 1
    except:
        pass
    
    total_comments = 0
    try:
        with open(comments_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    total_comments += 1
    except:
        pass
    
    return {
        "total_notes": total_notes,
        "ln_notes": ln_notes,
        "total_comments": total_comments,
        "contents_size_kb": round(contents_size / 1024, 1),
        "comments_size_kb": round(comments_size / 1024, 1)
    }

def get_top_routes():
    """从精选排名JSON提取TOP5"""
    try:
        path = r"D:\摩旅数据采集\辽宁摩旅路线_精选排名.json"
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        routes = data.get("routes", data)
        top5 = []
        for r in routes[:5]:
            top5.append({
                "title": r["basic_info"]["title"][:30],
                "author": r["basic_info"]["author"],
                "distance": r["route_analysis"]["distance_km"],
                "score": r.get("score", "?"),
                "waypoints": r["route_analysis"]["waypoint_names"][:3],
                "has_ollama": bool(r.get("ollama_review", ""))
            })
        return top5
    except:
        return []

def check_ollama_status():
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True, text=True, timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        if "qwen2.5" in result.stdout:
            return "running"
        return "idle"
    except:
        return "unknown"

def check_python_process():
    try:
        result = subprocess.run(
            ["tasklist", "/V", "/FO", "CSV"],
            capture_output=True, text=True, timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        return "python.exe" in result.stdout
    except:
        return False

def push_to_aliyun():
    """Push status file to Aliyun via SCP"""
    try:
        result = subprocess.run(
            ["scp", MONITOR_FILE, f"{ALIYUN_SSH}:{ALIYUN_PATH}"],
            capture_output=True, text=True, timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        return result.returncode == 0
    except:
        return False

def build_status():
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Agent configs
    agent_dirs = {
        "crawler": r"C:\Users\Administrator\.openclaw\agents\crawler\agent",
        "analysis": r"C:\Users\Administrator\.openclaw\agents\analysis\agent",
        "integrator": r"C:\Users\Administrator\.openclaw\agents\integrator\agent"
    }
    
    agents_info = {}
    for name, path in agent_dirs.items():
        exists = os.path.isdir(path)
        soul = ""
        soul_file = os.path.join(path, "SOUL.md")
        if os.path.isfile(soul_file):
            with open(soul_file, "r", encoding="utf-8") as f:
                soul = f.read(200)
        agents_info[name] = {
            "exists": exists,
            "soul_preview": soul[:60].replace('\n','') if soul else "(无)"
        }
    
    # Data
    data = get_data_stats()
    
    # Analysis files
    analysis_dir = r"D:\摩旅数据采集"
    analysis_files = {}
    if os.path.isdir(analysis_dir):
        for fname in sorted(os.listdir(analysis_dir)):
            fpath = os.path.join(analysis_dir, fname)
            if os.path.isfile(fpath):
                analysis_files[fname] = round(os.path.getsize(fpath) / 1024, 1)
    
    # Top routes
    top_routes = get_top_routes()
    
    # Services
    ollama = check_ollama_status()
    py_running = check_python_process()
    
    # Suggestions
    suggestions = []
    if data["ln_notes"] < 200:
        remaining = max(0, 200 - data["ln_notes"])
        suggestions.append(f"采集进度: 辽宁 {data['ln_notes']}条 / 目标200条 (剩余{remaining}条)")
    
    if ollama != "running":
        suggestions.append("⚠️ Ollama未运行，AI分析功能不可用")
    
    status = {
        "timestamp": now,
        "epoch_ms": int(time.time() * 1000),
        "agents": agents_info,
        "ollama": ollama,
        "python_running": py_running,
        "data": data,
        "analysis_files": analysis_files,
        "top_routes": top_routes,
        "suggestions": suggestions
    }
    
    return status

# ===== Main =====
status = build_status()

os.makedirs(r"D:\摩旅数据采集", exist_ok=True)
with open(MONITOR_FILE, "w", encoding="utf-8") as f:
    json.dump(status, f, ensure_ascii=False, indent=2)

# Push to Aliyun
push_ok = push_to_aliyun()

# Print summary
print(f"🕐 {status['timestamp']}")
print(f"{'='*50}")
print(f"📡 Agent 状态:")
for name, info in status['agents'].items():
    icon = "✅" if info['exists'] else "❌"
    print(f"  {icon} {name}: {'已配置' if info['exists'] else '未配置'}")

print(f"\n📊 数据采集:")
d = status['data']
print(f"  📝 总笔记: {d['total_notes']} | 辽宁: {d['ln_notes']} | 评论: {d['total_comments']}")

print(f"\n🤖 Ollama: {'✅ 运行中' if status['ollama'] == 'running' else '⏸️ 空闲/离线'}")
print(f"🐍 Python进程: {'运行中' if status['python_running'] else '空闲'}")

print(f"\n🥇 TOP5 路线:")
for i, r in enumerate(status['top_routes'][:5]):
    print(f"  #{i+1} [{r['score']}/10] {r['title']} | {r['distance']}km | {', '.join(r['waypoints'])}")

print(f"\n📁 分析产出 ({len(status['analysis_files'])}个文件):")
for fname, size in sorted(status['analysis_files'].items(), key=lambda x: -x[1])[:8]:
    print(f"  📄 {fname} ({size} KB)")

aliyun_host = "http://8.141.4.69:5000"
print(f"\n📡 阿里云推送: {'✅ 成功' if push_ok else '❌ 失败'}")
if push_ok:
    print(f"   访问地址: {aliyun_host}")
