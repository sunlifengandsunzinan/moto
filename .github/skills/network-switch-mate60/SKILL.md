---
name: network-switch-mate60
description: 'Use when running pip install, opening WeChat DevTools, pushing code to GitHub, or when the task mentions 切换网络, 热点, FF的Mate 60 Pro, BBA-Office-WLAN, 微信开发工具, pip安装, 代码推送. Treats FF的Mate 60 Pro and BBA-Office-WLAN as backup networks and auto-switches when the current network cannot reach the required service.'
user-invocable: true
---

# Network Switch Mate 60

## Purpose

This skill defines a backup-network workflow for network-sensitive actions. It keeps the current network if connectivity is healthy, and otherwise auto-switches between `BBA-Office-WLAN` and `FF的Mate 60 Pro`.

## When To Use

Use this skill when the task involves any of the following:

- `pip install` or `python -m pip install`
- opening or driving WeChat DevTools
- `git push` to GitHub
- user asks to switch network, use hotspot, or mentions `FF的Mate 60 Pro` or `BBA-Office-WLAN`

## Behavior

A workspace hook is configured in `.github/hooks/ensure-mate60-network.json` and runs `.github/hooks/scripts/ensure_mate60_network.py` before terminal tool execution.

The hook will:

1. Inspect the terminal command.
2. If the command matches a configured trigger, test whether the current network can reach the required service.
3. If the current network is unavailable, try the other configured network in the backup list.
4. Allow the command to continue only after a successful switch and a fresh connectivity check.
5. Restore the previous network when a switch attempt fails.
6. Ask for manual intervention if neither backup network is usable.

## Triggered Commands

Current automatic triggers include:

- `pip install`
- `pip3 install`
- `python -m pip install`
- `python3 -m pip install`
- `git push`
- commands containing `WeChat DevTools`, `wechat devtools`, `wechatwebdevtools`, or `微信开发者工具`

## Notes

- Current backup network order is `BBA-Office-WLAN` and `FF的Mate 60 Pro`.
- This workflow assumes both SSIDs are already saved on the Mac if a password is required.
- If you need more commands covered later, extend the regex list in `.github/hooks/scripts/ensure_mate60_network.py`.
