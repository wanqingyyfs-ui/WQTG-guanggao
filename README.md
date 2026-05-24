# 万青 TG 群发任务

基于 Python、PySide6、Telethon、Playwright 的 Telegram 用户号任务面板。

本项目不是 Bot 项目，不使用 Bot API，不使用 bot token。项目使用 Telegram 用户账号登录，通过本地 Telethon session 保存账号登录状态；同时集成 tgapipldc 工作台，用于代理检测、账号代理绑定、Telegram Web 登录、my.telegram.org API 获取、CSV 导入和 yanzheng 自动验证码登录。

## 功能总览

### WQTG 群发任务面板

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
- 发送前概率判定：广告、噪音、跳过
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

### API 批量工作台

新增“API 批量工作台”页面，集成原 tgapipldc 的核心流程：

- 在面板内编辑并覆盖 `accounts.csv`
- 在面板内编辑并覆盖 `proxies.csv`
- CSV 第一行表头锁定，正文区只编辑第二行开始的数据
- 检测代理，对应原命令：`python src\test_proxies.py`
- 构建可用代理池，对应原命令：`python src\build_proxy_pool.py`
- 绑定账号和代理，对应原命令：`python src\assign_proxies.py`
- 批量运行 Telegram Web / my.telegram.org 自动流程，对应原命令：`python src\login_telegram_web.py`
- 自动导出 `api_id` 和 `api_hash` 到 `csv/api.csv`
- 从 `api.csv` 导入 WQTG 账号
- 使用 yanzheng 页面自动读取验证码和 2FA，批量登录 WQTG Telethon session
- 保存浏览器 Profile 目录，便于后续扩展个人资料更新等浏览器操作

## 技术栈

- Python 3.11+
- PySide6
- Telethon
- Playwright
- requests
- pandas
- python-dotenv
- loguru
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
│  │  ├─ models.py
│  │  ├─ config_loader.py
│  │  ├─ telegram_client_manager.py
│  │  └─ ...
│  ├─ gui/
│  │  ├─ dialogs/
│  │  ├─ forms/
│  │  ├─ pages/
│  │  │  ├─ dashboard_page.py
│  │  │  ├─ tgapipldc_page.py
│  │  │  └─ ...
│  │  ├─ widgets/
│  │  └─ tgapipldc_panel_bootstrap.py
│  ├─ services/
│  │  ├─ runtime_service.py
│  │  ├─ tgapipldc_workspace_service.py
│  │  ├─ tgapipldc_proxy_service.py
│  │  ├─ tgapipldc_account_bind_service.py
│  │  ├─ tgapipldc_runner_service.py
│  │  ├─ tgapipldc_import_service.py
│  │  ├─ yanzheng_login_provider.py
│  │  └─ ...
│  └─ vendor/
│     └─ tgapipldc/
│        ├─ src/
│        ├─ data/
│        ├─ csv/
│        ├─ logs/
│        └─ profiles/
```

## 运行时数据目录

WQTG 主程序默认运行数据保存在 Windows 用户目录：

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

主程序配置文件：

```text
accounts.json
groups.json
tasks.json
templates.json
settings.json
noise_pool.json
```

主程序日志文件：

```text
app.log
task_send.jsonl
```

## tgapipldc 工作目录

API 批量工作台使用项目内置工作目录：

```text
app/vendor/tgapipldc/
```

子目录说明：

```text
app/vendor/tgapipldc/src/       # 迁移过来的 tgapipldc 原始脚本
app/vendor/tgapipldc/data/      # 账号、代理、绑定结果、代理检测结果
app/vendor/tgapipldc/csv/       # API 导出结果、失败账号结果
app/vendor/tgapipldc/logs/      # tgapipldc 日志
app/vendor/tgapipldc/profiles/  # Playwright 浏览器 Profile 登录目录
```

以下目录属于运行数据，默认不应该提交到 Git：

```text
app/vendor/tgapipldc/data/
app/vendor/tgapipldc/csv/
app/vendor/tgapipldc/logs/
app/vendor/tgapipldc/profiles/
```

## 安装依赖

建议使用虚拟环境：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
```

安装 Playwright Chromium：

```powershell
python -m playwright install chromium
```

如需打包 EXE，再安装打包依赖：

```powershell
python -m pip install -r requirements-build.txt
```

不要直接混用其它项目的 `pip.exe`。如果出现 pip 指向旧项目路径的问题，删除 `.venv` 后重新创建虚拟环境。

## 启动程序

```powershell
python main.py
```

## 使用流程：WQTG 主功能

### 1. 配置基础参数

打开“配置管理”页。

配置页会自动保存，不需要手动点击保存。群发运行中，发送相关配置会锁定，界面外观配置仍可调整。

重点配置：

- 广告概率
- 噪音概率
- 跳过概率
- 素材监听账号
- 素材群 Chat ID
- 新增任务默认值
- 面板字号和宽高

概率总和必须等于 100。

### 2. 添加或导入账号

可以通过两种方式添加账号：

1. 在“账号管理”页手动新增账号。
2. 在“API 批量工作台”页通过 tgapipldc 自动获取 API 后导入账号。

手动新增账号需要填写：

- 账号名称
- API ID
- API Hash
- 手机号
- Session 名称
- 启用状态

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

噪音池不会自动保存。新增、删除、排序、编辑后必须点击：

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

运行总控提供四个主控制按钮：

```text
启动全部账号
停止全部账号
启动群发
停止群发
```

群发运行中，不能修改账号、群组、任务、模板、噪音池等会影响发送的数据。需要先点击：

```text
停止群发
```

## 使用流程：API 批量工作台

### 1. 准备 accounts.csv 数据

面板中 `accounts.csv` 的第一行表头已锁定：

```csv
phone,country,profile_dir,status,yanzheng
```

正文区从第二行开始填写数据，每行一个账号：

```csv
14255871436,US,profiles/14255871436,pending,https://accac.cc/47d83e8d-1abf-48d9-8655-3bcbf77418c1/GetHTML
```

字段说明：

| 字段 | 说明 |
| --- | --- |
| phone | 手机号，可以不带 `+`，程序会结合 country 转换 |
| country | 国家代码，例如 `US`、`KH`、`TH`、`CN` |
| profile_dir | 浏览器 Profile 目录，例如 `profiles/14255871436` |
| status | 初始状态，建议填写 `pending` |
| yanzheng | yanzheng 页面地址，用于读取验证码和 2FA |

点击：

```text
覆盖 accounts
```

覆盖规则：保留第一行表头，删除旧数据行，再写入面板正文区的新数据。

### 2. 准备 proxies.csv 数据

面板中 `proxies.csv` 的第一行表头已锁定：

```csv
raw_proxy
```

正文区从第二行开始填写数据，每行一个代理：

```csv
Qg8Ajet4-res-th-sid-843678599-sidtime-70:GlVF6XC@proxy.global.ip2up.com:12348
```

点击：

```text
覆盖 proxies
```

覆盖规则：保留第一行表头，删除旧数据行，再写入面板正文区的新代理。

### 3. 检测代理

点击：

```text
检测代理
```

会读取：

```text
app/vendor/tgapipldc/data/proxies.csv
```

输出：

```text
app/vendor/tgapipldc/data/proxy_test_results.csv
```

检测结果会包含：

```text
raw_proxy
masked_proxy
exit_ip
duplicate
status
note
```

### 4. 构建代理池

点击：

```text
构建池
```

会读取代理检测结果，只保留可用且出口 IP 不重复的代理。

输出：

```text
app/vendor/tgapipldc/data/usable_proxies.csv
```

### 5. 绑定账号和代理

点击：

```text
绑定
```

会读取：

```text
app/vendor/tgapipldc/data/accounts.csv
app/vendor/tgapipldc/data/usable_proxies.csv
```

输出：

```text
app/vendor/tgapipldc/data/account_proxy_map.csv
```

绑定结果包含手机号、国家、Profile、yanzheng、代理、出口 IP 等信息。

### 6. 批量获取 API

点击：

```text
获取 API
```

会调用迁移后的 `login_telegram_web.py` 流程：

1. 检测代理实时出口 IP。
2. 启动 Playwright 持久化浏览器 Profile。
3. 检测浏览器出口 IP。
4. 打开 Telegram Web。
5. 使用 yanzheng 页面读取 Telegram 登录验证码。
6. 如有 2FA，使用 yanzheng 页面读取 `pass2fa`。
7. 登录 Telegram Web。
8. 打开 #777000。
9. 登录 my.telegram.org。
10. 自动创建或读取 Telegram API 应用。
11. 导出 API 信息。

成功输出：

```text
app/vendor/tgapipldc/csv/api.csv
```

失败输出：

```text
app/vendor/tgapipldc/csv/失败.csv
```

### 7. 导入 API 到 WQTG

点击：

```text
导入 API
```

会读取：

```text
app/vendor/tgapipldc/csv/api.csv
app/vendor/tgapipldc/data/account_proxy_map.csv
```

然后生成或更新 WQTG 账号配置。账号名默认按手机号生成，例如：

```text
tg_14255871436
```

### 8. 批量登录 WQTG

点击：

```text
登录 WQTG
```

会逐个账号执行 Telethon 登录。验证码和 2FA 会优先通过 yanzheng 页面自动读取，不再依赖手动弹窗。

成功后会生成 WQTG session：

```text
%LOCALAPPDATA%\万青TG群发任务\sessions\账号名.session
```

## 发送逻辑

每次发送前，系统根据配置页的概率进行判定：

1. 命中广告概率：从任务选定的启用模板池中随机选择一个模板发送，或发送纯文本。
2. 命中噪音概率：从噪音池中随机选择一条内容发送。
3. 命中跳过概率：本轮什么都不发送。

如果任务选择了多个模板，每次发送会随机选择一个启用模板。未启用模板不会参与随机选择。

## Git 提交安全规则

不要提交运行数据、账号、代理、API、浏览器 Profile、session、日志和打包产物。

禁止提交：

```text
app/vendor/tgapipldc/data/
app/vendor/tgapipldc/csv/
app/vendor/tgapipldc/logs/
app/vendor/tgapipldc/profiles/
%LOCALAPPDATA%\万青TG群发任务\sessions\
.venv/
build/
dist/
*.exe
*.log
.env
```

提交前建议检查：

```powershell
git status
git diff --cached --name-status
git ls-files | Select-String "app/vendor/tgapipldc/data|app/vendor/tgapipldc/csv|app/vendor/tgapipldc/logs|app/vendor/tgapipldc/profiles|accounts.csv|proxies.csv|api.csv|失败.csv|.session"
```

如果最后一条命令有输出，说明有敏感文件仍被 Git 追踪，需要先处理后再 push。

## 打包 EXE

安装运行依赖：

```powershell
python -m pip install -r requirements.txt
python -m playwright install chromium
```

安装打包依赖：

```powershell
python -m pip install -r requirements-build.txt
```

打包：

```powershell
pyinstaller --clean --noconfirm 万青TG群发任务.spec
```

打包完成后，EXE 通常位于：

```text
dist\万青TG群发任务.exe
```

首次打包后建议先在本机测试：

1. 打开“API 批量工作台”。
2. 覆盖 `accounts.csv`。
3. 覆盖 `proxies.csv`。
4. 检测代理。
5. 构建代理池。
6. 绑定账号代理。
7. 再测试批量获取 API。

如果 EXE 提示找不到 Playwright 浏览器，需要单独调整 PyInstaller spec 或在目标环境安装 Playwright Chromium。

## 常用验证命令

单文件语法验证：

```powershell
python -m py_compile main.py
```

全量语法验证：

```powershell
python -m compileall app main.py
```

检查依赖导入：

```powershell
python -c "import requests; print(requests.__version__)"
python -c "from playwright.sync_api import sync_playwright; print('playwright ok')"
python -c "from telethon import TelegramClient; print('telethon ok')"
```

## 清理构建产物

```powershell
Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
Get-ChildItem -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force
Get-ChildItem -Recurse -Include "*.pyc","*.pyo" -File | Remove-Item -Force
```

## 注意事项

- Telegram 用户号操作存在平台风控风险。
- 高频、重复、异常行为可能触发 FloodWait、验证码、限制或账号风险。
- 请合理设置发送间隔、账号延迟、群组延迟。
- 账号必须先登录成功并拥有目标群发言权限。
- 模板发送要求发送账号能访问来源素材群和目标群。
- 浏览器 Profile 与 Telethon session 是两套状态，不能混用。
- Playwright Profile 目录可能很大，不能提交到 Git。
- API、API Hash、手机号、代理、yanzheng 地址都属于敏感数据，不能提交到 Git。
- 群发运行中修改发送数据会被阻止，并提示“请先停止群发功能”。
