---
name: custom-skills-doc-updater
description: |
  Maintain documentation for the ai-dev framework and ai-dev-skills collection.
  Use when code or skill changes affect documented behavior, commands, agents, plugins,
  version releases, repository structure, README content, or changelogs.
  Applies to requests written in English or Chinese.
---

# Documentation Updater

讓文件與本次程式或 skill 變更一致：該記進 CHANGELOG 的記進去，說明使用方式的文件跟著改，各處版本號保持一致。

## Repository routing

先確認變更屬於哪個 repository：

- `ValorVie/custom-skills`：ai-dev CLI、commands、agents、plugins、project-template、OpenSpec 與 framework 文件。
- `ValorVie/ai-dev-skills`：第一方 skill content、skill tests、collection README 與 CHANGELOG。

跨 repository 變更要分開檢查、分開提交。不得把 skill content 複製回 framework repository，也不得把 ai-dev runtime 文件放進 skill 目錄冒充 self-contained content。

## 範圍

使用者沒指定範圍時，分析最近 1 個 commit，並在結果開頭寫明採用的範圍。用 `git log`、`git diff --stat` 與 `git diff` 讀出範圍內的變更。

| 參數 | 說明 | 範例 |
|------|------|------|
| 無參數 | 分析最近 1 個 commit | `/doc-updater` |
| `N` | 分析最近 N 個 commits | `/doc-updater 5` |
| `--since <ref>` | 從指定 ref 開始分析 | `/doc-updater --since v1.0.0` |
| `--check` | 只回報需要更新的文件，不修改 | `/doc-updater --check` |

## 變更類型與要看的文件

先依變更檔案的路徑判斷類型：

| 檔案路徑模式 | 變更類型 |
|-------------|---------|
| `skills/**/*.md` | `ai-dev-skills` repository 的 Skill 變更 |
| `agents/**/*.md` | Agent 變更 |
| `commands/**/*.md` | Command 變更 |
| `plugins/**/*` | Plugin 變更 |
| `script/**/*.py` | CLI 功能變更 |
| `pyproject.toml` (version) | 版本發布 |
| `openspec/specs/**/*` | Spec 變更 |
| `upstream/**/*` | 上游整合 |
| `docs/**/*` | 文件變更（可能需要交叉更新） |

再依類型找要看的文件。「一定要更新」的文件若判斷不用改，要寫出原因。

| 變更類型 | 一定要更新 | 視情況更新 |
|---------|-----------|-----------|
| Plugin | `CHANGELOG.md`、`plugins/<name>/README.md` | `README.md`（使用方式改變時）、`docs/AI開發環境設定指南.md`（安裝流程改變時） |
| Skill | `ai-dev-skills/CHANGELOG.md` | `ai-dev-skills/README.md`（skill 清單、安裝方式或 boundary 改變時）、`custom-skills/upstream/npx-skills.yaml`（只有 baseline 採用清單改變時） |
| Agent | `CHANGELOG.md`、`docs/Skill-Command-Agent差異說明.md`「附錄：內建 Agents 清單」 | — |
| Command | `CHANGELOG.md` | 列出該指令的指南 |
| CLI 功能 | `CHANGELOG.md`、`README.md`（指令說明、參數表格） | — |
| 版本發布 | `pyproject.toml` 的 version、`CHANGELOG.md` 的日期與版本號 | `README.md` |
| 上游整合 | `CHANGELOG.md`、`upstream/README.md`「整合決定記錄」 | — |

所有類型也要看 `README.md`；涉及專案脈絡時，再看 `openspec/config.yaml`（舊版是 `openspec/project.md`）。表上沒列到的文件，用變更中的檔名、功能名或指令名搜尋 `*.md` 找出來。

Plugin 改版本時，`plugins/<name>/.claude-plugin/plugin.json` 與 `package.json`（若有）的 `version` 要和 CHANGELOG 一致。

## 更新方式

- 改任何文件前先讀過它，沿用現有的格式與段落結構。
- CHANGELOG 依 Keep a Changelog 格式；各類文件的格式見 [references/doc-formats.md](references/doc-formats.md)。
- 文件用繁體中文，Skill、Command、Agent、Hook、Plugin、CLI、TUI、MCP、API、Git、GitHub、upstream 等技術詞保留英文。
- `--check` 時只回報，不修改任何檔案。

## 完成檢查

- [ ] 「一定要更新」的文件都已更新，或已寫出不用更新的原因
- [ ] `pyproject.toml`、`plugin.json`、`package.json` 與 CHANGELOG 的版本號一致
- [ ] 同一個功能在各文件的說法一致，連結有效

最後回報：分析範圍、已更新的文件與內容、判斷不用更新的文件與原因、版本一致性結果。
