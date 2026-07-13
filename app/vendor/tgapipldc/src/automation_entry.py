from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from automation_adapter import install_login_adapter, install_profile_adapter
from automation_locator_engine import LocatorConfigStore, build_selector_for_element, calibration_init_script
from profile_lock import ProfileLock
from proxy_utils import parse_raw_proxy


BASE_DIR = Path(__file__).resolve().parent.parent
LOG_DIR = BASE_DIR / "logs"
DATA_DIR = BASE_DIR / "data"


def _result_path() -> Path:
    raw = os.environ.get("WQTG_JOB_RESULT", "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    job_id = os.environ.get("WQTG_JOB_ID", "manual")
    return (LOG_DIR / "job_results" / f"{job_id}.json").resolve()


def _write_summary(payload: dict[str, Any]) -> None:
    path = _result_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)
    print(f"结构化运行结果：{path}", flush=True)


def run_login() -> int:
    import login_telegram_web as module

    state = install_login_adapter(module)
    error = ""
    try:
        module.main()
    except BaseException as exc:
        error = str(exc)
        raise
    finally:
        results = [bool(item) for item in state.get("results", [])]
        total = len(results)
        success_count = sum(results)
        status = "success" if total > 0 and success_count == total else "failed"
        _write_summary({
            "job_id": os.environ.get("WQTG_JOB_ID", ""),
            "job_type": "api-export",
            "status": status,
            "success_count": success_count,
            "failed_count": max(0, total - success_count),
            "total": total,
            "error": error,
            "finished_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        })
    return 0 if state.get("results") and all(state["results"]) else 2


def run_profile(action: str) -> int:
    import update_telegram_profile as module

    state = install_profile_adapter(module)
    error = ""
    try:
        config = module.load_config()
        accounts = module.read_account_proxy_map()
        total = len(accounts)
        used_photos: set[Path] = set()
        module.log("=" * 80)
        module.log(f"账号资料维护开始：动作={action}，账号数={total}")
        module.log("修改全部选项的批次行为由 stop_on_error 统一控制；不再无条件中断后续账号。")
        module.log("=" * 80)
        for index, account in enumerate(accounts, start=1):
            try:
                telegram_phone, country_code, national_number = module.split_phone_for_telegram(
                    account.get("phone", ""), account.get("country", "")
                )
                account["telegram_phone"] = telegram_phone
                account["country_code"] = country_code
                account["national_number"] = national_number
                result_row = module.process_account(action, config, account, index, total, used_photos)
            except Exception as exc:
                result_row = module.safe_status_row(account, action)
                result_row["final_status"] = "failed"
                result_row["note"] = f"batch_unhandled_error: {exc}"
                module.log(f"账号 {account.get('phone', '')} 出现未捕获错误：{exc}")

            result_row["updated_at"] = module.now_text()
            module.write_result(result_row)
            steps = module.action_steps(action, config)
            failed = module.failed_steps_from_result(result_row)
            unfinished = module.unfinished_steps_from_result(result_row, steps)
            final_status = str(result_row.get("final_status") or "")
            if final_status != "success":
                module.write_failed({
                    "phone": result_row.get("phone", ""),
                    "profile_dir": result_row.get("profile_dir", ""),
                    "masked_proxy": result_row.get("masked_proxy", ""),
                    "action": action,
                    "failed_steps": ";".join(failed),
                    "unfinished_steps": ";".join(unfinished),
                    "error_message": result_row.get("note", ""),
                    "updated_at": module.now_text(),
                })
                module.log(f"账号 {account.get('phone', '')} 资料维护未完全成功：{final_status}")
                if bool(config.get("stop_on_error")):
                    module.log("已启用遇错停止，结束后续账号。")
                    break
            else:
                module.log(f"账号 {account.get('phone', '')} 资料维护成功。")

            if index < total:
                delay_ms = max(0, int(config.get("account_delay_ms") or 3000))
                time.sleep(delay_ms / 1000)
    except BaseException as exc:
        error = str(exc)
        raise
    finally:
        rows = [dict(row) for row in state.get("rows", [])]
        success_count = sum(1 for row in rows if str(row.get("final_status") or "") == "success")
        failed_count = len(rows) - success_count
        status = "success" if rows and failed_count == 0 else ("partial_success" if success_count else "failed")
        _write_summary({
            "job_id": os.environ.get("WQTG_JOB_ID", ""),
            "job_type": "profile-maintenance",
            "action": action,
            "status": status,
            "success_count": success_count,
            "failed_count": failed_count,
            "total": len(rows),
            "rows": rows,
            "error": error,
            "finished_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        })
    return 0 if state.get("rows") and all(str(row.get("final_status") or "") == "success" for row in state["rows"]) else 2


def _is_proxy_auth_error(exc: BaseException | str) -> bool:
    text = str(exc or "").lower()
    return any(marker in text for marker in (
        "err_invalid_auth_credentials",
        "proxy authentication required",
        "proxy authentication failed",
        "407 proxy authentication",
    ))


def _configure_calibration_context(context, target_id: str, save_locator) -> None:
    context.expose_function("wqtgSaveLocator", save_locator)
    context.add_init_script(calibration_init_script(target_id))


def _open_calibration_browser(
    playwright,
    *,
    profile_path: Path,
    viewport: dict[str, Any],
    target_id: str,
    url: str,
    raw_proxy: str,
    save_locator,
):
    """Open calibration browser and retry direct only for proxy-auth failures.

    API export and profile maintenance remain proxy-strict. The direct retry is
    intentionally limited to the visual locator calibration tool.
    """
    target_url = url or "https://web.telegram.org/k/"
    base_kwargs: dict[str, Any] = {
        "user_data_dir": str(profile_path),
        "headless": False,
        "viewport": viewport,
    }
    parsed_proxy = None
    proxy_problem = ""
    if str(raw_proxy or "").strip():
        try:
            parsed_proxy = parse_raw_proxy(raw_proxy)
        except ValueError as exc:
            proxy_problem = str(exc)
            print(
                f"校准代理配置不可用：{proxy_problem}。"
                "将仅为定位校准改用直连；API 批量和资料维护仍会要求有效代理。",
                flush=True,
            )

    attempts = []
    if parsed_proxy:
        attempts.append(("proxy", parsed_proxy.playwright_proxy))
    attempts.append(("direct", None))

    first_auth_error = proxy_problem
    for mode, proxy_settings in attempts:
        launch_kwargs = dict(base_kwargs)
        if proxy_settings:
            launch_kwargs["proxy"] = proxy_settings
        context = playwright.chromium.launch_persistent_context(**launch_kwargs)
        attempt_succeeded = False
        try:
            _configure_calibration_context(context, target_id, save_locator)
            page = context.pages[0] if context.pages else context.new_page()
            try:
                page.goto(target_url, wait_until="commit", timeout=20000)
            except BaseException as exc:
                if mode == "proxy" and parsed_proxy and _is_proxy_auth_error(exc):
                    first_auth_error = str(exc)
                    print(
                        "校准代理认证失败（ERR_INVALID_AUTH_CREDENTIALS）。"
                        "将仅为定位校准自动改用直连重试一次；API 批量和资料维护仍严格使用代理。",
                        flush=True,
                    )
                    continue
                if mode == "direct" and first_auth_error:
                    raise RuntimeError(
                        "代理账号或密码无效，且校准浏览器直连重试也失败。"
                        "请在 API 批量工作台重新保存完整动态代理并生成运行表。"
                        f"代理错误：{first_auth_error}；直连错误：{exc}"
                    ) from exc
                raise
            attempt_succeeded = True
            return context, page, mode == "direct" and bool(str(raw_proxy or "").strip())
        finally:
            if not attempt_succeeded:
                try:
                    context.close()
                except Exception:
                    pass

    raise RuntimeError("校准浏览器启动失败")


def run_calibrate(target_id: str, profile_dir: str, url: str, proxy: str) -> int:
    from playwright.sync_api import sync_playwright

    config_path = Path(os.environ.get("WQTG_LOCATOR_CONFIG") or DATA_DIR / "automation_locators.json")
    store = LocatorConfigStore(config_path)
    config = store.load()
    if target_id not in config["targets"]:
        raise KeyError(f"未知定位目标：{target_id}")

    profile_path = (BASE_DIR / profile_dir).resolve() if not Path(profile_dir).is_absolute() else Path(profile_dir).resolve()
    lock_root = DATA_DIR / "profile_locks"
    captured: list[dict[str, Any]] = []
    used_direct_fallback = False
    error = ""

    def save_locator(payload: dict[str, Any]) -> None:
        selector = build_selector_for_element(payload)
        target = store.load()["targets"][target_id]
        strategies = [{"type": "css", "value": selector, "enabled": True}]
        text = str(payload.get("text") or "").strip()
        if text:
            strategies.append({"type": "text", "value_regex": re_escape(text[:100]), "enabled": True})
        strategies.append({
            "type": "relative_coordinate",
            "x_ratio": round(float(payload.get("xRatio") or 0.0), 6),
            "y_ratio": round(float(payload.get("yRatio") or 0.0), 6),
            "enabled": True,
        })
        target["strategies"] = strategies
        store.save_target(target_id, target)
        captured.append(payload)
        print(f"已保存定位目标 {target_id}：{selector}", flush=True)

    try:
        with ProfileLock(profile_path, lock_root, job_id=os.environ.get("WQTG_JOB_ID", "calibrate")):
            with sync_playwright() as playwright:
                context = None
                try:
                    context, _page, used_direct_fallback = _open_calibration_browser(
                        playwright,
                        profile_path=profile_path,
                        viewport=config.get("viewport") or {"width": 1200, "height": 900},
                        target_id=target_id,
                        url=url,
                        raw_proxy=proxy,
                        save_locator=save_locator,
                    )
                    print("校准浏览器已打开。按住 Ctrl + Shift 点击目标元素；保存后关闭浏览器。", flush=True)
                    if used_direct_fallback:
                        print("当前校准浏览器使用直连；这不会修改账号运行表中的代理。", flush=True)
                    try:
                        while context.pages:
                            time.sleep(0.5)
                    except KeyboardInterrupt:
                        pass
                finally:
                    if context is not None:
                        try:
                            context.close()
                        except Exception:
                            pass
    except BaseException as exc:
        error = str(exc)
        _write_summary({
            "job_id": os.environ.get("WQTG_JOB_ID", ""),
            "job_type": "locator-calibration",
            "status": "failed",
            "target_id": target_id,
            "captured": captured,
            "used_direct_fallback": used_direct_fallback,
            "error": error,
            "finished_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        })
        raise

    status = "success" if captured else "cancelled"
    _write_summary({
        "job_id": os.environ.get("WQTG_JOB_ID", ""),
        "job_type": "locator-calibration",
        "status": status,
        "target_id": target_id,
        "captured": captured,
        "used_direct_fallback": used_direct_fallback,
        "error": error,
        "finished_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    })
    return 0 if captured else 3


def re_escape(text: str) -> str:
    import re
    return re.escape(text)


def main() -> int:
    parser = argparse.ArgumentParser(description="WQTG Telegram automation entry")
    parser.add_argument("--mode", choices=("login", "profile", "calibrate"), required=True)
    parser.add_argument("--action", default="status")
    parser.add_argument("--target", default="")
    parser.add_argument("--profile-dir", default="")
    parser.add_argument("--url", default="https://web.telegram.org/k/")
    parser.add_argument("--proxy", default="")
    args = parser.parse_args()
    if args.mode == "login":
        return run_login()
    if args.mode == "profile":
        return run_profile(args.action)
    return run_calibrate(args.target, args.profile_dir, args.url, args.proxy)


if __name__ == "__main__":
    raise SystemExit(main())
