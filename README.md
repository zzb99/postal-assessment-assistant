# 邮件处理中心通信生产考核管理系统

面向内部管理的全流程考核系统，覆盖登录、草稿、正式编号、台账、统计、Word/PDF/Excel 导出、作废与审计。正式数据由服务端数据库统一保存，前端不保存业务记录。

## 生产部署（推荐）

要求 Windows Docker Desktop，首次部署执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\deploy.ps1 -Rebuild
```

仓库 `main` 分支通过质量检查后会自动发布 web/api 镜像到 GitHub Container Registry。服务器从仓库镜像部署时执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\deploy.ps1 -RepositoryImages
```

系统默认地址：`http://127.0.0.1:8080`。首次部署会自动生成 PostgreSQL、JWT 和管理员密码，保存在已被 Git 忽略的 `deploy/.env.runtime`。管理员用户名为 `admin`。

查看状态和日志：

```powershell
docker compose --env-file .\deploy\.env.runtime ps
docker compose --env-file .\deploy\.env.runtime logs --tail 100 api web db
```

停止（保留数据库）：

```powershell
docker compose --env-file .\deploy\.env.runtime down
```

备份 PostgreSQL：

```powershell
docker compose --env-file .\deploy\.env.runtime exec -T db pg_dump -U assessment -d assessment -Fc > assessment-backup.dump
```

禁止使用 `down -v`，否则会删除数据库卷。

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
