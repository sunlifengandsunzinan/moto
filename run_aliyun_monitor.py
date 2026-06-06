"""Flask monitor server (port 8899)"""
import sys
sys.path.insert(0, '/opt/moto-monitor')
from aliyun_monitor import app
app.run(host='0.0.0.0', port=8899, debug=False)
