from __future__ import annotations

import base64
import os
import time
import traceback
from multiprocessing.connection import Connection
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright

from app.browser_runtime.fingerprint import _extract_ip, _runtime_snapshot, _webrtc_safe
from app.browser_runtime.workflow import _execute_workflow, _pick_element
from app.telegram.web_actions import (
    TELEGRAM_WEB_URL,
    forward_message,
    is_logged_in,
    login_start,
    read_verification,
    resolve_group,
    send_message,
    submit_2fa,
    submit_code,
)

def _emit(connection: Connection, account_id: int, name: str, **payload: Any) -> None:
    try:
        connection.send({"account_id": account_id, "name": name, "payload": payload})
    except (BrokenPipeError, EOFError, OSError):
        pass

def browser_worker_main(connection: Connection, config: dict[str, Any]) -> None:
    account_id = int(config["account_id"])
    context = None
    playwright = None
    visible = False
    last_frame = 0.0
    last_heartbeat = 0.0
    try:
        proxy = config.get("proxy")
        if not proxy or not proxy.get("server"):
            raise RuntimeError("Static proxy is required; direct network fallback is forbidden")
        profile_dir = Path(config["profile_dir"])
        chromium_dir = profile_dir / "chromium-data"
        chromium_dir.mkdir(parents=True, exist_ok=True)
        env = config["environment"]
        args = [
            "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
            "--webrtc-ip-handling-policy=disable_non_proxied_udp",
            f"--window-size={env['screen_width']},{env['screen_height']}",
            "--no-default-browser-check",
        ]
        playwright = sync_playwright().start()
        launch_options: dict[str, Any] = {
            "user_data_dir": str(chromium_dir),
            "headless": True,
            "proxy": proxy,
            "locale": env["locale"],
            "timezone_id": env["timezone"],
            "viewport": {"width": env["viewport_width"], "height": env["viewport_height"]},
            "device_scale_factor": env["device_scale_factor"],
            "args": args,
            "accept_downloads": False,
        }
        context = playwright.chromium.launch_persistent_context(**launch_options)
        page = context.pages[0] if context.pages else context.new_page()
        dns_request_safe = False
        page.goto(config["dns_check_url"], wait_until="domcontentloaded", timeout=45000)
        dns_body = page.locator("body").inner_text(timeout=10000)
        dns_request_safe = bool(dns_body.strip())
        if not dns_request_safe:
            raise RuntimeError("Browser DNS-over-HTTPS validation request failed through the proxy")
        page.goto(config["proxy_check_url"], wait_until="domcontentloaded", timeout=45000)
        exit_ip = _extract_ip(page.locator("body").inner_text(timeout=10000))
        expected_ip = config.get("expected_ip")
        if not exit_ip:
            raise RuntimeError("Browser proxy check did not return an exit IP")
        if expected_ip and exit_ip != expected_ip:
            raise RuntimeError(f"Browser exit IP mismatch: expected {expected_ip}, got {exit_ip}")
        webrtc_safe = _webrtc_safe(page, expected_ip)
        if not webrtc_safe:
            raise RuntimeError("WebRTC candidate exposed an address outside the configured proxy")
        snapshot = _runtime_snapshot(page)
        browser_version = context.browser.version if context.browser else "unknown"
        user_agent = str(snapshot["navigator"]["userAgent"])
        _emit(
            connection,
            account_id,
            "runtime_ready",
            pid=os.getpid(),
            exit_ip=exit_ip,
            browser_version=browser_version,
            user_agent=user_agent,
            snapshot=snapshot,
            webrtc_safe=True,
            dns_request_safe=dns_request_safe,
        )
        page.goto(TELEGRAM_WEB_URL, wait_until="domcontentloaded", timeout=60000)
        _emit(
            connection,
            account_id,
            "page_state",
            url=page.url,
            title=page.title(),
            logged_in=is_logged_in(page),
        )
        while True:
            now = time.monotonic()
            if visible and now - last_frame >= 0.65:
                try:
                    png = page.screenshot(type="png")
                    _emit(
                        connection,
                        account_id,
                        "frame",
                        image_base64=base64.b64encode(png).decode("ascii"),
                        width=env["viewport_width"],
                        height=env["viewport_height"],
                    )
                except Exception:
                    pass
                last_frame = now
            if connection.poll(0.1):
                command = connection.recv()
                name = command.get("name")
                payload = command.get("payload") or {}
                if name == "stop":
                    break
                if name == "set_visible":
                    visible = bool(payload.get("visible"))
                elif name == "navigate":
                    page.goto(str(payload["url"]), wait_until="domcontentloaded", timeout=60000)
                elif name == "click":
                    page.mouse.click(float(payload["x"]), float(payload["y"]))
                elif name == "type":
                    page.keyboard.type(str(payload.get("text", "")))
                elif name == "press":
                    page.keyboard.press(str(payload["key"]))
                elif name == "reload":
                    page.reload(wait_until="domcontentloaded", timeout=60000)
                elif name == "login_start":
                    result = login_start(page, str(payload["phone"]))
                    _emit(connection, account_id, "command_result", command=name, result=result, request_id=payload.get("request_id"))
                elif name == "read_verification":
                    result = read_verification(context, str(payload["url"]))
                    _emit(connection, account_id, "command_result", command=name, result=result, request_id=payload.get("request_id"))
                elif name == "submit_code":
                    result = submit_code(page, str(payload["code"]))
                    _emit(connection, account_id, "command_result", command=name, result=result, request_id=payload.get("request_id"))
                elif name == "submit_2fa":
                    result = submit_2fa(page, str(payload["password"]))
                    _emit(connection, account_id, "command_result", command=name, result=result, request_id=payload.get("request_id"))
                elif name == "resolve_group":
                    result = resolve_group(page, str(payload["link"]))
                    _emit(connection, account_id, "command_result", command=name, result=result, request_id=payload.get("request_id"))
                elif name == "send_message":
                    result = send_message(
                        page,
                        link=str(payload["link"]),
                        text=str(payload.get("text", "")),
                        asset_paths=list(payload.get("asset_paths") or []),
                    )
                    _emit(connection, account_id, "command_result", command=name, result=result, request_id=payload.get("request_id"))
                elif name == "forward_message":
                    result = forward_message(
                        page,
                        source_link=str(payload["source_link"]),
                        target_link=str(payload["target_link"]),
                    )
                    _emit(connection, account_id, "command_result", command=name, result=result, request_id=payload.get("request_id"))
                elif name == "pick_element":
                    result = _pick_element(page, float(payload["x"]), float(payload["y"]))
                    _emit(connection, account_id, "command_result", command=name, result=result, request_id=payload.get("request_id"))
                elif name == "execute_workflow":
                    result = _execute_workflow(page, list(payload.get("steps") or []), profile_dir)
                    _emit(connection, account_id, "command_result", command=name, result=result, request_id=payload.get("request_id"))
                _emit(
                    connection,
                    account_id,
                    "page_state",
                    url=page.url,
                    title=page.title(),
                    logged_in=is_logged_in(page),
                )
            if now - last_heartbeat >= 5.0:
                _emit(connection, account_id, "heartbeat", monotonic=now)
                last_heartbeat = now
    except EOFError:
        pass
    except Exception as exc:
        _emit(
            connection,
            account_id,
            "fatal_error",
            error=str(exc),
            traceback=traceback.format_exc(limit=8),
        )
    finally:
        try:
            if context is not None:
                context.close()
        except Exception:
            pass
        try:
            if playwright is not None:
                playwright.stop()
        except Exception:
            pass
        _emit(connection, account_id, "stopped")
        try:
            connection.close()
        except Exception:
            pass
