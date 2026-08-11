---
name: knowledge-vault-sync
description: 'Pull and push a Git knowledge vault repository. Use when syncing notes, publishing updates, resolving remote changes, or checking vault git status.'
argument-hint: 'action=<pull|push|status|clone> [commit message] [vault path]'
---

# Knowledge Vault Sync

Use this skill to synchronize a local knowledge vault with the remote repository:
- Repository: `https://github.com/sunlifengandsunzinan/lifeng-knowledge-vault.git`
- Default local folder: `knowledge-vault` (workspace-relative)

## When To Use
- Pull latest notes before editing.
- Push local note updates to remote.
- Check sync status before/after edits.
- Clone the vault repo into the workspace if it does not exist yet.

## Procedure
1. Parse user intent into one action:
- `pull`: update local vault from remote
- `push`: commit and push local changes
- `status`: inspect repo status and branch
- `clone`: clone the vault repo into local path

2. Run the helper script:
- `bash ./.github/skills/knowledge-vault-sync/scripts/knowledge_vault_sync.sh <action> [vault_path] [commit_message]`

3. Report concise outcome:
- branch, ahead/behind state, files changed, and whether push/pull succeeded.

## Action Examples
- Pull:
  `bash ./.github/skills/knowledge-vault-sync/scripts/knowledge_vault_sync.sh pull`
- Status:
  `bash ./.github/skills/knowledge-vault-sync/scripts/knowledge_vault_sync.sh status`
- Push with message:
  `bash ./.github/skills/knowledge-vault-sync/scripts/knowledge_vault_sync.sh push knowledge-vault "docs: update route notes"`
- Pull from custom path:
  `bash ./.github/skills/knowledge-vault-sync/scripts/knowledge_vault_sync.sh pull /absolute/or/relative/path/to/vault`

## Notes
- If authentication is required, follow terminal prompts for Git credentials.
- This skill should not rewrite history and should not use force push.
- If remote has diverged, pull first and resolve conflicts before pushing.
