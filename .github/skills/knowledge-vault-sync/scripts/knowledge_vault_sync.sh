#!/usr/bin/env bash
set -euo pipefail

REPO_URL="https://github.com/sunlifengandsunzinan/lifeng-knowledge-vault.git"
ACTION="${1:-status}"
VAULT_DIR="${2:-knowledge-vault}"
COMMIT_MSG="${3:-chore: sync knowledge vault $(date '+%Y-%m-%d %H:%M:%S')}"

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Error: required command '$1' not found." >&2
    exit 1
  }
}

ensure_repo() {
  if [[ ! -d "$VAULT_DIR/.git" ]]; then
    echo "Vault repo not found at '$VAULT_DIR'. Cloning..."
    git clone "$REPO_URL" "$VAULT_DIR"
  fi
}

show_status() {
  git -C "$VAULT_DIR" status --short --branch
}

pull_repo() {
  ensure_repo
  echo "Pulling latest changes from remote..."
  git -C "$VAULT_DIR" fetch --all --prune
  local current_branch
  current_branch="$(git -C "$VAULT_DIR" rev-parse --abbrev-ref HEAD)"
  git -C "$VAULT_DIR" pull --rebase origin "$current_branch"
  show_status
}

push_repo() {
  ensure_repo
  local current_branch
  current_branch="$(git -C "$VAULT_DIR" rev-parse --abbrev-ref HEAD)"

  git -C "$VAULT_DIR" add -A

  if git -C "$VAULT_DIR" diff --cached --quiet; then
    echo "No staged changes to commit."
  else
    git -C "$VAULT_DIR" commit -m "$COMMIT_MSG"
  fi

  echo "Pushing branch '$current_branch' to remote..."
  git -C "$VAULT_DIR" push -u origin "$current_branch"
  show_status
}

clone_repo() {
  if [[ -d "$VAULT_DIR/.git" ]]; then
    echo "Vault repo already exists at '$VAULT_DIR'."
    show_status
    return
  fi

  git clone "$REPO_URL" "$VAULT_DIR"
  show_status
}

main() {
  require_cmd git

  case "$ACTION" in
    pull)
      pull_repo
      ;;
    push)
      push_repo
      ;;
    status)
      ensure_repo
      show_status
      ;;
    clone)
      clone_repo
      ;;
    *)
      echo "Usage: $0 <pull|push|status|clone> [vault_path] [commit_message]" >&2
      exit 2
      ;;
  esac
}

main
