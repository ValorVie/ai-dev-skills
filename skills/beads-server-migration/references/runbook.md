# Beads 伺服器模式操作手冊

本手冊處理單一 Linux repo：先準備 Dolt 並預覽，再把 embedded Dolt 移至本機 systemd user service；失敗時依資料是否變動退回。所有命令都在設定檔指定的**目標主機**，以指定的**執行帳號**執行。不要用 root 代替該帳號，也不要把容器測試當成真實 systemd 驗收。

## 操作前

取得切換、資料庫寫入、安裝與服務操作所需授權。切換期間停用所有使用該工作區的 `bd`，包括排程、代理、Git hooks 與其他 worktree；確認沒有人直接以另一帳號或改名的執行檔存取資料。核對 `/proc` 的可見性與掛載命名空間限制，見 [decisions.md](decisions.md)。如果無法確認或協調停用，停止。

準備 Python 3.14、`uv`、`bd`、Dolt、Git、`getfacl`、`setfacl`、`fuser` 或 `lsof`、`systemctl`、`curl`、`tar`。來源測試使用 bd 1.3.1、Dolt 2.6.x；其他版本先在隔離副本驗證。目標 `.beads` 和原內嵌根目錄須由執行帳號擁有、屬於設定的群組、模式 `2770`，且具有 default ACL（新檔繼承的權限）；保留所有既有檔的 owner、group、mode 和 ACL。若現場不同，停止並另定安全方案，不以 chmod／chown／setfacl 修改目標 `.beads` 硬闖。狀態目錄須與 `.beads` 同一檔案系統，且位於 `.beads` 和 `.cache` 之外。檢查磁碟可用空間；切換預檢要求資料大小三倍另加 1 GiB，事後退回另做空間檢查。

以目標主機的執行帳號，複製 [設定範例](../assets/target.example.json) 到私人工作位置並填好所有欄位。路徑必須是解析後的絕對路徑；systemd 工作目錄的 repo 路徑不可包含空白。`prefix` 是暫存 repo 初始化使用的前綴，須與 `database` 相同，確保初始化選到設定的資料庫；它不改寫目標既有 issue ID。`bd` 和 `dolt` 為可執行的實際檔案，名稱須分別為 `bd`／`dolt` 或其後接 `-` 的名稱，讓程序檢查可辨識。`docker_fixture` 對正式目標一律為 `false`。此檔不可在作業中改動；三個操作入口將設定雜湊與目標資訊綁到檢查點，退回與續跑必須用相同設定。

在目標主機、以執行帳號的 Bash 設定下列變數，實際路徑自行替換；每個後續程式都在同一個 shell 使用：

```bash
SKILL_ROOT=/path/to/beads-server-migration
TARGET_CONFIG=/path/to/target.json
PY=(uv run --offline --python 3.14 --no-project python -I -B)
```

讀回 hostname、帳號、repo 真實路徑、群組、資料庫、服務名稱及通訊埠，與設定檔逐項比對。確認 repo 的 `.beads.gate.lock` 已存在且能由執行帳號開啟；不得刪除或重建 gate 檔。目標 `.beads/.env` 或 `.beads/redirect`、選庫環境變數存在時先查明並排除。工具會拒絕已設定的選庫變數，包括空值，不顯示其值。

切換前整理 `.beads/config.yaml`：只使用簡單的單行純量與巢狀鍵值；頂層不可有 `sync:`，平鋪 `sync.remote:` 至多一行，且值須為非空的單行字串。工具無法判讀的格式及重複鍵會停止，請先整理並重新預覽。不得設定 `BD_SYNC_REMOTE` 或 `BD_SYNC_GIT_REMOTE`，避免環境變數覆寫暫存副本的本機遠端；工具不會修改來源設定。

## Dolt 下載與安裝

若已有與測試版本一致且核對過的 Dolt，可略過下載。安裝新檔須有授權；已存在的執行檔不可覆蓋。以下範例為 Linux amd64，`DOLT_TAG` 與目標路徑須依已驗證版本及設定檔調整。

在目標主機、以執行帳號下載官方 release 資訊與檔案到新建暫存目錄：

```bash
DOLT_TAG=v2.6.1
DOLT_DEST=/path/to/bin/dolt
STAGE=$(mktemp -d) || exit 1
curl -fLsS "https://api.github.com/repos/dolthub/dolt/releases/tags/$DOLT_TAG" -o "$STAGE/release.json" &&
curl -fLsS "https://github.com/dolthub/dolt/releases/download/$DOLT_TAG/dolt-linux-amd64.tar.gz" -o "$STAGE/dolt.tar.gz"
```

在目標主機、以執行帳號核對 GitHub release asset 的官方 `sha256:` digest 與下載檔；缺少或不一致即停止，不解壓或安裝：

```bash
"${PY[@]}" -c 'import hashlib,json,sys; d=json.load(open(sys.argv[1])); a=[x for x in d["assets"] if x["name"]=="dolt-linux-amd64.tar.gz"]; assert len(a)==1 and a[0].get("digest"," ").startswith("sha256:"); h=hashlib.file_digest(open(sys.argv[2],"rb"),"sha256").hexdigest(); assert a[0]["digest"]=="sha256:"+h; print("官方 digest 與下載檔一致")' "$STAGE/release.json" "$STAGE/dolt.tar.gz" &&
tar -xzf "$STAGE/dolt.tar.gz" -C "$STAGE" --strip-components=2 dolt-linux-amd64/bin/dolt
```

在目標主機、以執行帳號使用同目錄候選檔及不覆蓋的硬連結安裝。目的地若已存在或為符號連結就停止；候選檔或連結失敗時保留路徑並查明：

```bash
test ! -e "$DOLT_DEST" && test ! -L "$DOLT_DEST" &&
CANDIDATE=$(mktemp "${DOLT_DEST}.candidate.XXXXXX") &&
install -m 0755 "$STAGE/dolt" "$CANDIDATE" &&
ln -T -- "$CANDIDATE" "$DOLT_DEST" &&
cmp "$STAGE/dolt" "$DOLT_DEST" && "$DOLT_DEST" version &&
rm -- "$CANDIDATE"
```

保留下載檔、官方回應、digest 與版本紀錄至驗收完成。失敗時不要覆蓋目的地。清理暫存前先確認其確切路徑與沒有需要保留的證據。回復新安裝須先停用依賴此 Dolt 的服務，再依授權移除該新檔；替換既有檔要另定備份與回復方案。

## 第一次預覽

確認設定檔指定的 `bd` 與 Dolt 都已可執行。在目標主機、以執行帳號預覽；預覽不代表所有套用前置檢查已通過：

```bash
"${PY[@]}" "$SKILL_ROOT/scripts/switch.py" --config "$TARGET_CONFIG"
```

「退回程序可見性」未通過、目標不符、工具缺失或任何檢查不明時停止。預覽不啟動 `bd`；若目標已在 server 模式，還會讀取服務程序資訊。

## 建立狀態目錄與 user service

狀態目錄為本工作專用；預先確認其父目錄可信、位於相同檔案系統，且設定檔的 `state`、`group` 與下列值一致。目標已存在就停止，不覆蓋。

在目標主機、以執行帳號建立並讀回：

```bash
STATE=/path/to/migration-state
GROUP=example-team
mkdir -- "$STATE" && chgrp -- "$GROUP" "$STATE" && chmod 2770 "$STATE" &&
stat -c '%n %u:%g %a' "$STATE"
```

指定與設定檔 `service` 完全相同的 unit 路徑，先在同目錄建立候選，再以 `ln` 不覆蓋安裝。目錄須已存在並由執行帳號管理。若目的地或符號連結已存在，停止；任何中途失敗保留候選檔供核對。

在目標主機、以執行帳號安裝並讀回 unit：

```bash
UNIT="$HOME/.config/systemd/user/example-beads.service"
test ! -e "$UNIT" && test ! -L "$UNIT" &&
UNIT_CANDIDATE=$(mktemp "${UNIT}.candidate.XXXXXX") &&
"${PY[@]}" "$SKILL_ROOT/scripts/render-unit.py" --config "$TARGET_CONFIG" > "$UNIT_CANDIDATE" &&
chmod 0644 "$UNIT_CANDIDATE" && ln -T -- "$UNIT_CANDIDATE" "$UNIT" &&
cmp "$UNIT_CANDIDATE" "$UNIT" && rm -- "$UNIT_CANDIDATE" &&
systemctl --user daemon-reload && systemctl --user enable "${UNIT##*/}"
```

在目標主機、以執行帳號確認 service 是 `enabled` 且 `inactive`。若需要登出後仍持續執行，事先核對 user manager 的 linger 設定及適用授權。已安裝 unit 與設定生成內容不一致時，工具會停止。

```bash
systemctl --user is-enabled "${UNIT##*/}"
systemctl --user is-active "${UNIT##*/}"
```

## 切換與驗收

停妥所有相關 `bd`、完成備份與預覽並取得套用及資料庫寫入授權後，在目標主機、以執行帳號執行：

```bash
"${PY[@]}" "$SKILL_ROOT/scripts/switch.py" --config "$TARGET_CONFIG" --apply --reviewed
```

工具在隔離副本建立 Dolt commit、原生備份及伺服器還原；檢查資料表、結構、HEAD、staged、working 與分支指紋。原內嵌樹保留。保存輸出與狀態目錄的 `operations.log`；工具通過不等於使用者驗收通過。

繼續保持其他程序停止，於目標主機以執行帳號進入 repo，核對 `bd --readonly where --json` 與 `bd --readonly dolt show --json` 的工作區、資料庫、`127.0.0.1`、通訊埠與 `connection_ok`；再核對服務 `active`／`enabled`。以各實際使用帳號讀回同一筆資料；取得寫入授權後再寫入並由另一帳號讀回。驗證各 worktree 的 Git hook 實際呼叫 `bd` 並連到預期服務、驗證匯出與 `issues.jsonl` 新鮮度，以及實際的 `dolt.auto-commit`／`export.auto` 設定與環境覆寫。驗證使用者應在其自己的 shell 執行；shim 只換帳號時還須先切換工作目錄。未觀察到連線、任一帳號讀不到或資料不一致就停止並保留證據。

同時讀回 `export.git-add` 設定，並檢查各執行環境的 `BD_EXPORT_GIT_ADD` 覆寫；環境變數優先。此值為 `true` 時，符合匯出條件且未停用 Git 操作的 `bd` 會把匯出檔自動加入 Git 暫存區。提交前以 `git diff --cached` 檢查暫存內容。

取得適用的 Git 授權後，將切換後已核對的 `metadata.json` 納入提交。Dolt backup／restore 不帶 remotes，重新核對遠端；`dolt.auto-commit` 為 off 時，按授權執行 `bd dolt commit` 再同步。`bd dolt push` 的完整性檢查逾時時，查明原因，必要時提高 `BEADS_FSCK_TIMEOUT`，不要略過完整性檢查。

## 退回及再次切換

先停用所有相關 `bd`，保留狀態目錄、原樹、伺服器樹與備份。伺服器完整指紋未變時使用立即退回；資料已變時，立即退回會拒絕，使用事後退回。事後退回會在伺服器執行 `bd dolt commit`，須取得相應資料庫寫入授權。服務已停且資料已變時不要硬闖，先依現場回復計畫處理。

在目標主機、以執行帳號先預覽，確認適用授權後用相同模式套用。下例以立即退回為例；事後退回將兩行的 `--immediate` 改成 `--after-write`：

```bash
"${PY[@]}" "$SKILL_ROOT/scripts/rollback.py" --config "$TARGET_CONFIG" --immediate
"${PY[@]}" "$SKILL_ROOT/scripts/rollback.py" --config "$TARGET_CONFIG" --immediate --apply --reviewed
```

退回中斷時保持停用，使用相同設定與同一套用命令續跑；檢查點、檔案身分、完整指紋或權限漂移就停止。完成後讀回 embedded 工作區及服務 `inactive`／`disabled`。立即退回後若要再次切換，經授權先重新 enable unit。事後退回後，須在服務 `inactive`／`disabled` 時先封存保留原樹；`failed` 不是可封存的 `inactive`。

在目標主機、以執行帳號預覽及套用再次切換準備：

```bash
"${PY[@]}" "$SKILL_ROOT/scripts/prepare-reswitch.py" --config "$TARGET_CONFIG"
"${PY[@]}" "$SKILL_ROOT/scripts/prepare-reswitch.py" --config "$TARGET_CONFIG" --apply --reviewed
```

封存中斷時保留現狀並用相同套用命令續跑。完成後核對封存樹身分及服務狀態，經授權 enable unit，再從「切換與驗收」重做。

## 保管

`keep` 預設範例為 5，工具只清理符合自己命名及標記的舊備份／已完成紀錄，先列出再刪，保護當次回復所需資料；含 gate、使用中、失敗或無法確認狀態的資料保留，所以總數可能超過 `keep`。scratch 內可能有 gate，工具不自動刪除。作業後人工記錄目錄、大小、用途及磁碟空間；依授權和保管政策處理，不刪除或改名 gate 檔。
