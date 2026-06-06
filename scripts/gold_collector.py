#!/usr/bin/env python3
"""黄金活期价格采集器 - 每10分钟运行"""
import json, os, sys
from datetime import datetime

DATA_DIR = "/root/moto/data"
os.makedirs(DATA_DIR, exist_ok=True)

# 价格文件
PRICE_FILE = "/tmp/gold_price.json"
HOURLY_FILE = "/tmp/gold_hourly.json"
HISTORY_FILE = os.path.join(DATA_DIR, "gold_history.txt")

def fetch_gold():
    import urllib.request
    url = "https://api.gold-api.com/price/XAU/CNY"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            price_cny = data.get("price", 0)
            price_per_g = round(price_cny / 31.1035, 2)
            exchange_rate = data.get("exchangeRate", 6.8)
            price_usd_oz = round(price_cny / exchange_rate, 2)
            result = {
                "source": "gold-api",
                "price_usd_oz": price_usd_oz,
                "price_cny_oz": round(price_cny, 2),
                "price_cny_g": price_per_g,
                "exchange_rate": exchange_rate,
                "updated": data.get("updatedAt", ""),
                "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            return result
    except Exception as e:
        return {"error": str(e)}

def main():
    result = fetch_gold()
    
    with open(PRICE_FILE, "w") as f:
        json.dump(result, f, ensure_ascii=False)
    
    now = datetime.now()
    is_hourly = now.minute == 0
    
    if "error" not in result:
        price = result["price_cny_g"]
        print(f"{result['fetched_at']} | 金价: {price:.2f} 人民币/克")
        
        if is_hourly:
            # 保存整点数据用于通知
            with open(HOURLY_FILE, "w") as f:
                json.dump(result, f, ensure_ascii=False)
            # 追加历史
            with open(HISTORY_FILE, "a") as f:
                f.write(f"{result['fetched_at']}|{price:.2f}|{result['price_usd_oz']:.2f}|{result['exchange_rate']}\n")
            # 只输出价格给调用者
            print(f"HOURLY:{price:.2f}")
    else:
        print(f"ERROR: {result['error']}")

if __name__ == "__main__":
    main()
