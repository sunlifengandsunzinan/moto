import json, http.client

conn = http.client.HTTPConnection("127.0.0.1", 18800)
conn.request("GET", "/json")
resp = conn.getresponse()
pages = json.loads(resp.read().decode())
conn.close()

douyin_id = None
for p in pages:
    if p.get("type") == "page" and "douyin.com" in p.get("url", ""):
        douyin_id = p["id"]
        print(f"Found: {p['url'][:80]}")
        break

if douyin_id:
    print(f"Douyin page ID: {douyin_id}")
else:
    print("No douyin page found")
    for p in pages:
        if p.get("type") == "page":
            print(f"  {p.get('url', '')[:80]}")
