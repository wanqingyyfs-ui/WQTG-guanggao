# 万青 TG 群发任务

这是一个基于 Python、PySide6、Telethon 的 Telegram 用户号群发任务面板。

本项目不是 Bot 项目，不使用 Bot API，不使用 bot token。  
它使用 Telegram 用户账号登录，并通过本地 session 持久化账号状态。

## 当前最终版功能

- Telegram 用户号登录
- 多账号管理
- 多群组管理
- 多任务管理
- 多模板管理
- 素材群监听
- 素材消息自动入库为模板
- 单账号发送
- 多账号池轮询发送
- 单群组发送
- 多群组池轮询发送
- 多模板随机发送
- 发送前概率判定：
  - 广告概率
  - 噪音概率
  - 跳过概率
- 噪音池随机发送
- 间隔调度
- 每日定时调度
- 账号延迟随机范围
- 群组延迟随机范围
- 毫秒级延迟配置
- 任务执行日志
- GUI 运行日志
- FloodWait、无发言权限、账号未登录等常见异常处理
- 配置页自动保存
- 噪音池手动保存
- 账号、群组、任务、模板列表排序
- 排序结果保存并影响实际发送顺序
- 账号、群组、任务、模板配置使用 QDockWidget 浮动/停靠面板

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
│  │  ├─ forms/
│  │  ├─ pages/
│  │  └─ widgets/
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
noise_pool.json
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

```bash
pip install -r requirements.txt
pip install -r requirements-build.txt
pyinstaller --clean --noconfirm 万青TG群发任务.spec
```

打包完成后，EXE 通常位于：

```text
dist\万青TG群发任务.exe
```

## 使用流程

### 1. 配置基础参数

打开“配置管理”页。

配置页会自动保存，不需要手动点击保存。  
群发运行中，发送相关配置会锁定，界面外观配置仍可调整。

重点配置：

- 广告概率
- 噪音概率
- 跳过概率
- 素材监听账号
- 素材群 Chat ID
- 新增任务默认值
- 面板字号和宽高

概率总和必须等于 100。

### 2. 添加账号

打开“账号管理”页，点击“新增账号”。

账号配置会在右侧 QDockWidget 浮动/停靠面板中打开。  
填写：

- 账号名称
- API ID
- API Hash
- 手机号
- Session 名称
- 启用状态

保存后账号列表会更新。

### 3. 登录并启动账号

选择账号后点击：

```text
登录账号
启动该账号
```

也可以在“运行总控”页点击：

```text
启动全部账号
停止全部账号
```

### 4. 添加目标群组

打开“群组管理”页，点击“新增群组”。

填写：

- 群组名称
- Chat ID
- Username/链接
- 备注
- 启用状态

Chat ID 通常是 `-100` 开头的超级群或频道 ID。

### 5. 配置噪音池

打开“噪音配置”页。

噪音池不会自动保存。  
新增、删除、排序、编辑后必须点击：

```text
保存噪音池
```

噪音池允许重复内容。重复添加同一条内容可以提高随机命中权重。

### 6. 管理模板

模板由素材监听自动创建。

打开“模板管理”页，可以：

- 配置模板名称
- 配置启用状态
- 配置备注
- 删除模板
- 上移/下移模板顺序

模板来源账号、来源 Chat ID、来源消息 ID、消息类型、发送模式等内部字段会被保留，不在普通表单中编辑。

### 7. 创建群发任务

打开“任务管理”页，点击“新增任务”。

任务配置在 QDockWidget 浮动/停靠面板中打开。

可配置：

- 任务名称
- 启用状态
- 发送账号池
- 账号轮换模式
- 账号延迟最小/最大秒数
- 目标群组池
- 群组轮换模式
- 群组延迟最小/最大秒数
- 消息类型
- 文本内容或模板池
- 调度模式
- 间隔秒数
- 每日时间
- 备注

延迟输入支持 3 位小数，内部按毫秒保存。

### 8. 启动群发

打开“运行总控”页。

只保留四个运行控制按钮：

```text
启动全部账号
停止全部账号
启动群发
停止群发
```

群发运行中，不能修改账号、群组、任务、模板、噪音池等会影响发送的数据。  
需要先点击：

```text
停止群发
```

## 发送逻辑

每次发送前，系统根据配置页的概率进行判定：

1. 命中广告概率：从任务选定的启用模板池中随机选择一个模板发送，或发送纯文本。
2. 命中噪音概率：从噪音池中随机选择一条内容发送。
3. 命中跳过概率：本轮什么都不发送。

如果任务选择了多个模板，每次发送会随机选择一个启用模板。  
未启用模板不会参与随机选择。

## 注意事项

- Telegram 用户号操作存在平台风控风险。
- 高频群发可能触发 FloodWait。
- 请合理设置发送间隔、账号延迟、群组延迟。
- 账号必须先登录成功并拥有目标群发言权限。
- 模板发送要求发送账号能访问来源素材群和目标群。
- 不建议把 session、配置、日志、EXE 产物提交到 Git。
- 群发运行中修改发送数据会被阻止，并提示“请先停止群发功能”。

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
