# Harness 綁定對照表

本檔是 custom-agent-router 唯一記錄實際模型與 effort 的地方。`SKILL.md`、各 harness
profile 與設定引導只使用角色代號與佔位符；換模型、調整 effort 或新增 harness 時只改本檔，
新增 harness 時再補對應 profile。

角色代號與 tier／用途的對應定義在 [SKILL.md](../SKILL.md#harness-綁定)。表中值是設定契約，
不代表目前環境已安裝或 runtime 已提供；使用前仍依該 harness profile 核對。

## 讀法與佔位符

- 每個 harness 一節，節名就是 harness key，也是 binding receipt 的 `profile=` 值。
- 設定引導範本以 `{{<harness>.<角色代號>.model}}` 與 `{{<harness>.<角色代號>.effort}}`
  取值，例如 `{{codex.standard_builder.model}}`。套用範本時從下表代入，不另外寫死。
- `Lead` 是使用者所選的主 session 模型與 effort，Router 只讀回，不寫入設定。

## codex

| 角色代號 | model | effort |
|----------|-------|--------|
| `light_worker` | `gpt-5.6-luna` | `max` |
| `standard_builder` | `gpt-5.6-terra` | `max` |
| `expert` | `gpt-6-astra` | `high` |
| `reviewer` | `gpt-5.6-sol` | `xhigh` |
| `reanalyst` | `gpt-6-astra` | `xhigh` |

## claude-code

| 角色代號 | model | effort |
|----------|-------|--------|
| `light_worker` | `claude-sonnet-5-5` | `high` |
| `standard_builder` | `claude-opus-5-5` | `high` |
| `expert` | `claude-fable-5-1` | `high` |
| `reviewer` | `claude-opus-5-5` | `xhigh` |
| `reanalyst` | `claude-fable-5-1` | `xhigh` |

## 三次方向誤判的主模型條件

[通用計數與停止規則](../SKILL.md#同題三次方向誤判)累計達三輪時，只有在主 session 的實際
模型已由 runtime metadata 確認、出現在當前 harness 的表中，而且不是該 harness `reanalyst`
那一格的模型時，才啟動 `reanalyst`。別名須先確認對應模型；表中沒有的模型不得靠名稱或字串
排序猜測能力。主模型已是 `reanalyst` 的模型時，不論其 effort 為何，都不套用此特例。

重新分析固定使用 `reanalyst` 那一格的 model 與 effort，不沿用 `expert` 的 effort，也不繼承
較低的主模型。

| 主 session 與證據 | 結果 |
| --- | --- |
| 主模型是 `reviewer` 的模型；同題三輪反證，中間換過代理 | 一次 `reanalyst`，全新 context、只讀 |
| 主模型是 `standard_builder` 的模型；同題只有兩輪反證 | 不觸發特例，沿用原路由與停止條件 |
| 主模型是 `light_worker` 的模型；三個測試失敗但沒有方向反證 | 方向誤判計數為零，不觸發特例 |
| 主模型是 `reanalyst` 的模型，effort 較低；同題三輪反證 | 不觸發此主模型條件，不自動加開 `reanalyst` |
| 已啟動過同題重新分析 | 不再派第二個，無解則回交使用者 |
| 已滿三輪但 `reanalyst` 綁定不可用或調查未獲准 | 停止並回報，不降級、不擴權 |
| 主模型不在當前 harness 的表中 | 不觸發，回報未知模型 |

## Binding receipt

在通用路由紀錄後另加一行，記錄 runtime 實際回報的值：

```text
profile=<harness> binding=<角色代號> model=<實際模型> effort=<實際 effort> deviation=none
```

`deviation` 使用 `none`，或簡短記錄實際偏差，例如 `lead-direct-no-light-role`。這一行只記錄
runtime 綁定，不改變通用 route receipt 的欄位。

## 修改與新增

- 換模型或調整 effort：只改上面對應的表格列。已建立的專案角色檔不會自動更新，需依該
  harness 的設定引導重新核對差異。
- 新增 harness：新增一節同格式表格，建立 `profiles/<harness>.md` 說明設定位置、綁定方式、
  fresh context、唯讀證據與降級規則；需要專案設定引導時再加
  `references/<harness>-project-onboarding.md`，範本一律使用本檔佔位符。
- 不在本檔寫操作流程或安全限制；那些屬於各 harness profile。
