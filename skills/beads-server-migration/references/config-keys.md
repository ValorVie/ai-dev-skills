# Beads 1.3.1 設定鍵盤點與遷移限制

此表根據 Beads 1.3.1 原碼 commit `c1c4b642ac1c08d8c828007a1c2f96e47e43ef7c` 的 `cmd/bd/` 與 `internal/` 非測試 Go 檔，列出具名的設定讀取、預設值、YAML 登記及其原碼位置。`file:line` 均相對該原始碼根目錄；不同版本須重新盤點。資料庫設定與 YAML 設定不是同一來源；此表的「資料庫」是資料庫內的鍵，不能只用檔案檢查聲稱已拒絕。

「拒絕」指操作者的專案及使用者 YAML 設定不得包含該鍵或命名空間；工具自己的 scratch `sync.remote` 只有在檢查點身分正確且值等於工具建立的本機遠端時例外。`dolt.max-conns` 是唯一 Dolt 白名單：`internal/storage/dolt/open.go:318-332` 僅將它用於連線池大小。Dolt 其餘鍵與未知子鍵都拒絕。其他標成「其他」的鍵不因此取得完整安全保證，格式仍須通過工具的保守解析。

資料庫的 `routing.*`／`contributor.*` 可覆寫讀取位置：`cmd/bd/routing_read.go:25-43,51-92,162-176`、`internal/routing/routing.go:208-230`。子程序將路由模式固定為 `explicit`、預設 repo 固定為 `.`；操作者提供的路由環境變數遭拒絕。`bd where` 僅讀回路徑，不能單獨證明儲存模式；`cmd/bd/where.go:69-81` 與 `cmd/bd/main.go:1696-1703`。

表中「設定／預設」包含讀取或註冊預設；「YAML 登記」表示登記存在，不等於本工具會使用該功能。`*` 是依程式組合的動態後綴；`config get/set` 可接受任意鍵，`cmd/bd/config.go:311-328`，因此無法把所有執行期輸入枚舉為固定清單。整個受限命名空間均拒絕未知子鍵。測試檔、CLI flags、環境變數、metadata JSON 與直接 Git/Dolt 設定不是 YAML 鍵，須另依手冊檢查。

| 鍵 | 本工具處理 | 來源類型 | 原碼位置 |
| --- | --- | --- | --- |
| `actor` | 其他 | YAML 登記、設定／預設 | `cmd/bd/main.go:806`、`internal/config/config.go:249`、`internal/config/yaml_config.go:38` |
| `ado.filter.area_path` | 拒絕 | 設定／預設 | `cmd/bd/ado.go:305` |
| `ado.filter.iteration_path` | 拒絕 | 設定／預設 | `cmd/bd/ado.go:312` |
| `ado.filter.states` | 拒絕 | 設定／預設 | `cmd/bd/ado.go:326` |
| `ado.filter.types` | 拒絕 | 設定／預設 | `cmd/bd/ado.go:319` |
| `ado.org` | 拒絕 | 設定／預設 | `cmd/bd/ado.go:178`、`internal/ado/tracker.go:85` |
| `ado.pat` | 拒絕 | YAML 登記、設定／預設 | `cmd/bd/ado.go:177`、`internal/ado/tracker.go:80`、`internal/config/yaml_config.go:106` |
| `ado.project` | 拒絕 | 設定／預設 | `cmd/bd/ado.go:183`、`internal/ado/tracker.go:95` |
| `ado.projects` | 拒絕 | 設定／預設 | `cmd/bd/ado.go:182`、`internal/ado/tracker.go:94` |
| `ado.url` | 拒絕 | 設定／預設 | `cmd/bd/ado.go:179`、`internal/ado/tracker.go:86` |
| `agent.profile` | 其他 | YAML 登記、設定／預設 | `internal/config/agent_profile.go:57`、`internal/config/config.go:288`、`internal/config/yaml_config.go:50` |
| `agents.file` | 其他 | 設定／預設 | `internal/config/config.go:1146` |
| `ai.api_key` | 拒絕 | 設定／預設 | `internal/config/config.go:826` |
| `ai.base_url` | 拒絕 | 設定／預設 | `internal/config/config.go:343`、`internal/config/config.go:840` |
| `ai.model` | 拒絕 | 設定／預設 | `internal/config/config.go:342`、`internal/config/config.go:775`、`internal/config/config.go:784` |
| `allowed_prefixes` | 其他 | 資料庫 | `cmd/bd/graph_apply.go:722`、`internal/storage/domain/db/config.go:176`、`internal/storage/domain/issue.go:956` |
| `audit.enabled` | 其他 | 設定／預設 | `internal/audit/audit.go:71`、`internal/config/config.go:245` |
| `backup.enabled` | 拒絕 | YAML 登記、設定／預設 | `cmd/bd/backup_auto.go:35`、`cmd/bd/backup_auto.go:36`、`cmd/bd/backup_auto.go:59` |
| `backup.git-push` | 拒絕 | YAML 登記、設定／預設 | `internal/config/config.go:324`、`internal/config/yaml_config.go:83` |
| `backup.git-repo` | 拒絕 | YAML 登記、設定／預設 | `cmd/bd/backup_export.go:29`、`internal/config/config.go:325`、`internal/config/yaml_config.go:84` |
| `backup.interval` | 拒絕 | YAML 登記、設定／預設 | `cmd/bd/backup.go:133`、`cmd/bd/backup_auto.go:193`、`internal/config/config.go:323` |
| `claim.pools` | 其他 | 資料庫 | `cmd/bd/show_unit_helpers.go:58`、`cmd/bd/show_unit_helpers.go:70`、`internal/storage/uow/issue_operations.go:284` |
| `contributor.auto_route` | 拒絕 | 設定／預設 | `cmd/bd/create.go:326`、`cmd/bd/routing_read.go:76` |
| `contributor.planning_repo` | 拒絕 | 設定／預設 | `cmd/bd/create.go:331`、`cmd/bd/migrate_personal.go:104`、`cmd/bd/routing_read.go:81` |
| `create.require-description` | 其他 | YAML 登記、設定／預設 | `cmd/bd/create.go:150`、`cmd/bd/create_input.go:171`、`internal/config/config.go:291` |
| `db` | 拒絕 | YAML 登記、設定／預設、間接讀取 | `cmd/bd/main.go:1123`、`internal/config/config.go:248`、`internal/config/yaml_config.go:37` |
| `directory.labels` | 其他 | 設定／預設 | `internal/config/config.go:319`、`internal/config/config.go:904` |
| `doctor.suggest_pruning_issue_count` | 其他 | 資料庫 | `cmd/bd/doctor/database.go:555` |
| `dolt.auto-commit` | 拒絕 | 設定／預設 | `cmd/bd/main.go:1139`、`cmd/bd/main.go:760`、`internal/config/config.go:260` |
| `dolt.auto-push` | 拒絕 | 設定／預設 | `cmd/bd/dolt_autopush.go:84` |
| `dolt.auto-push-interval` | 拒絕 | 設定／預設 | `cmd/bd/dolt_autopush.go:135` |
| `dolt.auto-push-timeout` | 拒絕 | 設定／預設 | `cmd/bd/dolt_autopush.go:163` |
| `dolt.auto-start` | 拒絕 | 設定／預設 | `internal/doltserver/doltserver.go:175`、`internal/storage/dolt/open.go:176`、`internal/storage/dolt/open.go:178` |
| `dolt.data-dir` | 拒絕 | 設定寫入／metadata | `cmd/bd/dolt.go:2140,2169`、`internal/configfile/configfile.go:203-211` |
| `dolt.database` | 拒絕 | 設定寫入／metadata | `cmd/bd/dolt.go:2106-2111` |
| `dolt.debug` | 拒絕 | YAML 登記、設定／預設 | `internal/config/yaml_config.go:95`、`internal/doltserver/doltserver.go:128` |
| `dolt.host` | 拒絕 | 設定／預設 | `cmd/bd/backup_auto.go:112`、`cmd/bd/init.go:769`、`internal/configfile/configfile.go:433` |
| `dolt.local-only` | 拒絕 | 設定／預設 | `cmd/bd/dolt_local_only.go:9` |
| `dolt.max-conns` | 白名單 | YAML 登記、設定／預設 | `internal/config/yaml_config.go:92`、`internal/storage/dolt/open.go:328` |
| `dolt.mode` | 拒絕 | 設定／預設 | `cmd/bd/init.go:2947`、`cmd/bd/init.go:734`、`internal/configfile/configfile.go:389` |
| `dolt.pool-read-timeout` | 拒絕 | YAML 登記、設定／預設 | `internal/config/yaml_config.go:93`、`internal/storage/dolt/open.go:343` |
| `dolt.pool-write-timeout` | 拒絕 | YAML 登記、設定／預設 | `internal/config/yaml_config.go:94`、`internal/storage/dolt/open.go:349` |
| `dolt.port` | 拒絕 | 設定／預設 | `cmd/bd/bootstrap.go:721`、`cmd/bd/init.go:771`、`internal/doltserver/doltserver.go:828` |
| `dolt.shared-server` | 拒絕 | YAML 登記、設定／預設、間接讀取 | `cmd/bd/bootstrap.go:681`、`cmd/bd/config_apply.go:414`、`cmd/bd/migrate_dolt_mode.go:1200` |
| `dolt.socket` | 拒絕 | 設定寫入／metadata | `cmd/bd/dolt.go:2128-2131` |
| `dolt.user` | 拒絕 | 設定寫入／metadata | `cmd/bd/dolt.go:2133-2138` |
| `events-export` | 其他 | 設定／預設 | `internal/config/config.go:217` |
| `events-journal` | 其他 | YAML 登記、設定／預設、間接讀取 | `internal/config/config.go:223`、`internal/config/yaml_config.go:31`、`internal/eventsjournal/activation.go:30` |
| `events-journal-auto-prune` | 其他 | YAML 登記、設定／預設、間接讀取 | `internal/config/config.go:244`、`internal/config/yaml_config.go:34`、`internal/eventsjournal/autoprune.go:61` |
| `events-journal-retain-days` | 其他 | YAML 登記、設定／預設 | `cmd/bd/events.go:320`、`cmd/bd/events_journal.go:223`、`internal/config/config.go:235` |
| `events-journal-retain-rows` | 其他 | YAML 登記、設定／預設 | `cmd/bd/events.go:321`、`cmd/bd/events_journal.go:224`、`internal/config/config.go:236` |
| `export.auto` | 其他 | 設定／預設 | `cmd/bd/export_auto.go:99`、`cmd/bd/hooks.go:1520`、`internal/config/config.go:330` |
| `export.exclude_owner` | 其他 | 設定／預設、資料庫 | `cmd/bd/export.go:399`、`cmd/bd/export.go:406` |
| `export.exclude_owners` | 其他 | 設定／預設、資料庫 | `cmd/bd/export.go:396`、`cmd/bd/export.go:403` |
| `export.git-add` | 其他 | 設定／預設 | `cmd/bd/export_auto.go:268`、`cmd/bd/hooks.go:1580`、`internal/config/config.go:333` |
| `export.interval` | 其他 | 設定／預設 | `cmd/bd/export_auto.go:128`、`internal/config/config.go:331` |
| `export.path` | 其他 | 設定／預設 | `cmd/bd/export_auto.go:116`、`cmd/bd/hooks.go:1529`、`cmd/bd/hooks.go:1633` |
| `external_projects` | 拒絕 | 設定／預設 | `internal/config/config.go:355`、`internal/config/config.go:958` |
| `federation.allowed-remote-patterns` | 拒絕 | 設定／預設 | `cmd/bd/config.go:743`、`internal/config/config.go:277` |
| `federation.exclude_types` | 拒絕 | 設定／預設 | `internal/config/config.go:1078`、`internal/config/config.go:278` |
| `federation.remote` | 拒絕 | 設定／預設 | `cmd/bd/config.go:722`、`cmd/bd/config_apply.go:275`、`cmd/bd/config_drift.go:156` |
| `federation.sovereignty` | 拒絕 | 設定／預設 | `cmd/bd/config.go:721`、`internal/config/config.go:276`、`internal/config/sync.go:78` |
| `git.author` | 其他 | YAML 登記、設定／預設 | `internal/config/config.go:314`、`internal/config/yaml_config.go:46` |
| `git.no-gpg-sign` | 其他 | YAML 登記、設定／預設 | `internal/config/config.go:315`、`internal/config/yaml_config.go:47` |
| `github.owner` | 拒絕 | 設定／預設 | `cmd/bd/github.go:174`、`internal/github/tracker.go:49` |
| `github.repo` | 拒絕 | 設定／預設 | `cmd/bd/github.go:175`、`internal/github/tracker.go:50` |
| `github.repository` | 拒絕 | 設定／預設 | `cmd/bd/github.go:176`、`internal/github/tracker.go:54` |
| `github.token` | 拒絕 | YAML 登記、設定／預設 | `cmd/bd/github.go:173`、`internal/config/yaml_config.go:100`、`internal/github/tracker.go:44` |
| `github.url` | 拒絕 | 設定／預設 | `cmd/bd/github.go:177`、`internal/github/tracker.go:74` |
| `gitlab.default_project_id` | 拒絕 | 設定／預設 | `cmd/bd/gitlab.go:223`、`internal/gitlab/tracker.go:65` |
| `gitlab.filter_assignee` | 拒絕 | 設定／預設 | `cmd/bd/gitlab.go:378`、`internal/gitlab/tracker.go:102` |
| `gitlab.filter_labels` | 拒絕 | 設定／預設 | `cmd/bd/gitlab.go:375`、`internal/gitlab/tracker.go:99` |
| `gitlab.filter_milestone` | 拒絕 | 設定／預設 | `cmd/bd/gitlab.go:377`、`internal/gitlab/tracker.go:101` |
| `gitlab.filter_project` | 拒絕 | 設定／預設 | `cmd/bd/gitlab.go:376`、`internal/gitlab/tracker.go:100` |
| `gitlab.group_id` | 拒絕 | 設定／預設 | `cmd/bd/gitlab.go:222`、`internal/gitlab/tracker.go:64` |
| `gitlab.project_id` | 拒絕 | 設定／預設 | `cmd/bd/gitlab.go:221`、`internal/gitlab/tracker.go:63` |
| `gitlab.project_path` | 拒絕 | 設定／預設 | `internal/gitlab/tracker.go:88` |
| `gitlab.token` | 拒絕 | YAML 登記、設定／預設 | `cmd/bd/gitlab.go:220`、`internal/config/yaml_config.go:105`、`internal/gitlab/tracker.go:53` |
| `gitlab.url` | 拒絕 | 設定／預設 | `cmd/bd/gitlab.go:219`、`internal/gitlab/tracker.go:58` |
| `hierarchy.max-depth` | 其他 | YAML 登記、設定／預設 | `internal/config/config.go:311`、`internal/config/yaml_config.go:78` |
| `identity` | 其他 | YAML 登記、設定／預設 | `internal/config/config.go:1012`、`internal/config/config.go:253`、`internal/config/yaml_config.go:39` |
| `import.auto` | 其他 | YAML 登記、設定／預設 | `cmd/bd/hooks.go:1652`、`cmd/bd/main.go:2212`、`internal/config/config.go:338` |
| `import.path` | 其他 | YAML 登記、設定／預設 | `cmd/bd/hooks.go:1632`、`cmd/bd/import_path.go:12`、`internal/config/config.go:339` |
| `issue-prefix` | 其他 | 設定／預設 | `cmd/bd/ado.go:874`、`cmd/bd/create_deps.go:250`、`cmd/bd/github.go:520` |
| `issue_id_mode` | 其他 | 資料庫 | `internal/storage/domain/issue.go:1625` |
| `issue_prefix` | 其他 | 設定／預設、資料庫 | `cmd/bd/ado.go:877`、`cmd/bd/create.go:1058`、`cmd/bd/github.go:523` |
| `jira.api_token` | 拒絕 | YAML 登記、設定／預設、資料庫 | `cmd/bd/jira.go:354`、`internal/config/yaml_config.go:104`、`internal/jira/tracker.go:80` |
| `jira.api_version` | 拒絕 | 設定／預設 | `internal/jira/tracker.go:87` |
| `jira.last_sync` | 拒絕 | 資料庫 | `cmd/bd/jira.go:246` |
| `jira.project` | 拒絕 | 設定／預設、資料庫 | `cmd/bd/jira.go:249`、`cmd/bd/jira.go:348`、`internal/jira/tracker.go:72` |
| `jira.projects` | 拒絕 | 設定／預設、資料庫 | `cmd/bd/jira.go:248`、`cmd/bd/jira.go:347`、`internal/jira/tracker.go:71` |
| `jira.pull_jql` | 拒絕 | 設定／預設 | `internal/jira/tracker.go:195` |
| `jira.push_prefix` | 拒絕 | 資料庫 | `cmd/bd/jira.go:214` |
| `jira.url` | 拒絕 | 設定／預設、資料庫 | `cmd/bd/jira.go:245`、`cmd/bd/jira.go:340`、`internal/jira/tracker.go:63` |
| `jira.username` | 拒絕 | 設定／預設 | `internal/jira/tracker.go:79` |
| `json` | 其他 | YAML 登記、設定／預設 | `cmd/bd/main.go:1094`、`cmd/bd/main.go:751`、`internal/config/config.go:216` |
| `linear.api_endpoint` | 拒絕 | 資料庫 | `cmd/bd/linear.go:1160`、`cmd/bd/linear.go:1236`、`internal/linear/tracker.go:75` |
| `linear.api_key` | 拒絕 | YAML 登記、設定／預設 | `cmd/bd/linear.go:1024`、`cmd/bd/linear.go:1198`、`cmd/bd/linear.go:1228` |
| `linear.exclude_id_patterns` | 拒絕 | 資料庫 | `cmd/bd/linear.go:1289` |
| `linear.exclude_id_prefix` | 拒絕 | 資料庫 | `cmd/bd/linear.go:1286` |
| `linear.hash_length` | 拒絕 | 設定／預設 | `cmd/bd/linear.go:1306` |
| `linear.id_mode` | 拒絕 | 設定／預設 | `cmd/bd/linear.go:1267` |
| `linear.last_sync` | 拒絕 | 資料庫 | `cmd/bd/linear.go:839` |
| `linear.oauth_client_id` | 拒絕 | YAML 登記、設定／預設 | `cmd/bd/linear.go:1019`、`cmd/bd/linear.go:1186`、`cmd/bd/linear.go:1213` |
| `linear.oauth_client_secret` | 拒絕 | YAML 登記、設定／預設 | `cmd/bd/linear.go:1020`、`cmd/bd/linear.go:1187`、`cmd/bd/linear.go:1216` |
| `linear.project_id` | 拒絕 | 資料庫 | `cmd/bd/linear.go:1163`、`cmd/bd/linear.go:795`、`internal/linear/tracker.go:76` |
| `linear.push_prefix` | 拒絕 | 資料庫 | `cmd/bd/linear.go:804` |
| `linear.rate_limit_floor` | 拒絕 | 設定／預設 | `cmd/bd/linear.go:1169`、`internal/linear/tracker.go:84` |
| `linear.team_id` | 拒絕 | 設定／預設 | `cmd/bd/linear.go:1136`、`internal/linear/tracker.go:65` |
| `linear.team_ids` | 拒絕 | 設定／預設 | `cmd/bd/linear.go:1135`、`internal/linear/tracker.go:64` |
| `lint.sections.*` | 其他 | 間接讀取 | `internal/validation/template.go:44` |
| `list.limit` | 其他 | 設定／預設 | `cmd/bd/list_input.go:59`、`cmd/bd/list_input.go:60`、`internal/config/config.go:346` |
| `mail.delegate` | 其他 | 資料庫 | `cmd/bd/mail.go:102` |
| `max_collision_prob` | 其他 | 資料庫 | `internal/storage/domain/db/config.go:186` |
| `max_hash_length` | 其他 | 資料庫 | `internal/storage/domain/db/config.go:202` |
| `metrics.disabled` | 拒絕 | 設定／預設 | `internal/config/config.go:271` |
| `metrics.endpoint` | 拒絕 | 設定／預設 | `internal/config/config.go:272` |
| `min_hash_length` | 其他 | 資料庫 | `internal/storage/domain/db/config.go:194` |
| `no-db` | 拒絕 | YAML 登記、設定／預設 | `internal/config/config.go:246`、`internal/config/yaml_config.go:25` |
| `no-git-ops` | 拒絕 | YAML 登記、設定／預設 | `cmd/bd/export_auto.go:268`、`cmd/bd/hooks.go:1580`、`cmd/bd/hooks.go:1695` |
| `no-hooks` | 其他 | 設定／預設 | `cmd/bd/main.go:1809`、`cmd/bd/main.go:1920`、`internal/config/config.go:247` |
| `no-push` | 拒絕 | YAML 登記、設定／預設 | `cmd/bd/dolt.go:534`、`cmd/bd/init.go:2121`、`cmd/bd/init_proxied_server.go:621` |
| `node_id` | 其他 | YAML 登記、設定／預設 | `internal/config/config.go:1063`、`internal/config/config.go:255`、`internal/config/yaml_config.go:43` |
| `notion.data_source_id` | 拒絕 | 設定／預設 | `cmd/bd/notion.go:171`、`internal/notion/tracker.go:70` |
| `notion.push_label` | 拒絕 | 資料庫 | `cmd/bd/notion.go:591` |
| `notion.push_prefix` | 拒絕 | 資料庫 | `cmd/bd/notion.go:590` |
| `notion.view_url` | 拒絕 | 設定／預設 | `cmd/bd/notion.go:172`、`internal/notion/tracker.go:71` |
| `output.title-length` | 其他 | 設定／預設 | `cmd/bd/feedback.go:32`、`internal/config/config.go:351` |
| `prime.max-memories` | 其他 | YAML 登記、設定／預設 | `cmd/bd/prime.go:504`、`internal/config/yaml_config.go:68` |
| `prime.max-memory-chars` | 其他 | YAML 登記、設定／預設 | `cmd/bd/prime.go:508`、`internal/config/yaml_config.go:69` |
| `readonly` | 其他 | 設定／預設 | `cmd/bd/main.go:1102`、`cmd/bd/main.go:754` |
| `repos.additional` | 拒絕 | 設定／預設 | `internal/config/config.go:946`、`cmd/bd/doctor/config_values.go:162`、`cmd/bd/doctor/config_values.go:163` |
| `repos.primary` | 拒絕 | 設定／預設 | `internal/config/config.go:939`、`cmd/bd/doctor/config_values.go:149`、`cmd/bd/doctor/config_values.go:150` |
| `routing.contributor` | 拒絕 | YAML 登記、設定／預設、資料庫 | `cmd/bd/create.go:322`、`cmd/bd/init_contributor.go:286`、`cmd/bd/init_contributor.go:294` |
| `routing.default` | 拒絕 | YAML 登記、設定／預設、間接讀取 | `cmd/bd/create.go:336`、`cmd/bd/routing_read.go:86`、`internal/config/config.go:264` |
| `routing.maintainer` | 拒絕 | YAML 登記、設定／預設 | `cmd/bd/create.go:337`、`cmd/bd/routing_read.go:87`、`internal/config/config.go:265` |
| `routing.mode` | 拒絕 | YAML 登記、設定／預設、間接讀取 | `cmd/bd/create.go:321`、`cmd/bd/routing_read.go:72`、`internal/config/config.go:263` |
| `status.custom` | 其他 | 設定／預設、資料庫 | `internal/config/config.go:1102`、`internal/storage/issueops/config_helpers.go:62`、`cmd/bd/doctor/config_values.go:428` |
| `storage-class.*` | 其他 | 設定／預設、間接讀取 | `cmd/bd/create.go:700` |
| `sync.branch` | 拒絕 | 資料庫 | `cmd/bd/migrate.go:769` |
| `sync.git-remote` | 拒絕 | YAML 登記、設定／預設 | `cmd/bd/setup/agents.go:61`、`cmd/bd/sync_remote.go:24`、`cmd/bd/sync_remote.go:34` |
| `sync.remote` | 拒絕；受控 scratch 例外 | YAML 登記、設定／預設、間接讀取 | `cmd/bd/dolt.go:1826`、`cmd/bd/dolt_remote_proxied_server.go:33`、`cmd/bd/init.go:3391` |
| `sync.require_confirmation_on_mass_delete` | 拒絕 | YAML 登記、設定／預設 | `internal/config/config.go:269`、`internal/config/yaml_config.go:55` |
| `types.custom` | 其他 | 設定／預設、資料庫 | `cmd/bd/template.go:605`、`internal/config/config.go:1087`、`internal/storage/domain/db/config.go:141` |
| `types.infra` | 其他 | 設定／預設、資料庫 | `internal/config/config.go:1094`、`internal/storage/domain/db/config.go:237` |
| `validation.metadata.fields` | 其他 | 設定／預設 | `internal/config/config.go:1127` |
| `validation.metadata.mode` | 其他 | 設定／預設 | `internal/config/config.go:1111`、`internal/config/config.go:306` |
| `validation.on-close` | 其他 | YAML 登記、設定／預設 | `cmd/bd/close.go:618`、`internal/config/config.go:299`、`internal/config/yaml_config.go:74` |
| `validation.on-create` | 其他 | YAML 登記、設定／預設 | `cmd/bd/create.go:279`、`cmd/bd/create_input.go:307`、`internal/config/config.go:298` |
| `validation.on-sync` | 其他 | YAML 登記、設定／預設 | `internal/config/config.go:300`、`internal/config/yaml_config.go:75` |

以下鍵由常數或前綴掃描間接讀取；拒絕同樣只表示 YAML 輸入邊界，資料庫內資料不由預覽讀取或刪除。

| 鍵 | 本工具處理 | 來源類型 | 原碼位置 |
| --- | --- | --- | --- |
| `notion.token` | 拒絕 | 資料庫 | `internal/notion/auth.go:9,31` |
| `jira.status_map.*` | 拒絕 | 資料庫前綴 | `internal/jira/tracker.go:97` |
| `jira.type_map.*` | 拒絕 | 資料庫前綴 | `internal/jira/tracker.go:108` |
| `jira.priority_map.*` | 拒絕 | 資料庫前綴 | `internal/jira/tracker.go:119` |
| `jira.custom_fields.*` | 拒絕 | 資料庫前綴 | `internal/jira/tracker.go:130` |
| `ado.state_map.*` | 拒絕 | 資料庫前綴 | `internal/ado/tracker.go:115` |
| `ado.type_map.*` | 拒絕 | 資料庫前綴 | `internal/ado/tracker.go:116` |
| `linear.priority_map.*` | 拒絕 | 資料庫前綴 | `internal/linear/mapping.go:252` |
| `linear.state_map.*` | 拒絕 | 資料庫前綴 | `internal/linear/mapping.go:260` |
| `linear.outbound_state_map.*` | 拒絕 | 資料庫前綴 | `internal/linear/mapping.go:268` |
| `linear.label_type_map.*` | 拒絕 | 資料庫前綴 | `internal/linear/mapping.go:274` |
| `linear.relation_map.*` | 拒絕 | 資料庫前綴 | `internal/linear/mapping.go:280` |

下列動態呼叫依呼叫者傳入鍵，無法僅靠讀取函式列出無限多個名稱：`internal/config/config.go:678-750,880-892,1191-1220`、`internal/config/yaml_config.go:459,576`、`cmd/bd/config.go:311-328,515-530`、`cmd/bd/routing_read.go:25-43`。`repos` 映射由 `internal/config/repos.go:35-73` 另行解析。上述資料庫設定與外部服務設定不等於本工具已在真實目標驗證；此表只對固定版本和指定原碼範圍成立。
