# 隔离验收 部署与回滚方案

此文件提供可执行步骤，不表示生产环境已获准部署。本轮只在本机验证，没有连接生产服务器、修改 DNS 或发布 GitHub。

## 本机 Docker 验收

Docker Desktop 正常后，在本包目录执行：

```sh
docker compose -f compose.qa.yaml up -d --build
docker compose -f compose.qa.yaml logs --tail 100 api
```

使用 http://127.0.0.1:18021/，API 为 http://127.0.0.1:18020/。QA 项目名固定为 assessment-review-20261014，数据库及文书卷独立，数据库无宿主机端口。测试账号和示例密码仅用于此本机隔离环境，不能复制到生产。发布制度、出单后运行 `docker compose -f compose.qa.yaml restart api`，验证制度、账号及历史下载仍存在，再执行 `up -d --force-recreate api web` 验证卷持久化。

生产等价验收还必须在镜像中安装 requirements-dev.txt 并运行全量 pytest，以及检查实际 Linux 字体生成件。pytest 强制使用独立 SQLite 测试库，不能把这套测试计数当成真实 PostgreSQL 事务竞争测试。真实 PostgreSQL 需要另做 20 并发、编号/幂等和备份恢复演练。

## 生产切换前的备份

得到用户上线授权且全部阻塞项关闭后：确认当前提交、镜像 digest、Compose 项目名及现行制度；将正在运行的 API 停止接收写入，数据库容器保持运行。以生产实际 Compose 文件和私有环境文件执行，不使用 compose.qa.yaml。

```sh
docker compose --env-file /etc/postal-assessment.env stop api
docker compose --env-file /etc/postal-assessment.env exec -T db pg_dump -U assessment -d assessment -Fc > assessment-before.dump
docker compose --env-file /etc/postal-assessment.env exec -T db pg_restore --list < assessment-before.dump > assessment-before.list
docker compose --env-file /etc/postal-assessment.env run --rm --no-deps --entrypoint sh api -c 'tar -czf - -C /data documents' > documents-before.tar.gz
sha256sum assessment-before.dump documents-before.tar.gz > backup.sha256
tar -tzf documents-before.tar.gz > documents-before.list
```

将数据库和文书备份作为同一批次保存，文书包必须含 policies、manifest.json、归档 DOCX/PDF。备份文件放到权限受限的独立备份目录，不放在公开站点目录。私有环境文件另行备份，不能放进审核 ZIP。确认备份能够在全新的隔离数据库及新卷恢复，不覆盖生产数据进行试验。

## 发布

保留旧源码、镜像 digest 和上一批备份；本轮补丁不新增数据库表，但仍执行项目现有 Alembic 升级。构建/拉取固定的新镜像版本，运行单 Worker、单 LibreOffice 转换任务，保持现有文书和数据库卷。先在服务器本机入口验收，再按授权切换正式入口。核对登录、两个角色发布制度、匿名出单、历史下载、数据库约束、HTTPS 和备份日志。

## 回滚

如果新版本尚未接收正式写入，停止新 API，恢复上一镜像和源码配置，重新挂载原卷并检查历史文书。此次没有新增表，不需要逆向删表；绝不使用 `down -v`。

如果新版本已经产生新单据或新制度，不得直接把数据库或文书卷回到旧备份。先停写并完整备份最新状态，再判断旧应用是否能读取新日记/目录格式；优先回退程序并保留数据。确需整批数据回退时，应在新的数据库和新卷里恢复一致的库与文书备份，核对所有编号、记录和哈希，再由负责人确认切换。恢复操作和丢失写入范围必须记录。

新制度的历史恢复应优先通过本版本后台入口完成；磁盘 manifest、数据库审计和归档不得分别手工覆盖。当前 Docker/PostgreSQL 实测受阻，本方案尚未演练通过，不得据此宣称生产可上线。
