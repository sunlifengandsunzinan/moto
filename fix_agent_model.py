import json

path = r'C:\Users\Administrator\.openclaw\openclaw.json'
with open(path, 'r', encoding='utf-8-sig') as f:
    config = json.load(f)

for agent in config['agents']['list']:
    if agent['id'] == 'analysis':
        old = agent['model']['primary']
        agent['model']['primary'] = 'ollama/qwen2.5:7b'
        print(f'analysis model: {old} -> ollama/qwen2.5:7b')

with open(path, 'w', encoding='utf-8-sig') as f:
    json.dump(config, f, ensure_ascii=False, indent=4)

with open(path, 'r', encoding='utf-8-sig') as f:
    c = json.load(f)
for a in c['agents']['list']:
    print(f'  {a["id"]}: {a["model"]["primary"]}')
