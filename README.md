# Telegram 用户账号自动回复程序（CLI 版本）

## 说明
这是一个基于 Python + Telethon 的 Telegram 用户账号自动回复程序。
不是 Bot 项目，不使用 Bot API，不使用 bot token。

## 当前功能
- Telegram 用户账号登录
- Session 持久化
- 私聊新消息监听
- 固定关键词自动回复
- 多账号支持（配置文件方式）
- 日志输出到终端和文件
- 基础异常处理
- FloodWait 捕获

## 项目结构
project/
├─ main.py
├─ requirements.txt
├─ README.md
├─ app/
├─ config/
├─ sessions/
└─ logs/

## 安装依赖
```bash
pip install -r requirements.txt