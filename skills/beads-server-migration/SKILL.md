---
name: beads-server-migration
description: 將單一 repo 的 Beads 從 embedded Dolt 遷移到本機 Dolt 伺服器，或規劃切換、立即退回、寫入後退回及再次切換。多個 bd 程序等鎖、逾時或競爭同一個工作區時使用；只支援 Linux 與 systemd user service。
---

# Beads 伺服器模式遷移

每個 repo 使用自己的 Dolt 服務及本機通訊埠。切換會改變共用工作區、資料庫及服務；先核對授權、目標、停止條件與回復計畫，與所有使用者協調暫停 `bd`，直到驗收或退回結束。

本技能適用 Linux 上可執行 systemd user service 的 embedded 工作區。只想查詢 Beads、單次排鎖不影響工作、沒有足夠資源維護常駐服務、無法暫停所有相關程序或缺少回復授權時，不做切換。macOS 未驗證。效益、資源代價及程序可見性的限制見 [decisions.md](references/decisions.md)。

## 操作路徑

1. 閱讀 [runbook.md](references/runbook.md)，確認執行帳號、程式版本、權限與隔離前提。
2. 根據 [target.example.json](assets/target.example.json) 建立該 repo 的設定檔；主機、帳號、真實路徑、資料庫、服務、群組和執行檔由操作者填入。不要修改既有目標的權限來通過檢查。
3. 下載並核對官方 digest 後安裝 Dolt，再預覽並核對沒有遺漏任何 `bd`、Git hook 或背景程序。以不覆蓋方式安裝 unit。
4. 取得資料庫異動和服務操作所需授權後，依手冊以 `--apply --reviewed` 切換。保存操作紀錄，逐項驗收後才恢復使用。
5. 不一致或中斷時停止其他程序，依寫入狀態選擇立即退回或事後退回。資料、鎖與備份保留；檢查點不符時停止。

腳本及 systemd 範本只隨技能提供，不會自行安裝或啟動服務。Docker 測試中的 systemctl 替身不等於真實 systemd 驗收。
