# 微信小程序、职工网页与管理网站（2026-11-23）

## 三个入口

| 入口 | 地址 | 使用者 | 是否登录 |
| --- | --- | --- | --- |
| 微信小程序 | 微信内打开 | 普通职工 | 不需要 |
| 职工网页版 | `https://正式域名/` | 普通职工（手机或电脑浏览器） | 不需要 |
| 管理网站 | `https://正式域名/admin`（旧地址 `/#manage` 仍可用） | 管理员、主管、领导 | 需要账号 |

三者共用同一个 FastAPI 后端。小程序和职工网页调用免登录接口 `/api/quick/*`，用本机随机凭证区分设备；管理网站调用需要登录令牌的接口。普通职工的填报流程、AI 整理、金额核定、正式编号与 Word/PDF 归档规则都与 10 月 15 日验收版一致。

## 代码结构

```
miniprogram/                 微信开发者工具的项目根目录（导入时选这个目录）
  project.config.json        AppID（暂用游客号 touristappid）、TypeScript 编译插件
  tsconfig.json              小程序类型检查（npm run typecheck:mp）
  src/                       小程序代码（miniprogramRoot）
    shared/                  与职工网页共用的填报逻辑，纯 TypeScript，禁止引用 wx/window/document
      types.ts               /api/quick 接口数据结构
      fill.ts                表单状态流转、生成前校验、界面派生数据
      controller.ts          AI 调用、幂等提交、草稿与班组姓名保存
      format.ts ids.ts errors.ts  金额大写、日期、凭证与请求编号、错误提示
    platform/                小程序平台层：wx.request/downloadFile 封装、本地存储、安全随机数
    pages/fill               填写考核单
    pages/result             生成结果：预览、发到微信群、发送 PDF、打开 Word/PDF、复制文字
    pages/records            我的记录（本机生成的考核单）
    config.ts                后端地址：开发版连本机，体验版/正式版连正式域名
  tests/                     共用逻辑和页面冒烟测试（vitest，不会打包进小程序）
src/employee/                职工网页版（React），通过 @shared 引用同一套共用逻辑
src/App.tsx                  管理网站（业务功能未改，改为按需加载）
backend/                     新增分享图片接口 GET /api/quick/assessments/{id}/documents/png
```

**修改填报流程时**：先改 `miniprogram/src/shared`，小程序和网页同时生效，再分别调整两端界面。共用逻辑的测试在 `miniprogram/tests`。

## 本地开发

1. 后端：按 README「本地开发」启动，地址 `http://127.0.0.1:8000`。没有配置 `DEEPSEEK_API_KEY` 时，两端自动切换为手动填写，不会产生 AI 费用。
2. 网页：`npm.cmd run dev`，职工网页 `http://127.0.0.1:5173/`，管理网站 `http://127.0.0.1:5173/admin`。
3. 小程序：
   - 微信开发者工具 →「导入项目」→ 目录选 `miniprogram`（不是仓库根目录）→ AppID 用测试号或真实 AppID。
   - 右上角「详情 → 本地设置」勾选「不校验合法域名、web-view（业务域名）、TLS 版本以及 HTTPS 证书」。这个设置保存在 `project.private.config.json`，已被 Git 忽略。
   - 开发版默认连 `http://127.0.0.1:8000`。用手机真机调试时，把 `miniprogram/src/config.ts` 里 develop 的地址改成电脑的局域网 IP，并在手机上打开调试模式。
4. 检查命令：

```powershell
npm.cmd test
npm.cmd run typecheck:mp
npm.cmd run build
python -m pytest backend/tests -q
```

## 上线清单（需要单位负责人办理）

1. 注册微信小程序，拿到 AppID，填入 `miniprogram/project.config.json` 的 `appid`。建议用单位（企业）主体注册：个人主体可选的服务类目少，内部考核工具可能无法通过审核。
2. 在微信公众平台完成「小程序备案」。
3. 服务器域名完成 ICP 备案并启用 HTTPS（README 中的 Caddy 会自动申请证书）。
4. 小程序后台「开发管理 → 开发设置 → 服务器域名」：**request 合法域名**和 **downloadFile 合法域名**都填 `https://正式域名`。
5. 确认 `miniprogram/src/config.ts` 中 trial/release 的地址就是正式域名。当前预设为 `https://kaohe.zzb9.cn`；该域名目前仍指向旧的 GitHub Pages 静态站，DNS 切换到正式服务器之前，体验版和正式版连不上后端。
6. 「设置 → 基本设置 → 基础库最低版本设置」设为 **2.17.3 或更高**（本机凭证使用的安全随机数接口从该版本起提供）。
7. 「设置 → 服务内容声明 → 用户隐私保护指引」声明使用**剪切板**（结果页「复制文字」调用 `wx.setClipboardData`）。
8. 在开发者工具点「上传」→ 小程序后台提交审核 → 审核通过后发布。

## 小程序与网页的差异

- **发到群里**：小程序有「发到微信群」（`wx.showShareImageMenu`，发送图片）、「发送 PDF 文件」（`wx.shareFileMessage`），也可以长按图片发送。网页使用系统分享（安卓 Chrome、iOS Safari 支持分享文件）；微信内置浏览器不支持网页分享文件，只能长按图片发送，所以在微信里建议用小程序。
- **分享图片**：两端都使用后端由归档 PDF 渲染的 PNG（A4，1191×1684）。网页不再在浏览器里加载 pdf.js，首屏下载量明显减少。
- **本机记录互不相通**：小程序的凭证存在微信本地存储（同一微信号、同一手机），网页的凭证存在浏览器（沿用旧网页的存储键，升级后原有的本机记录仍能看到）。小程序生成的单据在网页「我的记录」里看不到，反之亦然；管理网站可以看到全部单据。
- **AI 签名的短期恢复**：网页保存在会话存储里，关闭标签页即失效；小程序没有会话存储，签名保存在本地存储，45 分钟后失效。后端仍会校验签名有效期、设备和制度版本摘要。

## 安全边界（沿用原设计）

- 免登录接口只能读取本机凭证生成的记录，不能访问台账、统计、作废和管理接口。
- 班组和姓名由使用者自己填写，不代表经过身份认证。
- 每个设备每小时最多渲染 120 次分享图片，超过返回 429。
- 「生成考核单」按钮不放在表单提交里，在输入框中按回车不会误生成正式单据。

## 以后可以做的增强

- 用 `wx.login` 静默获取 openid 并与本机凭证绑定（AppSecret 只保存在服务器），换手机或清除微信数据后仍能看到自己的记录；职工仍然不需要登录。

## 2026-11-23 验证情况

| 项目 | 结果 |
| --- | --- |
| 共用逻辑与小程序页面测试（vitest） | 41 项通过：状态流转、AI 结果处理、改正文重签、幂等重试、迟到的 AI 结果被丢弃，以及在模拟 `wx` 环境下运行三个页面 |
| 前端全部测试 | 84 项通过（含职工网页平台层与渲染测试） |
| 小程序类型检查 | `tsc` 配合官方类型包 `miniprogram-api-typings` 通过 |
| 小程序模板与样式 | 用开发者工具自带的 WXML 编译器 wcc、WXSS 编译器 wcsc 编译通过 |
| 网页生产构建 | 通过；职工端与管理网站分开打包 |
| 后端 | 新增 4 项分享图片测试通过；完整测试结果见交接记录 |
| 本地联调（Chromium，375px 手机宽度与电脑宽度） | 免登录手动出单 → 本机 LibreOffice 生成 Word/PDF → 显示分享图片 → 我的记录 → `/admin` 登录后工作台统计到该单据；转换超时后表单保留，重试未重复编号 |
| **未验证** | 微信开发者工具模拟器和真机运行（工具的「服务端口」未开启，命令行无法调用）；真实微信发群；AI 实时整理（本地未配置密钥）；生产 Linux/PostgreSQL 环境 |
