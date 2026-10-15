# 源码清理交付说明（2026-10-15）

本次基于用户指定 ZIP 的当前验收修复版继续清理，清理前提交为 `d25e6ee`。没有改变业务流程、AI 匹配或服务端文书生成逻辑，也没有部署生产环境。

## 清理范围

通过前端入口引用图、动态引用和文件名搜索确认，以下 17 个文件属于已停用的浏览器导出与遮罩预览链路，已删除：

- `src/components/GovernancePanel.tsx`
- `src/components/PreviewPane.tsx`
- `src/components/NoticePreview.tsx`
- `src/styles.css`
- `src/template.css`
- `src/services/documentData.ts`
- `src/services/exportService.ts`
- `src/services/exportService.test.ts`
- `src/utils/storage.ts`
- `src/utils/validation.ts`
- `src/utils/validation.test.ts`
- `src/utils/noticeSummary.ts`
- `src/utils/currency.ts`
- `src/utils/currency.test.ts`
- `src/templateLayout.ts`
- `public/assessment-notice-template.png`
- `public/assessment-notice-template.pdf`

同步移除 4 个无调用类型和 4 个直接依赖：`file-saver`、`html2canvas`、`pdf-lib`、`@types/file-saver`。锁文件已更新，离线依赖清理共移除 14 个安装包。规则生成脚本使用的 `pizzip` 和当前 PDF 图片分享使用的 `pdfjs-dist` 保留。

原始 Word、后端正式模板、制度、后端源码及测试均保留。只删除旧预览的派生 PNG/PDF，不删除原始文书模板。清理前文件可从 Git 提交 `d25e6ee` 或 r3 完整源码包恢复。

## 验证结果

- 清理前后完整后端测试均为 **222 通过**；本机启用真实 LibreOffice 文书转换测试。清理后耗时 108.02 秒。
- 前端由 55 项变为 **43 项通过**：退役旧导出 2 项、旧校验 9 项、旧金额包装 2 项测试；有用的金额大写断言迁至实际使用的 `amountToChinese`，新增 1 项。没有移除当前业务流程测试来掩盖失败。
- 每次删除后执行前端回归；最终生产构建通过。主 JS/CSS 和 PDF 相关构建文件的内容哈希名称与清理前一致，说明这些旧模块原本就不在运行时依赖图中。
- 用户指定的原 99 项后端定向测试保留，交付前核对原 ZIP 文件字节并核对本轮测试报告。
- 现有 Starlette/httpx 弃用提示仍为 1 条；不是测试失败。

测试日志和 XML 随独立证据包中的 `acceptance/cleanup-evidence` 交付。此前视觉证据和识别修复报告继续保留，未将它们冒充本轮重新执行的验收。

## 部署与回退

沿用 `docs/DEPLOY_ROLLBACK_20261014.md`。本次无数据库结构变更。正式上线前仍需完成真实 Docker/PostgreSQL、Linux 字体和生产备份恢复验收；本机测试不代替这些项目。

本轮仅交付源码，未修改服务器、DNS、密钥或运行数据。回退可使用清理前 r3 源码包重新构建应用并保留数据库、文书卷，不执行删卷命令。私有环境文件和运行数据不放入源码审核包。
