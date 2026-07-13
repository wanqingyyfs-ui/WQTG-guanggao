# Telegram 自动化定位与故障处理

本项目的 Telegram Web 和 my.telegram.org 按钮定位已统一放入：

`app/vendor/tgapipldc/data/automation_locators.json`

程序首次运行会自动生成默认配置。配置按以下顺序回退：

1. Playwright role/accessible name
2. CSS
3. 文本或图标文本
4. XPath
5. 相对坐标（默认关闭）

## 在界面中调整按钮

运行 `python main.py`，打开“自动化定位设置”页：

1. 选择定位目标。
2. 可直接编辑目标 JSON，并点击“保存目标”。
3. 选择一个测试 Profile，点击“打开校准浏览器”。
4. 在网页中按住 `Ctrl + Shift` 点击真实按钮。
5. 程序会记录 CSS、文本和相对坐标，并自动更新配置。
6. 关闭校准浏览器后重新运行对应批量任务。

相对坐标使用页面宽高比例，而不是固定像素。建议仅作为最后兜底使用。

## Profile 占用

同一个 Profile 不能被 API 工作台、资料维护、校准浏览器或另一个 WQTG 实例同时打开。发生占用时，日志会显示占用 PID、主机和任务 ID。先关闭占用浏览器或停止对应任务后再运行。

## 失败诊断

定位失败会在以下目录保存截图、HTML 和运行信息：

`app/vendor/tgapipldc/logs/automation_failures/`

批次结构化结果位于：

`app/vendor/tgapipldc/logs/job_results/`

## 数据安全

账号、代理和资料维护配置采用临时文件写入后原子替换。覆盖前会保留同名 `.bak` 文件。不要将 `data`、`profiles`、`logs` 或 API CSV 提交到 GitHub。

## 批次行为

“修改全部选项”不再无条件在第一个失败账号处停止。是否停止后续账号统一由“遇到账号错误后停止全部流程”决定。
