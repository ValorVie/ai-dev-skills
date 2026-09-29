---
name: custom-agent-router
description: |
  為目標、範圍與授權已明確的非簡單 Agent 工作選擇互動模式、能力層級、風險、派工形狀、審查與有限備援。適用於需要在主 Agent 直接處理、單一工作代理與有限平行之間選擇，或需要依複雜度與風險決定能力層級及審查強度的工作；目前 harness 的專案缺少已驗證的 Agent 設定時，也用本 Skill 引導使用者選擇建立、預覽或略過。簡單問答、唯讀確認與可直接驗證的小修改不要使用。
---

# Custom Agent Router

把已獲授權的工作映射成最小可行執行形狀。只選擇執行方式，不建立權限、任務追蹤器、
規格或新的工作流程。

## Harness 綁定

通用路由只使用 tier 與用途。每個 tier／用途對應一個跨 harness 共用的角色代號：

| Tier／用途 | 角色代號 |
|------------|----------|
| `light` | `light_worker` |
| `standard` | `standard_builder` |
| `frontier` | Lead（主 session） |
| `expert` | `expert` |
| fresh review | `reviewer` |
| direction reanalysis | `reanalyst` |

先完成通用路由，再讀取綁定：

1. [Harness 綁定對照表](profiles/bindings.md)：各 harness 每個角色代號的模型與 effort，
   是實際模型的唯一來源。
2. 當前 harness 的 profile：設定位置、綁定方式、fresh context、唯讀證據與降級規則。
   - Codex：[profiles/codex.md](profiles/codex.md)
   - Claude Code：[profiles/claude-code.md](profiles/claude-code.md)
3. 沒有已驗證 profile：保留抽象 tier，由主 Agent 使用現場可證明的能力，並記錄
   binding 偏差；不要猜測模型、effort、唯讀或 fresh-context 能力。

runtime profile 只能選擇實際模型與角色，不能改變 mode、risk、shape、批准或專案規則。
主 session 的模型與 effort 由使用者選擇；Router 只讀回，不為符合 profile 自動切換。

### 專案設定閘門

套用本 Skill 時，先依當前 harness profile 確認專案層 Agent 設定與 runtime metadata。
只核對本次路由需要的角色；若缺少必要設定且 runtime 也無法提供 profile 允許的等價能力，
讀取該 harness 的設定引導，說明目前能安全使用的降級能力，再詢問使用者要「建立建議設定」、
「只顯示建議」或「暫不設定」：

- Codex：[Codex 專案設定引導](references/codex-project-onboarding.md)
- Claude Code：[Claude Code 專案設定引導](references/claude-code-project-onboarding.md)

未取得使用者選擇前，不得建立或修改設定。若使用者略過，仍可完成通用路由，但要保留
抽象 tier，只使用現場能證明的能力並記錄 binding 偏差，不得把未驗證的 named role、
模型、effort、唯讀或 fresh-context 能力寫成已可用。

## 先確認邊界

1. 先讀取系統、使用者與專案規則。上層規則永遠優先。
2. 確認目標、允許範圍、驗收方式與停止條件足以執行。
3. 若缺少的資訊會改變結果、權限或風險，先詢問或做有限唯讀調查。
4. 沿用專案既有的任務追蹤器、Git、安全與批准規則，不建立第二套系統。
5. 只使用執行環境能證明存在的 Agent、sandbox、審查與並行能力，不依名稱猜測。

派工、重試或升級只能改變執行者，不能擴大檔案、工具、外部 mutation 或批准範圍。

## 路由順序

依序決定 `mode → tier → risk → shape → review → fallback`。風險控制批准與審查，
不直接決定 Agent 數量。

### 1. 選擇 mode

| Mode | 條件 | 下一步 |
|------|------|--------|
| `execute` | 結果、範圍與驗收清楚 | 直接執行，或交給最低可勝任的能力層級 |
| `explore_then_plan` | 方向清楚，但證據不足、跨元件或回復昂貴 | 做有限唯讀調查，形成一個可驗證工作切片 |
| `co_discover` | 問題、產品選擇或驗收仍不清楚 | 只釐清會改變方向的問題，搭配低成本探查 |

### 2. 選擇 tier

| Tier | 工作特徵 |
|------|----------|
| `light` | 搜尋、列舉、重現、測試、格式與規則固定的機械工作 |
| `standard` | 邊界清楚，但需要工程判斷的實作、除錯、整合與審查 |
| `frontier` | 歧義、架構、跨元件根因、安全、不可逆決策與最終仲裁 |
| `expert` | 複雜跨層問題，或需要獨立重查多輪錯誤假設與相互矛盾的證據 |

選擇最低可勝任的 tier。高 tier 可以暫代低 tier，但要在路由紀錄旁註明模型綁定偏差；
低 tier 不得替代必要的安全、架構或高風險判斷。實際模型與 effort 由執行環境設定
綁定，本 Skill 不指定產品模型名稱。

### 3. 套用 risk gate

| Risk | 典型條件 | 最低驗證 |
|------|----------|----------|
| `low` | 局部、可回復、驗收直接 | 執行者自測，主 Agent 回查 |
| `material` | 跨檔案或元件，或改變使用者可見行為 | 主 Agent 整合驗證；有明顯不確定性時使用全新上下文審查 |
| `high` | 資安、發布、外部狀態或回復昂貴 | 明確計畫與批准閘門；完成後使用全新上下文審查 |
| `critical` | 資料遺失、正式流量、不可逆或重大權限影響 | 停止自動執行，取得明確批准與獨立驗證 |

若工作包含資料庫或正式環境 mutation，先使用 `explore_then_plan / frontier / critical`。
批准只授權指定操作，不等於完成驗證。

### 4. 通過 dispatch brake

派工前逐項確認：

1. 每個工作代理的完成結果能用一句話說清楚。
2. 主 Agent 直接做不會更便宜可靠。
3. 工作不需要等待另一個工作代理才能前進。
4. 每個可寫工件只有一個負責者。
5. 已指定整合與最後驗證的負責者。

任一項不成立就維持 `direct`，或先調查到邊界清楚。通過後只使用三種形狀：

| Shape | 條件 |
|-------|------|
| `direct` | 小工作、緊密耦合問題，或方向仍需主 Agent 判斷 |
| `single_worker` | 一個邊界與驗收都清楚的獨立工作流 |
| `bounded_parallel` | 至少兩個已就緒工作彼此獨立，且寫入責任不重疊 |

使用 `single_worker` 或 `bounded_parallel` 時，派工說明至少包含：目標、允許寫入範圍、
不可觸碰範圍、輸入證據、驗收命令、停止條件與回傳格式。主 Agent 保留整合責任。

### 5. 選擇 review 與 fallback

- `low`：使用 `review=lead`，不為形式建立審查者。
- `material`：預設由主 Agent 整合驗證；跨模組、不確定性高或作者偏誤明顯時，
  使用 `review=fresh`。
- `high / critical`：完成聲明使用 `review=approval+fresh`。若執行環境無法證明全新
  上下文或唯讀能力，就停止完成聲明，不以自審冒充。
- 一般執行失敗先修正派工說明、證據或環境問題；需要時同一 tier 最多重試一次。
- 同原因再次失敗時最多升一個 tier。升級後仍失敗，或必要能力不可用，就交回主
  Agent 或使用者，不再自動重跑。

### 同題三次方向誤判

方向誤判是原先的根因判斷或修正方向，被後續可核對的證據推翻。每輪保存「原判斷、
反證、結果」；同一輪的多個失敗斷言只算一次。一般測試失敗、預期的 RED、命令錯誤、
網路或權限不足不計入；若它們另有證據推翻原判斷，才按該輪方向誤判計一次。

同一未解問題跨主／子代理累計，換代理、換方法或穿插其他工作不歸零；已解決的不同問題
不併計。沿用既有任務紀錄保存次數與證據，不新增計數程式或追蹤系統。

累計達三輪且主模型符合[對照表的主模型條件](profiles/bindings.md#三次方向誤判的主模型條件)時，
停止同題實作，設 `fallback=direction-reanalysis-once`，另派一個全新 context 的
`reanalyst` 重新分析。
只交付原目標、授權邊界、固定版本及三輪原判斷與反證，不把前代理的結論當成既定事實。
重新分析只讀取原本獲准的資料，回傳錯誤假設、證據、建議修正方向與仍未知項；不實作、
不改任務狀態、不自行恢復暫停的工作。同題最多啟動一次，結果由主 session 核對；仍無解
或診斷能力不可用就交回使用者，不再派第二個診斷代理，也不降級冒充。

這是一次獨立重新分析，不增加一般重試額度，也不要求刻意試滿三次。原有批准與安全
停止條件立即生效；若它們禁止繼續調查，就只記錄待分析原因，不啟動代理。

## 輸出路由紀錄

非簡單派工、能力升級或高風險直接執行都輸出一行：

```text
mode=execute risk=material tier=standard shape=single_worker owner=builder review=fresh fallback=one-tier-max
```

欄位只使用以下值：

| 欄位 | 值 |
|------|----|
| `mode` | `execute`、`explore_then_plan`、`co_discover` |
| `risk` | `low`、`material`、`high`、`critical` |
| `tier` | `light`、`standard`、`frontier`、`expert` |
| `shape` | `direct`、`single_worker`、`bounded_parallel` |
| `owner` | 負責交付的角色或 Agent 名稱 |
| `review` | `lead`、`fresh`、`approval+fresh` |
| `fallback` | `none`、`same-tier-once`、`one-tier-max`、`direction-reanalysis-once` |

路由紀錄只保存決策，不取代派工說明、測試證據、批准紀錄或任務狀態。簡單且直接
完成的工作不必為了格式輸出路由紀錄。

runtime profile 若要求 binding receipt，就放在 route receipt 下一行。binding receipt
只能補充實際角色、模型、effort 與偏差，不得覆寫通用路由結果。

## 固定回歸案例

| 案例 | 預期路由 |
|------|----------|
| 回答單一事實或唯讀確認 | `execute / light / low / direct / lead` |
| 邊界清楚的單一工程修改 | `execute / standard / material / single_worker / lead` |
| 兩個獨立且不寫同檔的盤點 | `execute / light / low / bounded_parallel / lead` |
| 需求與驗收仍有產品歧義 | `co_discover / frontier / direct` |
| 跨元件、證據不足但方向清楚 | `explore_then_plan / frontier / material / direct` |
| 複雜跨層，具備可獨立交付的子題 | `explore_then_plan / expert / material / single_worker / lead`；模型依 profile |
| 符合 profile 的主模型，同題累計三輪方向誤判 | 停止同題實作；全新 context 只讀重新分析一次，沿用原風險與批准邊界 |
| 資料庫或正式環境 mutation | `explore_then_plan / frontier / critical / approval+fresh` |
| 低能力層級不可用 | 記錄綁定偏差後升一層，或由主 Agent 直接處理 |
| 必要的全新上下文審查者不可用 | 停止高風險完成聲明，不以自審冒充 |

更換執行環境設定只能改變實際模型，不得改變 mode、risk、shape 或安全邊界。

## 停止條件

遇到以下任一情況就停止自動推進：

- 授權、範圍或驗收仍會改變路由結果。
- 需要的批准尚未取得。
- 執行環境無法證明必要能力。
- 派工後出現未預期的重疊寫入或外部狀態變更。
- 同一原因已用完一次同 tier 重試與一次 tier 升級：停止實作；只有符合上節且仍獲准的
  一次重新分析可以另行進行，不能藉此重新取得實作或重試額度。

不要建立排程器、佇列、Agent 登錄表、Hook、路由資料庫或通用任務追蹤器。只有真實
失敗證據顯示 Prompt 與執行環境原生能力不足時，才另案評估程式或 Hook。
