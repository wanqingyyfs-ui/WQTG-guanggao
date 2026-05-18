# 万青 TG 群发任务

这是一个基于 Python、PySide6、Telethon 的 Telegram 用户号群发任务面板。

本项目不是 Bot 项目，不使用 Bot API，不使用 bot token。  
它使用 Telegram 用户账号登录，通过本地 session 持久化账号状态。

## 当前功能

- Telegram 用户号登录
- 多账号管理
- Session 本地持久化
- 目标群组管理
- 群发任务管理
- 文本消息群发
- 模板消息转发
- 素材群监听
- 素材消息自动入库为模板
- 单账号发送
- 多账号池顺序轮换发送
- 手动发送一次
- 间隔调度
- 每日定时调度
- 随机延迟发送
- 任务执行日志
- GUI 运行日志
- FloodWait、无发言权限、账号未登录等常见异常处理

## 技术栈

- Python 3.11+
- PySide6
- Telethon
- PyInstaller

## 目录结构

```text
project/
├─ main.py
├─ requirements.txt
├─ requirements-build.txt
├─ README.md
├─ app.ico
├─ 万青TG群发任务.spec
├─ app/
│  ├─ core/
│  ├─ gui/
│  └─ services/
```

## 运行时数据目录

默认运行数据保存在 Windows 用户目录：

```text
%LOCALAPPDATA%\万青TG群发任务\
```

主要子目录：

```text
%LOCALAPPDATA%\万青TG群发任务\config\
%LOCALAPPDATA%\万青TG群发任务\logs\
%LOCALAPPDATA%\万青TG群发任务\sessions\
%LOCALAPPDATA%\万青TG群发任务\data\
```

配置文件：

```text
accounts.json
groups.json
tasks.json
templates.json
settings.json
```

日志文件：

```text
app.log
task_send.jsonl
```

## 安装依赖

建议使用虚拟环境：

```bash
python -m venv .venv
```

PowerShell 激活：

```powershell
.venv\Scripts\Activate.ps1
```

安装运行依赖：

```bash
pip install -r requirements.txt
```

如需打包 EXE，再安装打包依赖：

```bash
pip install -r requirements-build.txt
```

## 启动程序

```bash
python main.py
```

## 打包 EXE

先安装运行依赖和打包依赖：

```bash
pip install -r requirements.txt
pip install -r requirements-build.txt
```

使用 spec 文件打包：

```bash
pyinstaller --clean --noconfirm 万青TG群发任务.spec
```

打包完成后，EXE 通常位于：

```text
dist\万青TG群发任务.exe
```

## 使用流程

### 1. 添加账号

打开“账号管理”页，填写：

- 账号名称
- API ID
- API Hash
- 手机号
- Session 名称

然后点击“保存账号”。

### 2. 登录账号

选择账号，点击“登录账号”。

程序会弹窗要求输入 Telegram 验证码。  
如果账号开启了二步验证，还会继续要求输入二步验证密码。

### 3. 启动账号

账号登录成功后，可以点击：

```text
启动该账号
```

也可以在“运行总控”页点击：

```text
启动全部账号
```

### 4. 添加目标群

打开“群组管理”页，填写：

- 群组名称
- Chat ID
- Username/链接
- 备注

Chat ID 通常是 `-100` 开头的超级群或频道 ID。

### 5. 配置素材群监听

打开“运行总控”页，填写：

- 素材账号名
- 素材群 Chat ID

当指定账号在指定素材群中收到新消息时，程序会自动采集为模板。

### 6. 管理模板

打开“模板管理”页，可以查看、编辑、删除模板。

当前模板发送模式使用：

```text
forward
```

`clone` 模式当前未启用。

### 7. 创建群发任务

打开“任务管理”页，配置：

- 任务名称
- 发送账号池
- 轮换模式
- 目标群组
- 消息类型
- 文本内容或模板
- 调度模式
- 随机延迟

轮换模式：

```text
单账号
顺序轮换
```

### 8. 启动调度器

打开“运行总控”页，点击：

```text
启动群发调度
```

停止调度器：

```text
停止群发调度
```

## 注意事项

- Telegram 用户号操作存在平台风控风险。
- 高频群发可能触发 FloodWait。
- 请合理设置发送间隔和随机延迟。
- 账号必须先登录成功并拥有目标群发言权限。
- 模板转发要求发送账号能访问来源素材群和目标群。
- 不建议把 session、配置、日志、EXE 产物提交到 Git。

## 常用验证命令

单文件语法验证：

```bash
python -m py_compile main.py
```

全量语法验证：

```bash
python -m compileall app main.py
```

## 清理构建产物

```powershell
Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
```
