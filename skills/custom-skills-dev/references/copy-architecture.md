# ai-dev resource ownership reference

ai-dev 將「skill 安裝」與「framework 資源分發」分開。先判斷 owner，再選擇 npx 或 clone；同一 canonical skill ID 不得同時由兩者寫入。

## Pipeline

```text
ai-dev install
  │
  ├─ tools       更新必要 CLI tools
  ├─ repos       更新 framework 與保留的 upstream repositories
  ├─ npx-skills  依 upstream/npx-skills.yaml 安裝 skills
  └─ targets     分發非 npx-managed framework resources

ai-dev update
  │
  ├─ tools
  ├─ repos
  └─ npx-skills
```

`npx-skills` 在 `targets` 之前。fresh install 會先建立 skill installation，再分發 commands、agents、workflows 與 plugins。

## Ownership

| 資源 | Canonical source | Installer／writer |
| --- | --- | --- |
| ai-dev 第一方 global skills | `ValorVie/ai-dev-skills` | `npx skills` |
| manifest 中的第三方 global skills | 各公開 upstream | `npx skills` |
| ECC 白名單 skills | `~/.config/everything-claude-code/` | `ai-dev clone` + ManifestTracker |
| custom repo skills | `~/.config/ai-dev/repos.yaml` 註冊來源 | `ai-dev clone` + ManifestTracker |
| project-template repo-local skills | `custom-skills/project-template/` | project init/projection |
| commands、agents、workflows、plugins | `ValorVie/custom-skills` 或明確 upstream | `ai-dev clone`／原生 plugin manager |

## npx-managed skills

ai-dev 的 desired state 存在 `upstream/npx-skills.yaml`。npx global lock 是單一機器的實際安裝狀態，不取代 repository manifest。

規則：

- skill 必須以 frontmatter `name` 作為 canonical ID。
- baseline 必須逐項列出 skill names；不得用 wildcard 自動採用新內容。
- add command 依 repository 分組，對同一 package 傳入多個 `--skill`。
- npx 安裝成功並讀回驗證前，不得清理舊 copy ownership。
- clone prescan 若遇到 npx-managed canonical ID，必須跳過；另一來源同名時在寫入前停止。

### Agent paths

實際 global path 由目前安裝的 `skills` CLI 決定。ai-dev 只對已驗證 mapping 顯示具體操作指引：

| ai-dev target | npx agent | 主要路徑 |
| --- | --- | --- |
| `claude` | `claude-code` | `~/.claude/skills/` |
| `codex` | `codex` | 依目前 Codex/npx 設定解析 |
| `agy` | `gemini-cli` | `~/.gemini/skills/` |

Antigravity 或新 target 必須先探測實際讀取路徑。無法證明時採 fail closed，不猜測 agent ID。

## clone-managed resources

`ai-dev clone` 保留以下工作：

1. 分發 framework commands、agents、workflows 與 plugins。
2. 分發 `repos.yaml` 註冊的 custom repo resources。
3. 依 `upstream/distribution.yaml` 分發 ECC 白名單 resources。
4. 用 ManifestTracker 處理 clone-owned resource 的 hash、衝突與 orphan cleanup。

第一方 npx-managed skills 不加入 Stage 3 source config，也不寫入新的 target manifest。

## Migration boundary

舊版 target 可能仍有 `source=custom-skills` 的第一方 skill entries。一般 clone 不可直接將它們當 orphan 刪除；一次性 migration 必須依序完成：

```text
PREPARED → PUBLISHED → INSTALLED → VERIFIED → DETACHED
```

- target 與 stored base 不同時，保留內容並停止該 skill。
- canonical install 未通過時，保留舊 ownership。
- `custom-simplify → simplify` 只在新 canonical install 通過且舊路徑未修改時清理。

## 修改入口

| 需求 | 主要檔案 |
| --- | --- |
| 新增 baseline npx skill | `upstream/npx-skills.yaml`、`script/services/npx_skills/` |
| 調整 retained target resources | `script/utils/shared.py`、`script/services/targets/` |
| 調整 ECC whitelist | `upstream/distribution.yaml`、ECC specs/tests |
| 調整 list source labels | `script/utils/shared.py`、list tests |
| 調整 npx-managed toggle boundary | `script/commands/toggle.py`、resource-disable／standards tests |
| 修改第一方 skill content | `ValorVie/ai-dev-skills` |

修改後以 focused tests 驗證目標能力，再執行完整 repository suite。不要用 `npx skills` 成功取代 clone、migration 或使用者修改保護的驗證。
