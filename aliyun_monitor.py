"""Flask监控服务 - 部署在阿里云上，展示3个Agent的工作状态"""
import json, os, time
from flask import Flask, jsonify, render_template

app = Flask(__name__)

# 从本机同步过来的状态数据文件
STATUS_FILE = "/opt/moto-monitor/agent_status.json"

@app.route("/")
def index():
    """主监控页面"""
    return render_template("monitor.html")

@app.route("/api/status")
def api_status():
    """返回JSON状态数据"""
    try:
        with open(STATUS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return jsonify(data)
    except:
        return jsonify({
            "status": "waiting",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "message": "等待数据同步..."
        })

if __name__ == "__main__":
    # 确保模板目录存在
    os.makedirs("/opt/moto-monitor/templates", exist_ok=True)
    app.run(host="0.0.0.0", port=5000, debug=False)
