---
name: knowledge-vault-retro-sink
description: "Use when the user asks to沉淀复盘/写复盘/问题总结入库, or wants a standardized engineering note with sections: 问题-根因-改动-验证-回归."
argument-hint: "fix summary, touched files, verification evidence, and next regression guards"
---

# Knowledge Vault Retro Sink

This skill turns a completed fix into a reusable postmortem-style note and saves it into the knowledge vault in a standardized format.

## Primary Goal

Produce a note that can be copied directly into the vault with clear, engineering-grade structure:

- 问题
- 根因
- 改动
- 验证
- 回归

## Use This Skill When

Use this skill when user intent includes:

- 沉淀这次修复
- 写个复盘
- 放到知识库
- 形成标准化问题记录
- 以后可复用的故障处理笔记

Do not use this skill for pure Git synchronization only. If user asks pull/push only, use `knowledge-vault-sync`.

## Inputs Required

Collect from current context before writing:

1. Problem statement and user-visible symptom.
2. Root cause explanation at code/data level.
3. Exact changed files and key logic diffs.
4. Verification evidence (manual checks, API checks, tests, logs).
5. Regression guard plan (tests, monitoring, coding constraints).

If one input is missing, infer from workspace evidence and clearly mark assumptions.

## Output Format (Mandatory)

Use this exact section order in Chinese:

1. `# <标题>`
2. `## 背景`
3. `## 问题`
4. `## 根因`
5. `## 改动`
6. `## 验证`
7. `## 回归防线`
8. `## 影响范围`
9. `## 待办`
10. `## 关键信息索引`

### Section Rules

- 问题: describe expected vs actual behavior.
- 根因: include the mismatch source and why it was possible.
- 改动: list file path + key change point.
- 验证: include at least 2 evidence items.
- 回归防线: include at least 3 actionable safeguards.
- 关键信息索引: include API path, route slug, command snippets, and related file references.

## Writing Constraints

- Prefer concise, factual, reusable wording.
- No fluffy narrative.
- Keep each section scannable with short bullets.
- If uncertainty exists, mark with `假设:` and keep minimal.

## Save Rules

Default vault target:

- `knowledge-vault/Resources/Engineering/复盘/`

Filename rule:

- `YYYY-MM-DD-<主题>-复盘.md`

If the user specifies folder/topic, follow user instruction first.

## Standard Template

```markdown
# <主题> 复盘

## 背景
- 时间:
- 触发场景:
- 影响页面/接口:

## 问题
- 预期:
- 实际:
- 用户可见现象:

## 根因
- 直接原因:
- 深层原因:
- 为什么之前没发现:

## 改动
- 文件: <path>
  - 变更点:
  - 目的:
- 文件: <path>
  - 变更点:
  - 目的:

## 验证
- 用例1:
  - 操作:
  - 结果:
- 用例2:
  - 操作:
  - 结果:
- 辅助证据:

## 回归防线
- 增加校验:
- 增加测试:
- 增加监控/告警:

## 影响范围
- 受影响模块:
- 不受影响模块:
- 风险评估:

## 待办
- [ ]
- [ ]

## 关键信息索引
- 相关文件:
- 相关接口:
- 相关命令:
- 相关数据键:
```

## Execution Workflow

1. Gather fix context from current conversation and workspace.
2. Fill template with concrete facts.
3. Write note into vault path with date-prefixed filename.
4. Verify file exists and can be read.
5. If requested, chain to `knowledge-vault-sync` for push.

## Completion Output

Report:

- Final note path.
- Why folder was chosen.
- Whether pushed to remote or saved locally only.
