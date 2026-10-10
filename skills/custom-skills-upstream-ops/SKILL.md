---
name: custom-skills-upstream-ops
description: |
  Unified upstream repo operations: audit commit drift, detect repo overlap with local project, and perform sync maintenance.
  Use when: reviewing upstream updates, evaluating a new repo for integration, updating last-sync.yaml after sync.
  Applies to requests written in English or Chinese.
---

# Upstream Ops | 上游操作統一入口

管理所有跟上游 repo 相關的操作。依 argument 路由到 `modes/<name>.md`。

## 用法

```bash
/custom-skills-upstream-ops                           # 預設 = audit
/custom-skills-upstream-ops audit [--source <name>] [--archive]
/custom-skills-upstream-ops overlap <repo-path-or-source-name>
/custom-skills-upstream-ops maintenance <sub>
```

## Mode 選擇表

| 我想…… | 用哪個 mode |
|-------|-----------|
| 看上游有哪些變動、該怎麼同步 | `audit`（預設） |
| 評估某個 repo 跟本專案有多少重疊功能 | `overlap` |
| 同步完成後更新 `last-sync.yaml`、清理舊報告 | `maintenance` |

## Modes

- **audit** — 讀 `upstream/sources.yaml` + `last-sync.yaml`，對每個上游跑 `git log` / `git diff --stat`，輸出同步決策清單。見 `modes/audit.md`。
- **overlap** — 任一 repo vs 本專案的功能重疊偵測，輸出重疊清單與建議。見 `modes/overlap.md`。
- **maintenance** — `update-last-sync`、`archive-reports`、`list-orphans` 三個子命令。見 `modes/maintenance.md`。

## References

- `references/install-methods.md` — 各上游 `install_method` 的同步命令 one-liner
- `references/decision-patterns.md` — audit 結果判讀規則（取代舊 upstream-compare 的 reading guide）

## 相關

- `ai-dev update --only repos` — 拉取上游檔案
- `ai-dev clone` — 分發 `skills/`
- `custom-skills-tool-overlap-analyzer` — 分析**本專案內部**工具重疊（不同職責）
