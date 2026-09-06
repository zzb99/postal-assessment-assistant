# 邮件处理中心通信生产考核管理系统

面向内部管理的全流程考核系统，覆盖登录、草稿、正式编号、台账、统计、Word/PDF/Excel 导出、作废与审计。正式数据由服务端数据库统一保存，前端不保存业务记录。

## 正式文书原则

`public/assessment-notice-template.docx` 是版式设计来源，服务端模板位于 `backend/templates/assessment-notice-template-v20260819.docx`。正式生成时依次执行：服务器校验、分配编号、填充 Word 内容控件、LibreOffice 转 PDF、单页 A4 校验、DOCX/PDF 哈希归档、数据库提交。任一步失败都会回滚为草稿。

网页预览读取归档 PDF；下载读取同一批归档文件。模板升级不会重新生成或覆盖历史文书。

## 旧 GitHub Pages 版本

仓库曾通过 GitHub Pages 发布静态版本。`pages-static` 分支仅保留为代码级回退，不是正式系统；工作流仅允许手动运行，且不再向浏览器构建注入 DeepSeek 密钥。

正式服务器具备部署条件后，应使用下方容器方案切换域名；切换前先备份服务器数据库，并保留静态分支作为只读回退版本。

## 阿里云 Linux 生产部署

服务器使用 Docker Engine、Compose、Caddy、FastAPI 单 Worker、PostgreSQL 和 LibreOffice。首次准备主机：

```sh
sh deploy/install-server.sh
```

将 `deploy/postal-assessment.env.example` 复制为 `/etc/postal-assessment.env`，填写随机数据库密码、JWT 密钥、临时管理员密码和 DeepSeek 密钥，并执行 `chmod 600 /etc/postal-assessment.env`。不要把该文件提交到 Git。

从仓库部署：

```sh
git clone https://github.com/zzb99/postal-assessment-assistant.git /opt/postal-assessment
cd /opt/postal-assessment
sh deploy/deploy-linux.sh
```

切换 DNS 前，只通过 SSH 隧道访问服务器本机入口 `http://127.0.0.1:8080`。Caddy 对外监听 80/443；安全组和 DNS 就绪后会自动申请证书并强制 HTTPS。

查看状态和日志：

```sh
docker compose --env-file /etc/postal-assessment.env ps
docker compose --env-file /etc/postal-assessment.env logs --tail 100 api web db caddy backup
```

停止（保留数据库）：

```sh
docker compose --env-file /etc/postal-assessment.env down
```

`backup` 容器每天生成 PostgreSQL 自检备份和文书压缩包，保留 7 天日备份与约 3 个月月备份。备份保存在独立 Docker 卷中。禁止使用 `down -v`，否则会删除持久化卷。

手工触发并检查一次备份：

```sh
docker compose --env-file /etc/postal-assessment.env restart backup
docker compose --env-file /etc/postal-assessment.env logs --tail 50 backup
```

## 本地开发

1. 复制 `.env.example` 为 `.env` 并设置 `JWT_SECRET` 与临时管理员环境变量。
2. 安装后端依赖：`python -m pip install -r backend/requirements.txt`。
3. 执行 `python -m backend.app.bootstrap` 初始化管理员。
4. 分别执行 `python -m uvicorn backend.app.main:app --reload --port 8000` 与 `npm.cmd run dev`。

开发默认使用 SQLite；生产环境必须使用 PostgreSQL，并通过 Alembic 迁移。

## 验证

```powershell
npm.cmd exec tsc -- -b
npm.cmd test
npm.cmd run build
python -m pytest backend/tests -q
```

## 权限

- 系统管理员：全量数据、建单、作废、账号与基础数据管理。
- 领导：全量台账与统计，只读。
- 部门主管：仅本部门数据，可建单和维护草稿。

正式考核单不可直接修改或删除，只能作废；编号永久保留且不复用。历史记录保存部门、单位和问题分类名称快照。
