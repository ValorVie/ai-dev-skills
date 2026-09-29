# Changelog

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
