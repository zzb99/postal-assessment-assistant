# 整体升级与本地验收报告（2026-10-13）

## 交付结论与边界

现有全栈系统的本地升级已实施，不是重写。工作目录为 `D:\桌面\考核-server-release`，本地入口 `http://127.0.0.1:5173/`。未连接阿里云、未切DNS、未推送或部署生产环境。

本地自动化与真实LibreOffice文书链路已验证。真实DeepSeek写作质量、真实账单A/B/C、Linux字体和PostgreSQL生产并发仍 **NOT VERIFIED**，不能据此宣称已达到最终业务验收或70%-90%Token下降。

未收到独立的“GPT审查报告”文件；依据本轮两份任务正文、失败截图、源码、原制度/模板及历史Word实施。代码复核不是所缺独立报告的替代品。

## 主要修改文件

- AI共享服务：`backend/app/ai.py`、`ai_writing.py`、`rule_search.py`、`pricing.py`、`writing_style.py`、`ai_cache.py`、`ai_usage.py`、`work_queue.py`。
- 后端接口/持久化：`backend/app/routers/ai.py`、`routers/quick.py`、`quick.py`、`governance.py`、`schemas.py`、`models.py`、`services.py`、`config.py`、`main.py`；Alembic `20261013_04` / `20261013_05`。
- 原文与计价分离：`scripts/generate-rules.mjs`、`scripts/pricing-parser.mjs`、`backend/data/pricing-overrides.json`、`public/production-quality-rules.json`。生成器核验制度版本、条款ID及原文SHA-256，避免构建覆盖核验价。
- 文风：`backend/data/assessment-writing-examples.json`、`writing-history-analysis.json`、`scripts/analyse_writing_history.py`。
- 文书：`backend/app/documents.py`、`scripts/upgrade_assessment_template.py`、新增 `backend/templates/assessment-notice-template-v20261013.docx`、`scripts/render_upgrade_examples.py`。原始Word和旧版prepared模板保留。
- 手机及后台：`src/quick/AiComposer.tsx`、`QuickPage.tsx`、`aiContinuation.ts`、`quick.css`；`src/components/AiUsagePanel.tsx`、`GovernancePanel.tsx`；`src/App.tsx`、`src/data/rules.ts`。
- 发布配置：`compose.yaml`、`deploy/nginx.conf`、`.env.example`、`deploy/postal-assessment.env.example`、`vite.config.ts`、`package.json` / lockfile、`scripts/start-local-api.ps1`。
- 测试：`backend/tests/test_pricing.py`、`test_ai_optimization.py`、`test_upgrade_guards.py`、`test_authorization.py`、`test_queue.py`、`test_usage_and_stage.py`、`test_word_layout.py`、`test_real_document_journey.py`、`test_assessment_workflow.py`、`conftest.py`、24条检索fixture；前端计价、续处理、费用及跨会话权限回归。
- 对比工具：`scripts/benchmark_ai_prompts.py`；证据目录 `output/upgrade-20261013/`。该目录为本地验收资料，不含真实密钥或生产数据库。

## 统一业务流程

1. 选择公司/日期/班次，记住本人班组和姓名；首次登记设备码，由管理员一次授权。
2. 输入短事实；后端对完整319条含附件制度做字符n-gram/BM25及业务同义词检索，通常6条，歧义扩至15条。
3. 单次Flash请求只接收候选关键原文、精简写作要求、最多1条相关整改写法。固定资料在变化事实前；官方缓存仍是best-effort，不能保证命中。
4. AI返回条款选择、事实润色和整改；后端验证候选归属、数字/数量单位、公司、未核算金额及部分新增适用事实。
5. Decimal模块从原事实和显式回答确认触发条件、计费数量；不信任模型给出的最终金额。明确的否定条件不能被点击“是”覆盖。
6. 即使价格未定，完整两段式草稿保留。每次只问一个关键问题，已知条件续处理不调用AI。
7. 可编辑正文；标点和整改措辞本地核对重签。第一段的事实、否定和计费依据不能靠改文字继续沿用旧价，语义改变需重新整理。
8. 正式生成时校验设备授权、现行制度核准摘要、签名与全部输入。Word→同源PDF→归档成功才正式生效；幂等重试不重复编号。
9. 历史下载读取已归档文件并核验SHA-256；模板改版不会重生成旧单。手机分享图片由归档PDF生成。

## 制度与金额核验

可核对制度原件为20260819版；新ZIP包含86份有效考核单和4个Word锁定文件，不构成20260825版有效制度原件。系统以目录摘要、生效日期及管理员核准记录管理当前版本；目录内容改变即重新待核准。不能把技术解析标识当成主管业务核准。

| 场景 | 已实现处理 |
| --- | --- |
| 卸车完毕遗留1件或10件 | official-036，确认同一次事项后固定40元，不乘件数 |
| 未确认卸车完毕 | 保留完整草稿，补问；不自动定稿 |
| 小件机遗留1件 | 不等同“异常邮件未一小时一清”，确认异常、清理条件及违规次数 |
| 异常邮件按次 | official-050，100元/次；10件不等于10次 |
| 散落滞留 | official-012，严格超过2小时才满足时长；恰好2小时/不足2小时不套用 |
| 装车破损未拦截出局 | official-079，100元/件；未出局不能套用 |
| 吸烟 | official-107，实际吸烟、非吸烟区、同次事项确认后固定500元；携带打火机不等同吸烟 |
| 未穿工服 | official-114，符合实际触发条件且同次事项后固定300元 |
| 人为隐匿、毁弃、窃取 | official-013，须实际核实，固定价不得乘邮件件数 |
| 重件压轻件 | 召回附件official-214/215；裁量200—2000元/次，**未擅自定200元** |
| 缺岗、比例、分档、倍数、复杂责任 | 可检索、显示草稿及原文；未经核准的结构化条件不自动给价 |

自动价当前为8条原文哈希锁定规则，其余规则分类不等于自动核价授权。业务还需确认20260825原件是否现行、裁量规则如何核准、固定事项的业务计数口径。手工填单仍保留，仅授权设备可正式生成，其输入由填写人负责核对。

## 86份历史文书与写作质量

有效样本86，排除锁定文件4；ZIP SHA-256 `103258359dbec4974962432abbb46c81cc73f34ed8088afc42a0c634379c33a4`。
全量结构统计：77份两段式、5份三段式、4份一段式；正文105—201字，中位145.5字；字号以16pt为主（1509个显式32半磅记录，不是1509份文书）。分类：卸车19、装车12、小件机27、安全生产3、收容5、矩阵5、错发白送5、现场管理10。分类为自动归纳，未宣称人工逐条核准。

保留12条去除历史日期/单号/姓名/计价结论的写法参考，每次最多选1条整改语气，不能复制样本事实。Mock验证完整事实+具体整改保留，以及中文金额、数字单位挪用、模型条件不足、旧签名失效等保护；这不是对真实模型自然语言质量的盲评。所有未被程序识别的语义新增事实仍需填报人核对，不能宣称穷尽自然语言幻觉。

## Token、缓存与成本

默认 `deepseek-flash`、关闭thinking、JSON、900输出上限；超时/429/无效JSON不自动重试。实际模型配置可从登录后的 `/api/ai/status` 查看。密钥仅服务器私有环境，不进入浏览器资源。

本地缓存TTL默认900秒、256项、错误冷却20秒；键含权限范围、事实、公司、模型、提示词/文风/制度摘要。日期班次在服务端安全重组；不同设备不共享私有结果。相同在途请求合并；已知条件答复和整改文字确认不重新收费。

A/B/C四个现场问题的**离线重建请求**在 `output/upgrade-20261013/prompt-comparison.json`：A全目录+12样例约208946—208957字符；B稳定前缀约194116—194127字符；C候选检索约2745—7256字符。字符减少不能换算成真实Token降幅；A不是历史API日志。所有真实usage、官方缓存命中和实际费用字段明确为null，**未执行付费A/B/C实验**。

后端对真实API返回的input/cache-hit/cache-miss/output/total Token、时延、失败原因和估算人民币落库，仅存元数据，不存现场全文、人员、密钥、Prompt或响应。后台显示今日及近7天、缓存率、成功率、P95、平均完成稿估算费；缺usage不当0元。平均完成稿次数包括缓存完成与续处理，不等于正式归档单据唯一账单。

配置价按[DeepSeek官方价格页](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)核对：人民币/百万Token，Flash高峰缓存命中0.04、未命中2、输出8；低峰0.02、1、4。节假日由环境配置补齐，最终以服务商账单为准。官方前缀缓存按[缓存说明](https://api-docs.deepseek.com/guides/kv_cache/)尽力命中；[关闭思考模式](https://api-docs.deepseek.com/guides/thinking_mode/)使用官方参数。

## 测试与视觉结果

- 后端常规：**128 passed / 1 opt-in skipped**；跳过的是实际LibreOffice整链测试，不是失败隐藏。
- opt-in实际文书链另行执行：**1 passed**；Mock AI、独立SQLite测试库，两模拟手机并发生成，顺序编号不同，Word/PDF真实转换、归档、跨设备下载拒绝、幂等重试通过。不是两部真实手机或PostgreSQL压测。
- 前端：**52 passed**；TypeScript + Vite生产构建通过。生产依赖 `npm audit --omit=dev`：0项漏洞。开发依赖此前审计存在待处理项，未做破坏性强制升级。
- 本地数据库备份副本迁移03→04→05成功；assessments/users/assessment_documents/quick_submissions数量保持一致，SQLite integrity_check=ok。正式PostgreSQL迁移/备份恢复未执行。
- 24条历史检索场景覆盖附件，外加口语吸烟/工装/重压轻等回归。计价Python覆盖率此前单模块89%；不是全仓80%覆盖率。
- Playwright 320/390宽度浏览器检查；Mock超时输入保留、草稿可见及单项补问检查。320日期改成单列以免日期被裁。真实微信分享/实体手机 **NOT VERIFIED**。
- 真实生成卸车40、吸烟500、装车2件200示例，均DOCX→LibreOffice PDF→PNG查看。正文宋体16pt、两真实段落、首行两字、双端对齐；按原模板参考恢复约330pt正文填写区，不重新设计标题/主表/审批/备注。页脚16pt右定位制表位避免空格凑位置；10个中文宽度以内的班组+检查人单行，超出明确拒绝而不静默缩小。无限长姓名不可能无损塞进原单行，不声称支持。
- 最新可交付示例为 `output/upgrade-20261013/documents/{unloading,smoking,long-footer}.{docx,pdf,png}`；`*-render`是中间过程文件，不能替代最新根目录证据。
- 视觉检查确认最新三个示例标题、表格线、审批区、备注完整、金额一致、日期单行，无图片遮罩。Windows宋体结果通过；Linux/Noto替代字体须在部署镜像再次渲染确认。

## 首次本地使用

1. 打开本地首页，填班组姓名，在“本机出单授权”登记一次，记录登记码。
2. 管理员进入后台“制度”页，核实本人及登记码后授权设备；核对制度原件、当前规则及计价摘要后才点击制度核准。
3. 回手机首页刷新授权。日常无需登录；改姓名/班组、清除浏览器数据或换设备需要重新登记。
4. 不满足适用条件时不应为了出单随意点“是”；完整草稿保留，可核对原文或走授权人员的手工填报。

## 部署、备份与回滚（本轮未执行生产操作）

上线前：暂停生产API写入；记录当前镜像/提交/模板SHA-256；使用pg_dump custom格式备份数据库并检查pg_restore --list；备份独立文书卷及仅root可读的服务器环境配置，离机保存。必须在独立PostgreSQL测试实例做恢复和文书哈希核验，不能只校验压缩包可打开。

构建本次确定提交的API/Web镜像，固定tag或digest，不盲用latest；Compose保留持久卷、API单Worker、LibreOffice串行、2GB Swap和日志轮转。执行Alembic至20261013_05，仅新增元数据/授权表及QuickSubmission可空AI摘要列；检查319条、8个原文锁定价、模板版本20261013-2、Flash配置及私有密钥。先回环临时端口验收登录、授权、草稿、正式编号、两人并发、Word/PDF、重启持久化、备份恢复、Linux字体，再恢复入口。不得公开5432。

Vite构建剔除完整规则JSON，Nginx拒绝该静态路径，完整目录由登录且有权限的后端接口提供；源码仓库已有的公开历史无法仅靠本地修改追溯收回。不要发布本地验收资料、`.tmp`、私有环境、数据库或真实历史单给公开静态站。

回滚优先停止写入、换回已记录旧镜像和旧模板；新增数据库字段可保留以避免删除授权/用量审计。若必须恢复数据库，先另存升级后的完整数据，再把数据库与文书卷恢复至同一备份时点，并核验账号、最新正式编号和文件哈希。不要在生产随意downgrade、reset或覆盖数据。本地原始库及文书在 `.tmp/local-preview/backups/20261013-*` 已保留。

## 仍需业务/现场验收

现行制度20260825原件及版本关系；其余复杂裁量结构化核准；真实Flash输出质量和低额度A/B/C实际费用；真实手机/微信分享；Linux镜像字体和一页版式；真实PostgreSQL竞争、容器重启、正式备份恢复。未具备这些证据前，不把本地PASS称为正式上线验收通过。
