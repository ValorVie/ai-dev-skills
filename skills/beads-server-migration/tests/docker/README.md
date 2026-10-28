# 離線 Docker 演練

這是開發測試，不操作真實 repo。需要一份已保存的 embedded `.beads` 副本、一個已存在的本機 Docker 映像和足夠磁碟；來源副本以唯讀方式掛入，測試只在容器內複製及修改。兩個容器各限 4 CPU、`--network none` 且使用 Docker init 回收殭屍程序。容器內 systemctl 是測試替身，不能證明真實 systemd user service 的行為。

映像必須有 Python 3.14、`uv`、Git、`groupadd`、`useradd`、`runuser`、`bd`、Dolt、`getfacl`、`setfacl`、`fuser` 及其相依函式庫。可使用本目錄的 Dockerfile：準備一個私有 build context，把 Dockerfile 和已驗證、與基底系統相容的 `bd`、`dolt`、`getfacl`、`setfacl`、`fuser`、`libacl.so.1` 放進 context。基底映像須已在本機，構建時使用 `--network none`；來源及版本由執行者先確認。Dockerfile 不下載套件。

在測試主機、以有 Docker 權限的帳號建立映像；替換下列占位值：

```bash
docker image inspect "$BASE_IMAGE"
docker build --network none --build-arg "BASE_IMAGE=$BASE_IMAGE" -t "$TEST_IMAGE" "$BUILD_CONTEXT"
```

在測試主機、以同一帳號先建立空證據目錄、指定來源副本，再預覽。`SOURCE_COPY` 必須是副本，不能指向正在使用的 `.beads`；`LOGS` 在執行前必須是空目錄。

```bash
uv run --offline --python 3.14 --no-project python -I -B "$SKILL_ROOT/tests/docker/harness.py" --image "$TEST_IMAGE" --source "$SOURCE_COPY" --logs "$LOGS"
```

在測試主機、以同一帳號檢查預覽與適用授權後執行：

```bash
uv run --offline --python 3.14 --no-project python -I -B "$SKILL_ROOT/tests/docker/harness.py" --image "$TEST_IMAGE" --source "$SOURCE_COPY" --logs "$LOGS" --apply --reviewed
```

測試以兩組不同的 UID、GID、通訊埠、資料庫與服務名，分別建立 30 筆含留言及標籤的新資料與來源副本，演練切換、立即退回、再切換、寫入、事後退回、封存中斷及續跑。兩個閒置程序分別屬執行帳號及其他帳號，並核對前者不可傾印及兩者的程序身分。來源副本的資料庫目錄與 metadata 只在容器複本內改成測試名稱；`config.yaml` 不刪行，測試比對複本與來源的位元組。容器另有使用者層 `sync.remote`，切換後由 `bd config get` 讀回暫存副本的本機遠端，並確認來源設定未變。

成功時 harness 先列出再刪除自己建立的容器；失敗時保留容器和 log 供檢查。容器名稱顯示在 Docker 清單；只清理確認屬於本次的容器，先列出再刪。自建測試映像用完後也先列出再刪，已存在的共用基底映像保留。證據不應包含憑證。
