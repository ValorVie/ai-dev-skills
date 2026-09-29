# ai-dev-skills

`ai-dev-skills` 是 ai-dev 的第一方 Agent Skills collection。每個 skill 都可以透過
[`skills`](https://github.com/vercel-labs/skills) CLI 單獨安裝，不需要安裝 ai-dev framework。

## 安裝

列出全部 skills：

```bash
npx skills add ValorVie/ai-dev-skills --list
```

互動式選擇並安裝：

```bash
npx skills add ValorVie/ai-dev-skills
```

互動式清單會將 20 個 skills 收在 `Ai Dev Skills` group。`skills@1.5.22` 可從
group 那一列整組選取；`skills@1.5.23` 以上另提供最上方的 `Select All`。展開
group 後仍可個別選擇。

只安裝指定 skill：

```bash
npx skills add ValorVie/ai-dev-skills --skill custom-agent-router
```

ai-dev 使用者不需要逐一執行這些命令。ai-dev 的 `npx-skills` phase 會依明確清單安裝及更新 baseline skills。

## Skills

- `cloud-infrastructure-security`
- `custom-agent-router`
- `simplify`
- `custom-skill-creator`
- `custom-skills-dev`
- `custom-skills-doc-updater`
- `custom-skills-doc-writer`
- `custom-skills-ecc-analyze`
- `custom-skills-git-commit`
- `custom-skills-notify`
- `custom-skills-plan-analyze`
- `custom-skills-threads-research`
- `custom-skills-tool-overlap-analyzer`
- `custom-skills-upstream-ops`
- `discuss-multi-ai`
- `eli5`
- `first-principles`
- `safe-run`
- `wiki`
- `work-log-claude`

## 安裝邊界

`npx skills` 只安裝選定的 skill 目錄。Claude Code plugins、hooks、commands、agents 與 ai-dev framework 不會隨之安裝。需要 companion integration 的 skill 會在自己的 `SKILL.md` 提供獨立入口。

## 驗證

```bash
python tests/validate_skills.py
python -m pytest tests/test_custom_agent_router_contract.py skills/work-log-claude/tests
DISABLE_TELEMETRY=1 npx --yes skills@1.5.22 add . --list
```

validator 會檢查 canonical ID、目錄名稱、必要 frontmatter、plugin collection
清單、相對連結、generated files 與公開邊界。`.claude-plugin/plugin.json` 必須明確
列出全部 canonical IDs，讓 `npx skills` 顯示可整組選取的 collection。

## 維護原則

- `skills/<name>/` 必須與 `SKILL.md` frontmatter 的 `name` 相同。
- skill 的主要流程必須 self-contained；必要 scripts、references、assets、templates、evals 與直接測試放在 skill 目錄內。
- 新增 skill 不代表它會自動進入 ai-dev baseline。baseline 另由 ai-dev repository 的明確清單管理。
- 公開內容不得包含內部品牌、repository、host、帳號、credential 位置、private path 或組織專用流程。

## 來源

初始 snapshot 來自 `ValorVie/custom-skills` commit
`56953acf0709f6841d52ded85bc0e67d52cb540a`，並在首次發布前完成公開邊界清理。

## License

MIT。個別 skill 若有額外授權或來源說明，以該目錄內文件為準。
