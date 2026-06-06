# -*- coding: utf-8 -*-
import json

# Gold cron usage from cron runs data
gold_usage = [
    {"input": 524, "output": 390, "total": 18477},
    {"input": 564, "output": 415, "total": 18132},
    {"input": 351, "output": 290, "total": 18132},
    {"input": 523, "output": 402, "total": 18476},
    {"input": 460, "output": 465, "total": 18543},
    {"input": 351, "output": 290, "total": 18132},
    {"input": 531, "output": 426, "total": 18484},
    {"input": 549, "output": 374, "total": 18512},
    {"input": 525, "output": 261, "total": 18360},
    {"input": 351, "output": 285, "total": 18132},
    {"input": 532, "output": 460, "total": 18496},
    {"input": 569, "output": 456, "total": 18532},
    {"input": 497, "output": 507, "total": 18577},
    {"input": 568, "output": 468, "total": 18507},
    {"input": 548, "output": 423, "total": 18501},
    {"input": 550, "output": 418, "total": 18503},
    {"input": 692, "output": 445, "total": 18594},
    {"input": 472, "output": 365, "total": 18425},
    {"input": 517, "output": 382, "total": 18470},
    {"input": 351, "output": 295, "total": 18132},
    {"input": 545, "output": 431, "total": 18497},
    {"input": 527, "output": 368, "total": 18480},
    {"input": 442, "output": 578, "total": 18500},
]

gold_input = sum(u["input"] for u in gold_usage)
gold_output = sum(u["output"] for u in gold_usage)
gold_total = sum(u["total"] for u in gold_usage)

print("=== Gold Cron (6/1-6/3, 23次成功运行) ===")
print(f"  运行次数: {len(gold_usage)}")
print(f"  输入tokens:    {gold_input:>8,}")
print(f"  输出tokens:    {gold_output:>8,}")
print(f"  上下文tokens:  {gold_total - gold_input - gold_output:>8,}")
print(f"  总tokens:      {gold_total:>8,}")
gold_cost = (gold_input * 0.5 + gold_output * 2.0) / 1_000_000
print(f"  费用:          {gold_cost:.3f}")

print()
# 估算其他
chat_input = 50000
chat_output = 30000
chat_cost = (chat_input * 0.5 + chat_output * 2.0) / 1_000_000

crawler_input = 1500
crawler_output = 900
crawler_cost = (crawler_input * 0.5 + crawler_output * 2.0) / 1_000_000

analysis_cost = 0

total_cost = gold_cost + chat_cost + crawler_cost + analysis_cost

print("=== 全部分布 (6/1-6/3) ===")
print(f"  Gold Cron        {gold_cost:.3f}  ({gold_cost/total_cost*100:.0f}%)")
print(f"  日常对话(估)     {chat_cost:.3f}  ({chat_cost/total_cost*100:.0f}%)")
print(f"  Crawler子agent   {crawler_cost:.3f}  ({crawler_cost/total_cost*100:.0f}%)")
print(f"  Analysis子agent  {analysis_cost:.3f}  ({analysis_cost/total_cost*100:.0f}%)")
print(f"  ---------------------------------")
print(f"  总计             {total_cost:.3f}")
print()

# Monthly projection
m_gold = gold_cost * 30 / 3
m_chat = chat_cost * 30
m_total = m_gold + m_chat
print("=== 月度预估 ===")
print(f"  Gold Cron:         {m_gold:.1f}")
print(f"  日常对话:          {m_chat:.1f}")
print(f"  总计:              {m_total:.1f}")
print()
print("价格基准: DeepSeek标准 0.5/百万输入 + 2.0/百万输出")
