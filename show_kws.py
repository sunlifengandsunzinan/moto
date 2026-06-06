import re, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
with open(r'C:\Users\Administrator\.openclaw\workspace\MediaCrawler\config\base_config.py', 'r', encoding='utf-8') as f:
    content = f.read()
match = re.search(r'KEYWORDS\s*=\s*"(.+?)"', content)
if match:
    kws = match.group(1).split(',')
    for i, kw in enumerate(kws):
        print(f'{i+1}. {kw}')
