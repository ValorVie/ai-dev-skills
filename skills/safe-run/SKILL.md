---
name: safe-run
description: |
  為 AI 開發與維運工作選擇安全的執行邊界：在 Codex、Claude Code 或其他 harness 原生沙盒，與 OpenShell 隔離 worker 之間路由。適用於工作同時可能涉及 host 真實狀態、程式碼修改、跨系統 API、憑證、長時間自主執行或多 agent；也適用於判斷一個任務應留在 host-aware 原生沙盒、移入 OpenShell，或拆成兩階段。使用 OpenShell 路徑前，必須確認 NVIDIA/OpenShell skills 已安裝。
---

# Safe Run

把 AI 工作先分類成「理解這台機器」或「完成一份工作」，再選擇最小、最清楚的安全邊界。

本 Skill 不取代 Codex、Claude Code、其他 harness 的原生 sandbox，也不把所有工作強制移入 OpenShell。目標是避免兩種錯誤：

- 為了隔離，把需要真實 host 狀態的除錯工作塞進容器，最後靠大量 bind mount 補洞。
- 為了方便，把長時間自主、跨 API、帶 credential 的 worker 直接放在真實 host 上。

## 核心模型

```text
                         AI task
                            |
               +------------+------------+
               |                         |
      工作物件是「這台機器」？       工作物件是「一份任務」？
               |                         |
              yes                       yes
               |                         |
               v                         v
   Codex / Claude Code /             OpenShell
   當前 harness 原生沙盒               isolated worker
               |                         |
      host-native filesystem        cloned/copied workspace
      host runtime / logs           scoped network/API
      host process state            brokered credentials
               |                         |
               +------------+------------+
                            |
                    若同時需要兩者
                            |
                            v
                    split into phases
```

## 路由原則

先問：

> 這個 AI 的主要工作物件，是「目前這台 host 的真實狀態」，還是「一個可以獨立封裝、完成後丟棄的 task」？

### Route A：harness 原生沙盒

選擇 Codex、Claude Code 或當前 harness 的原生 sandbox，條件包括：

- 需要直接讀取 host 的 `/etc`、`/var/log`、`/proc`、`/sys`、package 狀態、systemd、socket 或 process state。
- 需要同時理解 repo 與實際部署環境。
- 使用者正在互動式 debug，且會即時監督操作。
- 工作的主要價值來自「看到真實 host」，不是建立乾淨 worker。
- 可以用原生 sandbox 做「大範圍唯讀 + 少量明確可寫路徑」。

不要把「原生沙盒」等同於特定技術。使用當前 harness 在目前 OS 上實際提供的機制：

- Codex：使用 Codex 原生 sandbox。
- Claude Code：使用 Claude Code 原生 sandbox。
- 其他 harness：只有在能驗證其原生 sandbox 能力時才使用；不能只因名稱或文件宣稱而假設存在。

典型形狀：

```text
Host
 |
 +-- real /etc
 +-- real /var/log
 +-- real runtime/process state
 +-- real repo
       |
       v
Codex / Claude Code / harness
       |
       v
native sandbox
       |
       +-- host-wide read as needed
       +-- explicit writable workspace
       +-- dangerous mutation denied or approval-gated
```

### Route B：OpenShell isolated worker

選擇 OpenShell，條件包括：

- 工作可以從 repo、artifact、task description 或明確輸入重建。
- AI 要長時間自主執行，沒有人持續盯著。
- 需要跨 Git hosting、cloud API、CI、issue tracker、artifact registry、internal API 等多個外部系統。
- 需要 credential，但不希望 agent process 直接持有真正 credential。
- 需要明確控制 egress、API method/path、provider、credential destination。
- 需要同時跑多個 worker，彼此 filesystem 與生命週期隔離。
- 完成後希望直接 destroy worker，不留下 host runtime 污染。

典型形狀：

```text
Task / Issue / Queue
        |
        v
   Orchestrator
        |
        v
    OpenShell
        |
   +----+----+
   |         |
 Codex    Claude Code
   |         |
   +----+----+
        |
 isolated workspace
        |
 +------+------+------+
 |             |      |
Git hosting   Cloud   Internal API
 policy       policy  policy
```

在 OpenShell 路徑中，OpenShell 是主要的外部 capability boundary。不要依賴某個 harness 的內建 approval 來代表整體安全邊界。

### Route C：混合任務

如果任務同時需要：

- 真實 host 狀態；
- isolated worker；
- 外部 API / credential；
- 長時間 autonomous execution；

不要直接把整台 host bind mount 到 OpenShell。

優先拆成：

```text
Phase 1: host-aware investigation
        |
        v
harness native sandbox
        |
        +-- read logs
        +-- inspect config
        +-- inspect runtime/process
        +-- extract minimal evidence
        |
        v
bounded evidence / artifact
        |
Phase 2: task execution
        |
        v
OpenShell worker
        |
        +-- clone/copy repo
        +-- modify
        +-- test
        +-- call approved APIs
        +-- create patch/branch/PR
```

只有當 Phase 2 必須持續讀取 live host data，而且無法用 snapshot、log export、API 或明確 artifact 取代時，才考慮 OpenShell explicit read-only bind mount。

## OpenShell 前置閘門

只要路由結果需要 OpenShell，在執行任何 OpenShell setup、policy、provider 或 sandbox command 前：

1. 先確認目前 harness 能讀取 NVIDIA OpenShell 的 skills。
2. 若無法證明已安裝，執行：

```bash
npx skills add NVIDIA/OpenShell
```

3. 安裝後，先讀取與本次工作相關的 NVIDIA/OpenShell skill，再產生或修改 OpenShell policy。
4. 不把 NVIDIA/OpenShell skills 視為本 Skill 隨附內容；這是獨立安裝的 upstream dependency。
5. 如果無法安裝或無法讀取 upstream skill，不要憑記憶猜 OpenShell 的最新 policy schema 或 CLI 參數；停止在設計/規劃層，或改走不依賴 OpenShell 的路徑。

## Harness 原生沙盒閘門

走 Route A 前：

1. 確認當前 harness 與 OS。
2. 確認該 harness 的原生 sandbox 目前真的啟用。
3. 確認至少能表示：
   - 需要的 read scope；
   - writable workspace；
   - network boundary；
   - 必要的 approval / escalation。
4. 若原生 sandbox 不存在、被停用、或無法滿足最小邊界，不要假裝安全；改用 OpenShell、Docker/VM 隔離，或停止高風險 mutation。

不要把 `bubblewrap` 寫成跨平台前提。Linux、macOS、Windows 的原生機制不同，路由只依「harness 是否能在目前平台提供所需 boundary」判斷。

## 判斷矩陣

| 任務特徵 | Harness 原生沙盒 | OpenShell |
|---|---:|---:|
| 讀真實 host `/etc` / logs / process | **優先** | 不優先 |
| 互動式系統 debug | **優先** | 不優先 |
| 單一 repo、使用者在旁監督 | **優先** | 可選 |
| isolated disposable coding worker | 可用 | **優先** |
| 長時間 autonomous task | 不優先 | **優先** |
| 多 worker 平行 | 有限 | **優先** |
| 多外部系統 API | 可做但分散 | **優先** |
| credential 不可暴露給 agent | harness-specific | **優先** |
| API method/path 細粒度限制 | harness-specific | **優先** |
| 需要直接理解 host runtime | **優先** | 除非明確 RO bind |
| 完成後整個環境可丟棄 | 普通 | **優先** |

## 快速決策

按順序判斷：

1. **需要 live host state 嗎？**
   - 是 → Route A。
   - 否 → 下一題。

2. **工作能從明確輸入重建嗎？**
   - 否 → Route A 或先做 Route A 取證。
   - 是 → 下一題。

3. **是否長時間自主、跨多外部系統、需要 credential 或多 worker？**
   - 是 → Route B。
   - 否 → 原生 sandbox 通常更簡單。

4. **兩邊條件都成立？**
   - 拆 Route C，不先做大範圍 host bind。

## 典型案例

### 系統故障分析

```text
「分析目前這台 server 的 Nginx / runtime / logs，找出 timeout 根因」
```

路由：

```text
native-sandbox
```

理由：真實 host 就是工作物件。

### 互動式 code change

```text
「修改目前 repo，跑測試，我在旁邊看結果」
```

路由：

```text
native-sandbox
```

理由：單一 workspace、互動監督、原生 sandbox 成本最低。

### Issue 到 PR

```text
「收到 issue 後自動 clone、修改、測試、push branch、開 PR」
```

路由：

```text
openshell
```

理由：task-isolated、可重建、需要 Git provider 與長時間自主執行。

### 跨系統調查後修正

```text
「先看 staging host 的實際 logs 與 config，再修 repo 並呼叫 Git / cloud API」
```

路由：

```text
native-sandbox -> evidence -> openshell
```

理由：調查階段需要 host-native view；實作階段適合 isolated capability boundary。

## OpenShell 使用原則

路由到 OpenShell 後：

- workspace 預設獨立建立，不預設 expose host filesystem。
- provider / credential 使用 OpenShell 的機制，不直接把長期 secret 丟進 agent environment。
- egress 與 API scope 只開本 task 需要的最小集合。
- host bind mount 預設不用；若必要，優先 read-only，且明確列出 source、target、理由與移除條件。
- 不把 production mutation 權限和一般 coding 權限放在同一 worker。
- worker 完成後保留必要 artifact / commit / logs，再停止或刪除 sandbox。

## 不要這樣做

### 不要為了統一而統一

```text
所有 Codex / Claude Code
        |
        v
    OpenShell
        |
        v
大量 host bind mounts
```

這會同時失去 host-native debug 的簡潔性與 isolated worker 的乾淨邊界。

### 不要把原生 approval 當成 autonomous worker 的完整邊界

Codex、Claude Code 或其他 harness 的 approval 對互動式工作很好，但跨系統 autonomous worker 仍應有獨立的 network、credential、API capability boundary。

### 不要用 OpenShell 模擬整台真實 host

如果工作核心是理解現有 machine，優先使用 harness 原生 sandbox。OpenShell 的 explicit bind mount 是例外，不是預設架構。

## 路由輸出

需要明確記錄時，輸出一行：

```text
execution_boundary=native-sandbox reason=host-aware
```

或：

```text
execution_boundary=openshell reason=autonomous-cross-system
```

或：

```text
execution_boundary=split reason=host-investigation-plus-isolated-execution
```

若選 OpenShell，再補：

```text
openshell_skill=verified
```

只有已確認 NVIDIA/OpenShell skill 可讀取時才能標記 `verified`。
