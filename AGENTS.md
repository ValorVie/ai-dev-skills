# Agent instructions

## Language

預設以繁體中文回應與撰寫文件。技術識別字、命令、路徑、API、設定鍵與產品名稱保留原文。

## Scope

本 repository 只維護可由 `npx skills` 安裝的第一方 skills 與其驗證。ai-dev CLI、copy/distribution、commands、agents、plugins 與 project-template 留在 `ValorVie/custom-skills`。

## Change rules

- 先讀取目標 skill 的 `SKILL.md`、references、scripts、assets、evals 與 tests，再修改。
- 只改與需求直接相關的 skill；不順手重構其他 skill。
- 目錄名必須與 frontmatter `name` 相同，且 canonical IDs 不得重複。
- 每個 skill 必須 self-contained。主要流程需要的檔案不得透過相對路徑逃出 skill root。
- companion plugin、hook、command 或 agent 必須標成獨立安裝，不得宣稱由 `npx skills` 一起安裝。
- 不加入 npm package、自訂 registry、第二種 lock format 或自製 installer。

## Public boundary

所有 tracked files 都是公開內容。不得加入內部品牌、repository、host、帳號、project ID、credential 位置、private path、secret 或組織專用維運流程。提交前檢查本輪 diff 與 staged diff，測試資料也適用。

## Validation

修改後至少執行：

```bash
python tests/validate_skills.py
DISABLE_TELEMETRY=1 npx --yes skills@1.5.22 add . --list
```

若 skill 有直接測試或 validator，必須一併執行。驗證通過不代表已發布、已安裝到使用者環境或已被 ai-dev baseline 採用。

## Git

只提交本輪範圍，不夾帶其他工作。未取得明確批准前不得 push、建立 release 或改動 remote 設定。
