from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "app" / "vendor" / "tgapipldc" / "src"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def replace_once(text: str, old: str, new: str, file_label: str) -> tuple[str, bool]:
    if old in text:
        return text.replace(old, new, 1), True
    if new in text:
        print(f"{file_label} 已经是动态代理逻辑，跳过。")
        return text, False
    raise RuntimeError(f"{file_label} 未找到预期代码块，未修改。请确认文件版本是否匹配。")


def patch_login_telegram_web() -> None:
    path = SRC_DIR / "login_telegram_web.py"
    text = read_text(path)

    old = '''            if browser_ip != realtime_ip:\n                note = f"requests={realtime_ip}, browser={browser_ip}"\n                print("浏览器 IP 和实时代理 IP 不一致，不要继续登录。")\n                append_status_for_proxy_failure(account, parsed_proxy, "ip_mismatch", note, browser_ip)\n                return False, f"ip_mismatch: {note}"\n'''
    new = '''            if browser_ip != realtime_ip:\n                print("动态轮换代理模式：requests 出口 IP 与浏览器出口 IP 不一致，允许继续。")\n                print(f"requests={realtime_ip}, browser={browser_ip}")\n'''
    text, changed = replace_once(text, old, new, "login_telegram_web.py")

    old_note = '''                note = automation_note or "my.telegram.org API 导出成功"\n'''
    new_note = '''                note = " | ".join([automation_note or "my.telegram.org API 导出成功", f"dynamic_proxy，requests_ip={realtime_ip}，browser_ip={browser_ip}"])\n'''
    if old_note in text and new_note not in text:
        text = text.replace(old_note, new_note, 1)
        changed = True

    old_fail_note = '''                note = automation_note or "my.telegram.org 自动流程未完成或未成功写入 API CSV"\n'''
    new_fail_note = '''                note = " | ".join([automation_note or "my.telegram.org 自动流程未完成或未成功写入 API CSV", f"dynamic_proxy，requests_ip={realtime_ip}，browser_ip={browser_ip}"])\n'''
    if old_fail_note in text and new_fail_note not in text:
        text = text.replace(old_fail_note, new_fail_note, 1)
        changed = True

    old_intro = '''    print("结构说明：批量自动模式；不再手动选择账号，按 account_proxy_map.csv 顺序逐个账号执行；前置登录/API 导出逻辑不变。")\n'''
    new_intro = '''    print("结构说明：动态轮换代理模式；所有账号共用面板保存的一条 raw_proxy，按 account_proxy_map.csv 顺序逐个账号执行。")\n'''
    if old_intro in text and new_intro not in text:
        text = text.replace(old_intro, new_intro, 1)
        changed = True

    if changed:
        write_text(path, text)
        print("已修改 login_telegram_web.py")


def patch_update_telegram_profile() -> None:
    path = SRC_DIR / "update_telegram_profile.py"
    text = read_text(path)

    old = '''    if browser_ip != realtime_ip:\n        return False, browser_ip, f"ip_mismatch: requests={realtime_ip}, browser={browser_ip}"\n'''
    new = '''    if browser_ip != realtime_ip:\n        log("动态轮换代理模式：requests 出口 IP 与浏览器出口 IP 不一致，允许继续。")\n        log(f"requests={realtime_ip}, browser={browser_ip}")\n'''
    text, changed = replace_once(text, old, new, "update_telegram_profile.py")
    if changed:
        write_text(path, text)
        print("已修改 update_telegram_profile.py")


def patch_open_account_browser() -> None:
    path = SRC_DIR / "open_account_browser.py"
    text = read_text(path)

    old = '''        if browser_ip == realtime_ip:\n            status = "ok"\n            note = ""\n            print("状态：通过。浏览器代理配置正确。")\n\n            if account["historical_exit_ip"] != browser_ip:\n                update_account_proxy_map_exit_ip(\n                    phone=account["phone"],\n                    new_exit_ip=browser_ip,\n                )\n\n            print("可以继续用这个窗口做 Telegram Web 登录测试。")\n        else:\n            status = "ip_mismatch"\n            note = f"requests={realtime_ip}, browser={browser_ip}"\n            print("状态：不通过。requests 实时 IP 和浏览器 IP 不一致。")\n            print("不要继续登录 Telegram。")\n'''
    new = '''        status = "ok"\n        note = f"dynamic_proxy，requests={realtime_ip}, browser={browser_ip}"\n        if browser_ip != realtime_ip:\n            print("动态轮换代理模式：requests 出口 IP 与浏览器出口 IP 不一致，允许继续。")\n        print("状态：通过。浏览器代理已生效。")\n\n        if account["historical_exit_ip"] != browser_ip:\n            update_account_proxy_map_exit_ip(\n                phone=account["phone"],\n                new_exit_ip=browser_ip,\n            )\n\n        print("可以继续用这个窗口做 Telegram Web 登录测试。")\n'''
    text, changed = replace_once(text, old, new, "open_account_browser.py")
    if changed:
        write_text(path, text)
        print("已修改 open_account_browser.py")


def delete_dynamic_wrapper_files() -> None:
    for name in (
        "login_telegram_web_dynamic.py",
        "update_telegram_profile_dynamic.py",
        "open_account_browser_dynamic.py",
    ):
        path = SRC_DIR / name
        if path.exists():
            path.unlink()
            print(f"已删除新增包装脚本：{path}")


def main() -> int:
    delete_dynamic_wrapper_files()
    patch_login_telegram_web()
    patch_update_telegram_profile()
    patch_open_account_browser()
    print("动态轮换代理清理和原脚本修补完成。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
