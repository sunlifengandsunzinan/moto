---
name: knowledge-vault-note-sync
description: "Use when the user asks to sync notes into the Sunlifeng knowledge vault, says 同步到知识库 / 放到知识库 / 写到知识库 / 存到知识库, or wants a summary, reflection, project note, resume note, or PM note placed into knowledge-vault with the right PARA folder and date-prefixed filename."
argument-hint: "note request or summary content"
---

# Knowledge Vault Note Sync

This skill is for turning conversation output into a properly placed note inside the local Sunlifeng knowledge vault.

Vault facts:

- local vault path: `knowledge-vault/`
- vault structure follows PARA: `Inbox/`, `Projects/`, `Areas/`, `Resources/`, `Archive/`
- naming rule: prefer date-prefixed, semantic filenames such as `2026-08-22-主题.md`

## Use This Skill When

Use this skill when the user asks to:

- 同步到知识库
- 放到知识库
- 写到知识库
- 存到知识库
- 放进 sunlifeng 开头的知识库
- 把总结、复盘、项目说明、简历素材、业务笔记落到知识库

Do not use this skill for Git sync alone. If the user explicitly asks to pull/push the vault repo, chain to the existing `knowledge-vault-sync` skill after creating or updating the note.

## Decision Rules

Choose the target folder by note type:

- `Inbox/`: quick capture, temporary notes, raw ideas waiting for cleanup
- `Projects/`: project plans, milestone logs, execution notes tied to an active project
- `Areas/`: long-term responsibility notes, ongoing domains, career or learning areas
- `Resources/`: reusable knowledge, methods, summaries, frameworks, interview notes, resume material, PM notes
- `Archive/`: only when the user explicitly wants to archive old material

Default behavior:

- if the note is a reusable summary or methodology, prefer `Resources/`
- if the note is mainly project progress or a project working log, prefer `Projects/`
- if the note belongs under an existing topic subfolder, reuse that subfolder
- if no matching topic folder exists, create the smallest sensible new subfolder only when needed

## Required Workflow

1. Read `knowledge-vault/README.md` if folder conventions are unclear.
2. Inspect the relevant PARA directory and nearby files to infer naming style.
3. Create or update one Markdown note with:
   - clear title
   - short context/background section when needed
   - structured bullets or headings
   - concise, reusable wording
4. Use a date-prefixed semantic filename unless the user asks to append to an existing note.
5. After writing, validate that the file exists and is readable.
6. If the user also wants repository sync, run the `knowledge-vault-sync` workflow with `status`, then `push` if appropriate.

## Writing Style

- prefer Chinese unless the user asks for English
- keep notes concise and reusable
- optimize for future lookup and copy-paste reuse
- avoid fluffy prose
- for resume/interview material, separate: usable claims, boundaries, likely follow-up questions, next-step improvements

## Output Expectations

When finished, report:

- the exact knowledge vault note path
- why that folder was chosen
- whether the note was only saved locally or also pushed