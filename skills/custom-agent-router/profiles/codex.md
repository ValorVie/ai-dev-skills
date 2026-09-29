# Codex runtime profile

本 profile 說明 Codex 的設定位置、綁定方式與安全限制。實際模型與 effort 見
[Harness 綁定對照表](bindings.md#codex) 的 `codex` 節；本檔不寫模型名稱。使用前先核對
本次需要的角色、模型、effort 與 runtime metadata；角色代號是設定契約，不代表目前環境已安裝。

## 已驗證基線

| 項目 | 值 | 證據 |
|------|----|------|
| Codex CLI | `0.154.0` | `codex --version` |
| Multi-agent | 現行版本預設可用，且本機 `multi_agent` stable | Codex 官方 Subagents 文件、`codex features list` |
| Session 上限 | 最多 15 threads | `.codex/config.toml` 的 `max_concurrent_threads_per_session = 15` |

15 是上限，不是預設派工數。實際並行數取 runtime 剩餘 slot、專案限制與獨立工作數的
最小值。

## 主 session 由使用者選擇

使用者依任務自行選擇主 session 的模型與 effort。Router 沿用當前選擇，不修改主 session、
使用者層或專案層的模型設定，也不因主模型較強或較弱就另建 Lead。主 session 持續負責範圍、
批准、整合與最後判斷；能力不足時依下表派出所需工作代理，不讓較低能力的主模型獨自承擔
必要的高風險判斷。

## 能力綁定

| Tier／用途 | Codex role | 使用限制 |
|------------|------------|----------|
| `light` | `light_worker` | 只做規則固定、可重複的工作；遇到第一個例外就停止 |
| `standard` | `standard_builder` | 只在設計、檔案範圍與驗收已定時實作 |
| `frontier` | Lead | 保留主 session；處理範圍、架構、安全與整合，能力不足則派所需代理 |
| `expert` | `expert` | 複雜跨層分析；實作僅限另外交付的明確檔案與已批准驗收 |
| fresh review | `reviewer` | 使用全新 context；高風險時還必須證明 sandbox 與 filesystem 唯讀 |
| direction reanalysis | `reanalyst` | 同題三輪方向誤判後，全新 context 只讀重新分析一次；不實作 |

每個 role 的 model 與 effort 取自對照表 `codex` 節。這不是所有任務都必須派代理，也不保證
相同 token 用量。`expert` 仍須通過通用 Router 的派工條件；主 session 已是 `expert` 的模型時，
也只按獨立子題是否值得分工決定，不機械式重複派出同能力代理。

## 綁定方式

1. 先依通用 Router 決定 tier、shape 與 review，再套用本 profile。
2. 只有 runtime 的 custom role 清單與 metadata 符合對照表時，才使用 named role。
3. 缺少本次角色時，若 runtime 支援精確 model／effort override，可用等價綁定，並在
   交接中完整保留該角色的權限與停止條件。重新分析使用 `fork_turns="none"` 或可證明
   等價的全新上下文，並驗證回報的模型／effort；不只憑角色名稱或請求參數宣稱成功。
4. named role 不可用時，主 Agent 可以直接完成低風險工作，或使用較高且已驗證的
   tier；不得用較低 tier 替代必要判斷。

### 三次方向誤判的 Codex 條件

主模型條件與範例見[對照表](bindings.md#三次方向誤判的主模型條件)。Codex 上的
`reanalyst` 必須是全新 context（`fork_turns="none"` 或可證明等價），且 runtime metadata
回報的 model 與 effort 符合對照表 `codex` 節的 `reanalyst` 列。同題已啟動過一次、不滿三輪，
或只有一般執行錯誤時，都不再派出。沒有對應模型／effort、全新 context 或允許範圍內的唯讀
能力時，回報缺項並停止；既有停止條件若禁止調查，先等使用者決定。分析結果不是實作、
外部寫入或恢復 goal 的批准。

新專案設定使用現行 Codex standalone custom agent 格式：角色檔放在
`.codex/agents/*.toml`，每個檔案自行宣告 `name`、`description` 與
`developer_instructions`。不要替新專案產生舊式 `[agents.<name>] config_file` registry；
遇到既有舊式設定時，只在 runtime 已成功載入並可驗證的情況下沿用，不為了 onboarding
自動遷移。完整互動與範本見
[Codex 專案設定引導](../references/codex-project-onboarding.md)。

在通用路由紀錄後另加一行 binding receipt，格式見[對照表](bindings.md#binding-receipt)：

```text
profile=codex binding=standard_builder model=<實際模型> effort=<實際 effort> deviation=none
```

## Reviewer 安全限制

先前在 Codex 0.146.1 觀察到：從可寫 parent 直接啟動唯讀審查角色時，角色檔的
`sandbox_mode = "read-only"` 不一定能覆蓋 parent 權限。提示文字與
`approval_policy = "never"` 都不能證明唯讀。
這是已知限制，不是宣稱目前版本已修復。`reanalyst` 也必須核對實際唯讀限制；
無法證明時停止派工，不只靠提示文字限制寫入。

高風險審查只接受以下證據：

- Reviewer 是全新 context。
- Reviewer 的 runtime metadata 顯示對照表 `codex` 節 `reviewer` 列的 model 與 effort。
- parent 與 child 的 sandbox、managed filesystem permissions 都是唯讀。

目前已驗證的路徑是從獨立 read-only 主 session 啟動 `reviewer`。若做不到，將
fresh review 標成 unavailable，停止 `high / critical` 的完成聲明。低風險工作仍可
由 Lead 回查，但不得把它寫成 fresh review。

## 停止與降級

- runtime slot 少於設定值：使用較低上限，不等待或建立隱藏佇列。
- `light_worker` 不可用：由 Lead 直接做機械工作，或使用 `standard_builder` 並記錄偏差。
- `standard_builder` 不可用：只有 Lead 具備所需判斷時才直接做；否則停止派工。
- `expert` 或 `reanalyst` 的模型、effort 或角色／等價綁定無法驗證：停止該派工並回報，
  不自動換弱模型。
- Reviewer 唯讀或 fresh context 無法驗證：停止高風險完成聲明。

不要自動重寫 `.codex/config.toml`、建立新 role 或放寬 sandbox。profile 只描述可用
binding；專案 adapter 決定是否允許使用。
