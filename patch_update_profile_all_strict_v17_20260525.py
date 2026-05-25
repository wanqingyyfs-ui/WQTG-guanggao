from __future__ import annotations

import py_compile
import re
import shutil
import time
from pathlib import Path


OVERRIDE_BLOCK = '\n# ===== profile maintenance all strict override v17 begin =====\ndef _v17_sleep(page, ms: int) -> None:\n    try:\n        page.wait_for_timeout(ms)\n    except Exception:\n        time.sleep(ms / 1000)\n\n\ndef _v17_step_delay_ms() -> int:\n    try:\n        return random.randint(3000, 5000)\n    except Exception:\n        return 4000\n\n\ndef _v17_success_status(status: str) -> bool:\n    clean_status = str(status or "").strip().lower()\n    return clean_status in {"success", "already_added"}\n\n\ndef _v17_return_to_initial_telegram_page(page, account: dict[str, str], reason: str) -> None:\n    """\n    每个动作完成后回到 Telegram Web 初始聊天页面，避免下一个动作接不上。\n    """\n    log(f"{reason}：准备返回 Telegram Web 初始页面。")\n\n    for _ in range(2):\n        try:\n            page.keyboard.press("Escape")\n            _v17_sleep(page, 500)\n        except Exception:\n            pass\n\n    try:\n        page.goto(TELEGRAM_WEB_URL, wait_until="commit", timeout=20000)\n    except Exception as exc:\n        log(f"{reason}：返回 Telegram Web 初始页 commit 超时/失败，继续等待页面状态：{exc}")\n\n    _v17_sleep(page, 4000)\n\n    try:\n        if not is_telegram_logged_in_page(page, timeout=2000):\n            log(f"{reason}：返回初始页后未识别为已登录，重新确认登录状态。")\n            ensure_logged_in_without_mytelegram(page, account)\n    except Exception as exc:\n        log(f"{reason}：返回初始页后登录态确认异常，继续后续流程：{exc}")\n\n    _v17_sleep(page, 1000)\n\n\ndef _v17_hard_refresh_for_retry(page, account: dict[str, str], step: str, attempt: int, error_text: str) -> None:\n    """\n    单个动作失败后，硬刷新 Telegram Web，再从当前步骤重新尝试。\n    """\n    log(f"步骤 {step} 第 {attempt} 次失败，准备硬刷新后重试。错误：{error_text}")\n\n    try:\n        dump_debug_html(page, f"profile_all_{step}_attempt_{attempt}_failed")\n    except Exception:\n        pass\n\n    for _ in range(2):\n        try:\n            page.keyboard.press("Escape")\n            _v17_sleep(page, 500)\n        except Exception:\n            pass\n\n    try:\n        page.keyboard.press("Control+F5")\n        log(f"步骤 {step}：已发送 Ctrl+F5。")\n        _v17_sleep(page, 3000)\n    except Exception as exc:\n        log(f"步骤 {step}：Ctrl+F5 失败，继续 reload：{exc}")\n\n    try:\n        page.reload(wait_until="commit", timeout=20000)\n        log(f"步骤 {step}：reload(commit) 已执行。")\n    except Exception as exc:\n        log(f"步骤 {step}：reload(commit) 失败，继续 goto 初始页：{exc}")\n\n    try:\n        page.goto(TELEGRAM_WEB_URL, wait_until="commit", timeout=20000)\n        log(f"步骤 {step}：已重新打开 Telegram Web 初始页。")\n    except Exception as exc:\n        log(f"步骤 {step}：重新打开 Telegram Web 初始页失败，继续等待页面恢复：{exc}")\n\n    _v17_sleep(page, 5000)\n\n    try:\n        if not is_telegram_logged_in_page(page, timeout=2500):\n            log(f"步骤 {step}：硬刷新后未识别为已登录，重新确认登录状态。")\n            ensure_logged_in_without_mytelegram(page, account)\n    except Exception as exc:\n        log(f"步骤 {step}：硬刷新后登录态确认异常：{exc}")\n\n    delay_ms = _v17_step_delay_ms()\n    log(f"步骤 {step}：硬刷新恢复完成，等待 {delay_ms} 毫秒后重试当前步骤。")\n    _v17_sleep(page, delay_ms)\n\n\ndef _v17_execute_step_strict(\n    telegram_page,\n    step: str,\n    config: dict[str, Any],\n    account: dict[str, str],\n    account_index: int,\n    used_photos: set[Path],\n    max_attempts: int,\n) -> str:\n    """\n    严格执行单个步骤：\n    - 调用已经修好的单独按钮逻辑 execute_step；\n    - 失败不跳过；\n    - 硬刷新后重试当前步骤；\n    - 只有 success / already_added 才算完成。\n    """\n    last_error = ""\n\n    for attempt in range(1, max_attempts + 1):\n        try:\n            log(f"开始执行步骤 {step}，尝试 {attempt}/{max_attempts}。")\n            status = execute_step(telegram_page, step, config, account, account_index, used_photos)\n            clean_status = str(status or "").strip()\n            log(f"步骤 {step} 返回状态：{clean_status}")\n\n            if _v17_success_status(clean_status):\n                _v17_return_to_initial_telegram_page(\n                    telegram_page,\n                    account,\n                    reason=f"步骤 {step} 完成",\n                )\n                delay_ms = _v17_step_delay_ms()\n                log(f"步骤 {step} 完成后等待 {delay_ms} 毫秒，再进入下一个动作。")\n                _v17_sleep(telegram_page, delay_ms)\n                return clean_status\n\n            last_error = f"step_status_not_success: {clean_status}"\n            if attempt < max_attempts:\n                _v17_hard_refresh_for_retry(telegram_page, account, step, attempt, last_error)\n                continue\n\n            raise RuntimeError(last_error)\n\n        except Exception as exc:\n            last_error = str(exc)\n            if attempt < max_attempts:\n                _v17_hard_refresh_for_retry(telegram_page, account, step, attempt, last_error)\n                continue\n            break\n\n    raise RuntimeError(f"步骤 {step} 在 {max_attempts} 次尝试后仍未完成：{last_error}")\n\n\ndef process_account(action: str, config: dict[str, Any], account: dict[str, str], account_index: int, total: int, used_photos: set[Path]) -> dict[str, Any]:\n    """\n    v17 覆盖版账号处理逻辑。\n\n    修改全部选项 action=all：\n    - 使用单个按钮已经修好的 execute_step 逻辑；\n    - 账号 A 必须完成所有动作，才允许进入账号 B；\n    - 某一步失败，硬刷新 Telegram Web 后重试当前步骤；\n    - 不跳过失败步骤；\n    - 每个动作之间 3~5 秒延迟；\n    - 每个动作完成后返回 Telegram Web 初始页面。\n    """\n    result_row = safe_status_row(account, action)\n    steps = action_steps(action, config)\n    note_parts: list[str] = []\n\n    log("-" * 80)\n    log(f"资料维护脚本版本：{SCRIPT_VERSION}")\n    log(f"开始处理账号 {account_index}/{total}：{account.get(\'phone\', \'\')}")\n    log(f"Profile：{account.get(\'profile_dir\', \'\')}")\n    log(f"代理：{account.get(\'masked_proxy\', \'\')}")\n    log(f"动作：{action}，步骤：{steps or [\'status\']}")\n    log("-" * 80)\n\n    parsed_proxy = parse_raw_proxy(account["raw_proxy"])\n    result_row["masked_proxy"] = parsed_proxy.masked_raw_proxy\n\n    ok, realtime_ip, error = verify_proxy_before_browser(account, parsed_proxy)\n    if not ok:\n        result_row["final_status"] = "failed"\n        result_row["note"] = error\n        return result_row\n\n    strict_all_mode = action == "all"\n    step_max_attempts = int(config.get("step_max_attempts") or 3)\n    if step_max_attempts < 1:\n        step_max_attempts = 1\n    if step_max_attempts > 5:\n        step_max_attempts = 5\n\n    with sync_playwright() as playwright:\n        context = None\n        try:\n            context, _ = launch_context_for_account(playwright, account)\n            ok, browser_ip, error = verify_browser_proxy(context, account, realtime_ip)\n            if not ok:\n                result_row["final_status"] = "failed"\n                result_row["note"] = error\n                return result_row\n\n            telegram_page = context.new_page()\n            try:\n                logged_in = ensure_logged_in_without_mytelegram(telegram_page, account)\n            except Exception as exc:\n                try:\n                    dump_debug_html(telegram_page, "profile_maintenance_login_failed")\n                except Exception:\n                    pass\n                raise RuntimeError(f"login_failed: {exc}") from exc\n\n            if not logged_in:\n                result_row["final_status"] = "not_logged_in"\n                result_row["note"] = "Telegram Web 未登录，自动登录失败"\n                for step in steps:\n                    result_row[STEP_STATUS_FIELDS[step]] = "not_logged_in"\n                return result_row\n\n            if action == "status":\n                result_row["final_status"] = "success"\n                result_row["note"] = f"logged_in，browser_ip={browser_ip}"\n                return result_row\n\n            if strict_all_mode:\n                log("修改全部选项进入严格模式：必须当前账号全部动作完成后才进入下一个账号。")\n                for step in steps:\n                    field = STEP_STATUS_FIELDS[step]\n                    try:\n                        status = _v17_execute_step_strict(\n                            telegram_page,\n                            step,\n                            config,\n                            account,\n                            account_index,\n                            used_photos,\n                            max_attempts=step_max_attempts,\n                        )\n                        result_row[field] = status\n                        log(f"账号 {account.get(\'phone\', \'\')} 步骤 {step} 完成：{status}")\n                    except Exception as exc:\n                        error_text = str(exc)\n                        result_row[field] = f"failed: {error_text}"\n                        note_parts.append(f"{step}: {error_text}")\n                        try:\n                            dump_debug_html(telegram_page, f"profile_all_{step}_final_failed")\n                        except Exception:\n                            pass\n                        log(f"账号 {account.get(\'phone\', \'\')} 步骤 {step} 最终失败，严格模式停止当前账号后续动作：{error_text}")\n                        result_row["final_status"] = "failed"\n                        result_row["note"] = " | ".join(note_parts)\n                        return result_row\n\n                result_row["final_status"] = "success"\n                result_row["note"] = "修改全部选项全部动作完成"\n                return result_row\n\n            # 单独按钮仍然使用原来的宽松模式：单步失败记录失败，不影响后续账号。\n            for step in steps:\n                field = STEP_STATUS_FIELDS[step]\n                try:\n                    status = execute_step(telegram_page, step, config, account, account_index, used_photos)\n                    result_row[field] = status\n                    log(f"账号 {account.get(\'phone\', \'\')} 步骤 {step} 完成：{status}")\n                except Exception as exc:\n                    error_text = str(exc)\n                    result_row[field] = f"failed: {error_text}"\n                    note_parts.append(f"{step}: {error_text}")\n                    try:\n                        dump_debug_html(telegram_page, f"profile_{step}_failed")\n                    except Exception:\n                        pass\n                    log(f"账号 {account.get(\'phone\', \'\')} 步骤 {step} 失败：{error_text}")\n\n            failed = failed_steps_from_result(result_row)\n            if failed:\n                result_row["final_status"] = "partial_failed" if len(failed) < len(steps) else "failed"\n            else:\n                result_row["final_status"] = "success"\n            result_row["note"] = " | ".join(note_parts) if note_parts else "完成"\n            return result_row\n        finally:\n            if context is not None:\n                try:\n                    context.close()\n                except Exception:\n                    pass\n\n\ndef main() -> int:\n    parser = argparse.ArgumentParser(description="Telegram 账号资料维护")\n    parser.add_argument("--action", choices=sorted(ACTIONS), default="status")\n    args = parser.parse_args()\n\n    action = str(args.action or "status").strip().lower()\n    config = load_config()\n    rows = read_account_proxy_map()\n    total = len(rows)\n    used_photos: set[Path] = set()\n\n    log("=" * 80)\n    log(f"账号资料维护开始：动作={action}，账号数={total}")\n    log(f"配置文件：{CONFIG_FILE}")\n    log(f"结果文件：{RESULTS_FILE}")\n    log(f"失败文件：{FAILED_FILE}")\n    log("=" * 80)\n\n    success_count = 0\n    failed_count = 0\n\n    for index, account in enumerate(rows, start=1):\n        try:\n            telegram_phone, country_code, national_number = split_phone_for_telegram(\n                account.get("phone", ""),\n                account.get("country", ""),\n            )\n            account["telegram_phone"] = telegram_phone\n            account["country_code"] = country_code\n            account["national_number"] = national_number\n\n            result_row = process_account(action, config, account, index, total, used_photos)\n        except Exception as exc:\n            result_row = safe_status_row(account, action)\n            result_row["final_status"] = "failed"\n            result_row["note"] = f"batch_unhandled_error: {exc}"\n            log(f"账号 {account.get(\'phone\', \'\')} 出现未捕获错误：{exc}")\n\n        result_row["updated_at"] = now_text()\n        write_result(result_row)\n\n        steps = action_steps(action, config)\n        failed = failed_steps_from_result(result_row)\n        unfinished = unfinished_steps_from_result(result_row, steps)\n        final_status = str(result_row.get("final_status") or "")\n\n        if final_status == "success":\n            success_count += 1\n            log(f"账号 {account.get(\'phone\', \'\')} 资料维护成功。")\n        else:\n            failed_count += 1\n            write_failed({\n                "phone": result_row.get("phone", ""),\n                "profile_dir": result_row.get("profile_dir", ""),\n                "masked_proxy": result_row.get("masked_proxy", ""),\n                "action": action,\n                "failed_steps": ";".join(failed),\n                "unfinished_steps": ";".join(unfinished),\n                "error_message": result_row.get("note", ""),\n                "updated_at": now_text(),\n            })\n            log(f"账号 {account.get(\'phone\', \'\')} 资料维护未完全成功：{final_status}，{result_row.get(\'note\', \'\')}")\n\n            if action == "all":\n                log("修改全部选项严格模式：当前账号没有全部完成，停止整个批次，不进入下一个账号。")\n                break\n\n            if config.get("stop_on_error"):\n                log("配置为遇到账号错误后停止全部流程，当前流程结束。")\n                break\n\n        if index < total:\n            delay_ms = int(config.get("account_delay_ms") or 3000)\n            log(f"等待 {delay_ms} 毫秒后处理下一个账号。")\n            time.sleep(delay_ms / 1000)\n\n    log("=" * 80)\n    log(f"账号资料维护结束：成功 {success_count} 个，未完全成功 {failed_count} 个，总计 {total} 个。")\n    log("=" * 80)\n    return 0\n# ===== profile maintenance all strict override v17 end =====\n'


def find_repo_root() -> Path:
    start = Path.cwd().resolve()
    for candidate in [start, *start.parents]:
        target = candidate / "app" / "vendor" / "tgapipldc" / "src" / "update_telegram_profile.py"
        if target.exists():
            return candidate
    raise FileNotFoundError(
        "没有找到 app/vendor/tgapipldc/src/update_telegram_profile.py。"
        "请把本补丁文件放到项目根目录 E:\\WQTG-guanggao 后再运行。"
    )


def remove_old_all_override(text: str) -> str:
    return re.sub(
        r"\n?# ===== profile maintenance all strict override v\d+ begin =====[\s\S]*?# ===== profile maintenance all strict override v\d+ end =====\n?",
        "\n",
        text,
        count=1,
    )


def insert_before_main_guard(text: str, block: str) -> str:
    marker = 'if __name__ == "__main__":'
    if marker in text:
        return text.replace(marker, block + "\n\n" + marker, 1)
    return text.rstrip() + "\n\n" + block + "\n"


def main() -> int:
    repo_root = find_repo_root()
    target = repo_root / "app" / "vendor" / "tgapipldc" / "src" / "update_telegram_profile.py"

    original = target.read_text(encoding="utf-8")
    text = remove_old_all_override(original)
    text = insert_before_main_guard(text, OVERRIDE_BLOCK)

    text = re.sub(
        r'SCRIPT_VERSION\s*=\s*"[^"]+"',
        'SCRIPT_VERSION = "profile-maintenance-017-all-strict-retry"',
        text,
        count=1,
    )

    if text == original:
        print("文件没有变化，可能已经修复过。")
        return 0

    backup = target.with_name(f"{target.name}.bak_v17_all_strict_retry_{time.strftime('%Y%m%d_%H%M%S')}")
    shutil.copy2(target, backup)
    target.write_text(text, encoding="utf-8")

    try:
        py_compile.compile(str(target), doraise=True)
    except Exception as e:
        shutil.copy2(backup, target)
        print("修复后语法检查失败，已自动恢复备份。")
        print(f"错误：{e}")
        return 1

    print(f"已修复：{target}")
    print(f"已备份旧文件：{backup}")
    print("语法检查：通过")
    print("修复内容：")
    print("1. 修改全部选项 action=all 改为严格模式。")
    print("2. 每个账号必须完成所有动作后才进入下一个账号。")
    print("3. 单步失败后硬刷新 Telegram Web，并从当前步骤重试。")
    print("4. 每个动作之间保留 3~5 秒延迟。")
    print("5. 每个动作完成后返回 Telegram Web 初始页面。")
    print("6. 单独按钮 photo/name/username/bio/folder 保持原执行方式。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
