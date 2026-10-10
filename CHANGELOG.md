# Changelog

## Unreleased

- `custom-skills-doc-updater` 改寫成「範圍 → 變更類型與要看的文件 → 更新方式 → 完成檢查」：未指定範圍時直接分析最近 1 個 commit，不再跳出選單；移除逐步驟的中間報告範本，以及已不存在的 `sources/`、`.standards/`、`agents/claude/README.md`、`commands/claude/README.md` 路徑。
- `custom-skill-creator` 的輸出格式範例改用一般語氣（不再示範全大寫 ALWAYS），benchmark schema 範例的模型 ID 改為佔位字串。
- `custom-skills-ecc-analyze` 移除已退役的 `uds` 與寫死的 skill 數量。
- `custom-skills-ecc-analyze`、`custom-skills-dev`、`custom-skills-doc-updater` 的 description 移除觸發片語清單，保留 Use when 的意圖說明。
- 移除 `work-log-claude`。工作日誌改由 ai-dev 專案範本提供的 `work-log-codex` 處理，Claude Code 與 Codex 共用同一套解析器；只讀 Claude Code 紀錄時用範本的 `.claude/skills/work-log-claude` 薄包裝。skill collection 更新為 19 個 skills。

## 0.1.2 - 2026-09-29

- 新增 `safe-run`，依 host-aware、task-isolated 與 mixed workflow 在 harness 原生沙盒與 OpenShell 之間路由。
- OpenShell 路徑要求先確認 NVIDIA/OpenShell skills；若未安裝，執行 `npx skills add NVIDIA/OpenShell`。
- skill collection 更新為 20 個 skills。

## 0.1.1 - 2026-08-28

- 新增 `.claude-plugin/plugin.json`，讓 `npx skills` 將 19 個 skills 顯示為可整組選取的 `Ai Dev Skills` collection。
- validator 會檢查 plugin collection 與 canonical skill inventory 完全一致。

## 0.1.0 - 2026-08-28

- 從 `ValorVie/custom-skills` 抽離 19 個第一方 skills。
- 將 `custom-simplify` 來源目錄正規化為 canonical ID `simplify`。
- 清理內部範例與 private paths，修正跨 agent 安裝路徑及 escaping links。
- 加入 repository-level canonical ID、relative link 與公開邊界驗證。

初始 snapshot 來源 commit：`56953acf0709f6841d52ded85bc0e67d52cb540a`。
