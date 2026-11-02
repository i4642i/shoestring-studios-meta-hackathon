import json
import urllib.request

s = json.load(urllib.request.urlopen(
    "http://127.0.0.1:8000/api/settings", timeout=30))
print(list(s.keys()))
pcs = s.get("pcs", {})
for pcname, cell in pcs.items():
    print("=" * 20, pcname)
    print(json.dumps(cell, ensure_ascii=False)[:900])
