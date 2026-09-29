# Claude Code runtime profile

本 profile 說明 Claude Code 的設定位置、綁定方式與安全限制。實際模型與 effort 見
[Harness 綁定對照表](bindings.md#claude-code) 的 `claude-code` 節；本檔不寫模型名稱。
使用前先核對本次需要的角色、模型、effort 與 runtime 實際回報；角色代號是設定契約，
不代表目前環境已安裝。

## 已驗證基線

| 項目 | 值 | 證據 |
|------|----|------|
| Claude Code | `2.1.284` | `claude --version` |
| 角色檔位置 | 專案 `.claude/agents/*.md`；使用者 `~/.claude/agents/*.md` | 官方 Subagents 文件 |
| 角色檔格式 | YAML frontmatter 加 Markdown system prompt；必填 `name`、`description` | 同上 |
| `model` 欄位 | 接受 alias、完整 model ID 或 `inherit` | 同上 |
| `effort` 欄位 | `low`、`medium`、`high`、`xhigh`、`max`；覆蓋 session effort，可用值依模型而定 | 同上 |
| 檔案載入 | 已存在的 agents 目錄會在數秒內載入新增或修改；session 中才建立的第一個 agents 目錄要重啟才載入 | 同上 |
| 實際 model／effort | `/tasks`（v2.1.242+）列出 subagent 的模型，角色檔設有 `effort` 時一併列出；transcript 位於 `~/.claude/projects/<project>/<session>/subagents/agent-<id>.jsonl` | 同上 |

官方文件：<https://code.claude.com/docs/en/sub-agents>（2026-09-29 查核）。

本 profile 沒有驗證固定的同時派工上限。並行數依獨立工作數、專案限制與 runtime 實際狀況
決定，不自行假設上限。subagent 預設最多往下巢狀三層，可由
`CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH` 調整。

## 主 session 由使用者選擇

使用者以 `/model` 與 effort 設定選擇主 session。Router 沿用當前選擇，不修改主 session、
使用者層或專案層設定。主 session 持續負責範圍、批准、整合與最後判斷；能力不足時依下表派出
所需工作代理，不讓較低能力的主模型獨自承擔必要的高風險判斷。

## 能力綁定

| Tier／用途 | Claude Code subagent | 使用限制 |
|------------|----------------------|----------|
| `light` | `light_worker` | 只做規則固定、可重複的工作；遇到第一個例外就停止 |
| `standard` | `standard_builder` | 只在設計、檔案範圍與驗收已定時實作 |
| `frontier` | Lead | 保留主 session；處理範圍、架構、安全與整合，能力不足則派所需代理 |
| `expert` | `expert` | 複雜跨層分析；實作僅限另外交付的明確檔案與已批准驗收 |
| fresh review | `reviewer` | 全新 context；高風險時還必須以工具白名單證明唯讀 |
| direction reanalysis | `reanalyst` | 同題三輪方向誤判後，全新 context 只讀重新分析一次；不實作 |

每個 subagent 的 `model` 與 `effort` 取自對照表 `claude-code` 節。`expert` 仍須通過通用
Router 的派工條件；主 session 已是 `expert` 的模型時，只按獨立子題是否值得分工決定。

## 綁定方式

1. 先依通用 Router 決定 tier、shape 與 review，再套用本 profile。
2. 派出 named subagent 時只指定角色代號，不另外傳 Agent 工具的 `model` 參數。派工時的
   `model` 參數優先於角色檔 frontmatter，會讓對照表的綁定失效。
3. Agent 工具的派工參數只能選模型、不能設 effort，所以 effort 只能靠角色檔生效。缺少角色檔時，
   `light_worker`、`standard_builder` 與 `expert` 可用 `model` 參數做模型等價綁定，但必須先以
   `/tasks` 或 transcript 確認實際模型符合對照表，並記錄 `deviation=effort-unbound`；
   `reviewer` 與 `reanalyst` 必須有角色檔，不接受等價綁定。
4. 需要全新 context 時使用 named subagent，不使用 fork。fork 繼承整段對話、system prompt
   與模型，不是 fresh context。
5. named subagent 不可用時，主 Agent 可以直接完成低風險工作，或使用較高且已驗證的 tier；
   不得用較低 tier 替代必要判斷。

### 三次方向誤判的 Claude Code 條件

主模型條件與範例見[對照表](bindings.md#三次方向誤判的主模型條件)。Claude Code 上的
`reanalyst` 必須以 named subagent 啟動，角色檔的 `model`、`effort` 符合對照表
`claude-code` 節的 `reanalyst` 列，工具白名單符合下方唯讀證據，並以 `/tasks` 或 transcript
確認實際 model 與 effort。同題已啟動過一次、不滿三輪，或只有一般執行錯誤時，都不再派出。
缺少任一條件時回報缺項並停止；分析結果不是實作、外部寫入或恢復工作的批准。

角色檔範本與建立流程見 [Claude Code 專案設定引導](../references/claude-code-project-onboarding.md)。

在通用路由紀錄後另加一行 binding receipt，格式見[對照表](bindings.md#binding-receipt)：

```text
profile=claude-code binding=standard_builder model=<實際模型> effort=<實際 effort> deviation=none
```

## Reviewer 安全限制

角色檔的 `permissionMode` 不能當唯讀證據：主 session 處於 `bypassPermissions`、
`acceptEdits` 或 auto 模式時，subagent 沿用主 session 的模式，並忽略角色檔設定。提示文字
同樣不能證明唯讀。

高風險審查只接受以下證據：

- Reviewer 以 named subagent 啟動，不是 fork。
- `/tasks` 或 transcript 顯示對照表 `claude-code` 節 `reviewer` 列的 model 與 effort。
- 角色檔 `tools` 白名單只有 `Read`、`Grep`、`Glob`。`tools` 未列出的工具都會移除；
  白名單含 `Bash`、`Write`、`Edit`、`NotebookEdit`、`Agent` 或 MCP 工具時，不算唯讀。

Reviewer 需要 diff 或測試輸出時，由 Lead 放進交接訊息，或先寫成檔案供其讀取。任一證據無法
滿足時，將 fresh review 標成 unavailable，停止 `high / critical` 的完成聲明。低風險工作仍可
由 Lead 回查，但不得把它寫成 fresh review。`reanalyst` 適用同一組唯讀證據。

## 停止與降級

- `light_worker` 不可用：由 Lead 直接做機械工作、使用 `standard_builder`，或依綁定方式第 3 點
  做模型等價綁定，並記錄偏差。
- `standard_builder` 不可用：只有 Lead 具備所需判斷時才直接做，或依第 3 點做模型等價綁定；
  否則停止派工。
- `expert` 或 `reanalyst` 的模型、effort 或角色檔無法驗證：停止該派工並回報，不自動換弱模型。
- Reviewer 唯讀或 fresh context 無法驗證：停止高風險完成聲明。

不要自動建立或改寫 `.claude/agents/`、`settings.json` 或權限模式。profile 只描述可用
binding；專案 adapter 決定是否允許使用。
