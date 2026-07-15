# WQTG 浏览器原生工作台 2.0

这是一次干净重构后的独立版本：账号登录、群组解析、资料维护、素材发送、消息链接转发和任务执行全部通过 Telegram Web 与每账号独立 Chromium Persistent Context 完成。

旧版用户客户端、API ID/API Hash、`.session` 登录链、API 批量工作台及其无使用场景的服务和页面均已从生产代码树删除。迁移器只读取仍有价值的数据，不运行任何旧模块。

## 核心约束

- 一个账号对应一个唯一 Profile、一个独立浏览器 Worker、一个固定环境档案。
- 账号没有账号组、静态代理、预期出口 IP 或健康检测结果时，不能启用和启动。
- 代理失败后直接阻断，浏览器不会回退本机网络。
- 浏览器启动时验证 HTTP 出口、浏览器出口、DNS-over-HTTPS 请求链和 WebRTC 候选地址。
- 首次真实运行后保存浏览器版本、User-Agent、Navigator、Screen、时区、语言、Canvas、WebGL、Audio 和字体检测摘要；后续运行发生变化时阻断启动，避免环境漂移。
- 浏览器工作台只显示当前选中账号的画面；其他账号 Worker 和页面保持运行但不输出画面。
- 群组以标准化 `t.me` 链接为主标识，`observed_chat_id` 只是可选观测信息，任务不依赖数字 ID。
- 任务仅允许发送到已加入、可发言、浏览器验证通过并人工批准的白名单群组。
- 账号冷却、目标群冷却、每日上限、模板去重窗口、发送前预览和平台警告停机均为强制策略。
- 不自动加入未知群组，不绕过验证码、二步验证、平台风控或权限限制。

## 11 个一级页面

1. 运行总控
2. 账号中心
3. 账号组与静态 IP
4. 浏览器工作台
5. 群组管理
6. 素材与模板
7. 广告任务
8. 执行记录
9. 账号资料维护
10. 自动化定位
11. 系统设置与诊断

## 架构

```text
PySide6 MainWindow
├─ SQLite transaction data layer
├─ BrowserRuntimeManager
│  ├─ BrowserWorker(account A) -> persistent Chromium profile A
│  ├─ BrowserWorker(account B) -> persistent Chromium profile B
│  └─ BrowserWorker(account C) -> persistent Chromium profile C
├─ Strict proxy policy and health records
├─ Telegram Web actions
├─ Authorized task runner / scheduler
├─ Workflow and locator engine
└─ Audit, diagnostics, backup and one-way migration
```

运行数据默认位于：

```text
%LOCALAPPDATA%\WQTG浏览器原生版\
├─ data\wqtg.db
├─ profiles\<phone>\chromium-data\
├─ profiles\<phone>\environment.json
├─ profiles\<phone>\screenshots\
├─ assets\
├─ logs\
├─ backups\
└─ secrets\
```

验证码网址和代理密码使用 Windows DPAPI 加密。非 Windows 开发环境使用权限受限的本地 Fernet 密钥。审计记录会屏蔽验证码网址、密码、验证码、Cookie、LocalStorage 和 Token。

## Windows 安装

要求 Python 3.11、Git 和可用的静态代理。

```powershell
cd D:\编程\WQTG-guanggao
PowerShell -ExecutionPolicy Bypass -File .\scripts\install.ps1
```

安装脚本会：

1. 重建 `.venv`。
2. 安装依赖。
3. 安装 Playwright Chromium。
4. 编译所有 Python 文件。
5. 运行全部测试。

启动：

```powershell
.\.venv\Scripts\python.exe main.py
```

## 首次配置顺序

1. 在“账号组与静态 IP”创建代理，必须填写预期出口 IP。
2. 运行代理测试，状态必须变为 `healthy`。
3. 创建账号组并绑定代理。
4. 在“账号中心”按 `手机号|验证码网址` 导入账号。
5. 分配账号组；未定稿环境会自动对齐代理时区和账号组语言。
6. 启用账号并启动浏览器。
7. 在“浏览器工作台”选中账号；被选中账号显性显示，其他账号隐性运行。
8. 执行登录；验证码网址会在同一账号、同一代理的 BrowserContext 内访问。
9. 导入群组链接，使用当前已登录账号逐条解析。
10. 只对确认有发布权限的群组点击“批准白名单”。
11. 创建模板和任务，确认目标、配额、冷却、去重和预览后执行。

## 环境档案

环境档案先生成现实参数组合，首次浏览器启动后由真实 Chromium 运行结果定稿。定稿后不会自动随机或改写。只有同时满足以下条件才能重新生成：

- 浏览器已停止；
- 没有活动任务；
- Profile 已完成备份。

Chromium 升级导致真实指纹变化时，系统会阻断启动，而不是静默更新环境。

## 群组链接导入

支持：

```text
https://t.me/example_group
@example_group
https://t.me/+privateInviteCode
https://t.me/joinchat/privateInviteCode
```

公开用户名统一转为小写并去重。私有邀请链接只有账号拥有访问权限后才能读取完整信息。数字 Chat ID 不作为任务依赖。

## 模板类型

- 纯文本
- 本地图片、视频或文件素材
- 多素材本地克隆
- Telegram 消息链接转发

本地素材在发送前检查文件是否存在。消息链接模板通过 Telegram Web 转发界面处理；源消息或目标群不可访问时明确失败或转人工。

## 自动化定位与资料维护

定位策略支持：

- CSS
- 文本
- Role
- 坐标
- 多策略回退

浏览器工作台提供“定位拾取模式”。点击页面元素后会返回 CSS 路径、文本、Role、ARIA、Placeholder 和边界信息。

资料维护工作流进入对应账号 BrowserWorker 的串行命令队列，不会再次启动同一个 Profile。步骤支持导航、等待、点击、填写、输入、按键和上传；失败会截图并按 `stop_on_error` 决定是否终止。

## 旧版数据迁移

在“系统设置与诊断”选择旧版配置目录。迁移前会创建：

```text
backups\pre-browser-refactor-YYYYMMDD-HHMMSS\
```

可迁移手机号、验证码网址、国家、群组链接等仍有价值的数据。旧 API 凭据和旧会话文件不会迁移，也不会被执行。

## 验证命令

```powershell
.\.venv\Scripts\python.exe -m compileall -q app main.py
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m playwright install --dry-run chromium
```

CI 在 Windows + Python 3.11 上执行编译和测试。
