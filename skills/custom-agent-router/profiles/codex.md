# Codex runtime profile

本 profile 定義 Codex 的模型對應。使用前先核對本次需要的角色、模型、effort 與
runtime metadata；下方角色名是設定契約，不代表目前環境已安裝。

## 已驗證基線

| 項目 | 值 | 證據 |
|------|----|------|
| Codex CLI | `0.154.0` | `codex --version` |
| Multi-agent | 現行版本預設可用，且本機 `multi_agent` stable | Codex 官方 Subagents 文件、`codex features list` |
| Session 上限 | 最多 15 threads | `.codex/config.toml` 的 `max_concurrent_threads_per_session = 15` |

15 是上限，不是預設派工數。實際並行數取 runtime 剩餘 slot、專案限制與獨立工作數的
最小值。

## 主 session 由使用者選擇

使用者可依任務選 Sol 或 Astra，並自行選擇 effort；嚴謹任務可採 `gpt-5.6-sol xhigh`。
Router 沿用當前選擇，不修改主 session、使用者層或專案層的模型設定，也不因主模型是
Astra 就另建 Sol Lead。主 session 持續負責範圍、批准、整合與最後判斷；能力不足時
依下表派出所需工作代理，不讓較低能力的主模型獨自承擔必要的高風險判斷。
Sol／Astra 是建議選擇，不是強制白名單。若現有主 session 已用 Terra／Luna，也不擅自
切換；依實際能力安排工作，並適用下方三次方向誤判的條件。

## 能力綁定

| Tier／用途 | Codex binding | 模型與 effort | 使用限制 |
|------------|---------------|---------------|----------|
| `light` | `luna_worker` | `gpt-5.6-luna max` | 只做規則固定、可重複的工作；遇到第一個例外就停止 |
| `standard` | `terra_builder` | `gpt-5.6-terra max` | 只在設計、檔案範圍與驗收已定時實作 |
| `frontier` | Lead | 使用者所選主模型與 effort | 保留主 session；處理範圍、架構、安全與整合，能力不足則派所需代理 |
| `expert` | `astra_expert` | `gpt-6-astra high` | 複雜跨層分析；實作僅限另外交付的明確檔案與已批准驗收 |
| fresh review | `sol_reviewer` | `gpt-5.6-sol xhigh` | 使用全新 context；高風險時還必須證明 sandbox 與 filesystem 唯讀 |
| direction reanalysis | `astra_reanalyst` | `gpt-6-astra xhigh` | 同題三輪方向誤判後，全新 context 只讀重新分析一次；不實作 |

`light` 與 `standard` 使用不同模型，兩者 effort 都保留 `max`。這不是所有任務都必須
派代理，也不保證相同 token 用量。`expert` 仍須通過通用 Router 的派工條件；主 session
已用 Astra 時，也只按獨立子題是否值得分工決定，不機械式重複派出同能力代理。

## 綁定方式

1. 先依通用 Router 決定 tier、shape 與 review，再套用本 profile。
2. 只有 runtime 的 custom role 清單與 metadata 符合上表時，才使用 named role。
3. 缺少本次角色時，若 runtime 支援精確 model／effort override，可用等價綁定，並在
   交接中完整保留該角色的權限與停止條件。重新分析使用 `fork_turns="none"` 或可證明
   等價的全新上下文，並驗證回報的模型／effort；不只憑角色名稱或請求參數宣稱成功。
4. named role 不可用時，主 Agent 可以直接完成低風險工作，或使用較高且已驗證的
   tier；不得用較低 tier 替代必要判斷。

### 三次方向誤判的 Codex 條件

依 [通用計數與停止規則](../SKILL.md#同題三次方向誤判) 執行；只在主 session 的實際模型
已確認為 `gpt-5.6-sol`、`gpt-5.6-terra` 或 `gpt-5.6-luna` 時啟動 `astra_reanalyst`。
別名須先由 runtime metadata 確認對應模型；未知模型不得靠字串排序猜測能力。
主模型已是 `gpt-6-astra` 時，不論其 effort 為何，都不套用此特例。

這次重新分析固定 `gpt-6-astra xhigh`，不沿用一般跨層工作的 `high`，也不繼承較低主模型。
同題已啟動過一次、不滿三輪，或只有一般執行錯誤時，都不再派出。
沒有 Astra/xhigh、全新 context 或允許範圍內的唯讀能力時，回報缺項並停止；既有停止
條件若禁止調查，先等使用者決定。分析結果不是實作、外部寫入或恢復 goal 的批准。

| 主 session 與證據 | 結果 |
| --- | --- |
| Sol；同題三輪反證，中間換過代理 | 一次 `astra_reanalyst`，Astra/xhigh，全新 context、只讀 |
| Terra；同題只有兩輪反證 | 不觸發特例，沿用原路由與停止條件 |
| Luna；三個測試失敗但沒有方向反證 | 方向誤判計數為零，不觸發特例 |
| Astra/low；同題三輪反證 | 不觸發此主模型條件，不自動加開 Astra/xhigh |
| Sol；已啟動過同題重新分析 | 不再派第二個，無解則回交使用者 |
| Sol；已滿三輪但 Astra/xhigh 不可用或調查未獲准 | 停止並回報，不降級、不擴權 |

新專案設定使用現行 Codex standalone custom agent 格式：角色檔放在
`.codex/agents/*.toml`，每個檔案自行宣告 `name`、`description` 與
`developer_instructions`。不要替新專案產生舊式 `[agents.<name>] config_file` registry；
遇到既有舊式設定時，只在 runtime 已成功載入並可驗證的情況下沿用，不為了 onboarding
自動遷移。完整互動與範本見
[Codex 專案設定引導](../references/codex-project-onboarding.md)。

在通用路由紀錄後另加一行 binding receipt：

```text
profile=codex binding=terra_builder model=gpt-5.6-terra effort=max deviation=none
```

`deviation` 使用 `none`，或簡短記錄實際偏差，例如 `lead-direct-no-light-role`。這一行
只記錄 runtime 綁定，不改變通用 route receipt 的欄位。

## Reviewer 安全限制

先前在 Codex 0.146.1 觀察到：從可寫 parent 直接啟動 `sol_reviewer` 時，角色檔的
`sandbox_mode = "read-only"` 不一定能覆蓋 parent 權限。提示文字與
`approval_policy = "never"` 都不能證明唯讀。
這是已知限制，不是宣稱目前版本已修復。`astra_reanalyst` 也必須核對實際唯讀限制；
無法證明時停止派工，不只靠提示文字限制寫入。

高風險審查只接受以下證據：

- Reviewer 是全新 context。
- Reviewer 的 runtime metadata 顯示 `gpt-5.6-sol xhigh`。
- parent 與 child 的 sandbox、managed filesystem permissions 都是唯讀。

目前已驗證的路徑是從獨立 read-only 主 session 啟動 `sol_reviewer`。若做不到，將
fresh review 標成 unavailable，停止 `high / critical` 的完成聲明。低風險工作仍可
由 Lead 回查，但不得把它寫成 fresh review。

## 停止與降級

- runtime slot 少於設定值：使用較低上限，不等待或建立隱藏佇列。
- `luna_worker` 不可用：由 Lead 直接做機械工作，或使用 `terra_builder` 並記錄偏差。
- `terra_builder` 不可用：只有 Lead 具備所需判斷時才直接做；否則停止派工。
- 必要的 Astra 模型、effort 或角色／等價綁定無法驗證：停止該派工並回報，不自動換弱模型。
- Reviewer 唯讀或 fresh context 無法驗證：停止高風險完成聲明。

不要自動重寫 `.codex/config.toml`、建立新 role 或放寬 sandbox。profile 只描述可用
binding；專案 adapter 決定是否允許使用。
