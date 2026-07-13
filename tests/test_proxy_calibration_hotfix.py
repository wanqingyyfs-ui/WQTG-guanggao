from __future__ import annotations

import sys
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "app" / "vendor" / "tgapipldc" / "src"
if not SRC.exists():
    SRC = Path(__file__).resolve().parent
sys.path.insert(0, str(SRC))

import automation_entry
from proxy_utils import parse_raw_proxy


class FakePage:
    def __init__(self, error: str = "") -> None:
        self.error = error
        self.url = ""

    def goto(self, url: str, wait_until: str = "commit", timeout: int = 20000) -> None:
        if self.error:
            raise RuntimeError(self.error)
        self.url = url


class FakeContext:
    def __init__(self, page: FakePage) -> None:
        self.pages = [page]
        self.closed = False

    def new_page(self) -> FakePage:
        page = FakePage()
        self.pages.append(page)
        return page

    def expose_function(self, _name, _callback) -> None:
        return None

    def add_init_script(self, _script) -> None:
        return None

    def close(self) -> None:
        self.closed = True
        self.pages = []


class AuthFailureThenDirectChromium:
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.contexts: list[FakeContext] = []

    def launch_persistent_context(self, **kwargs) -> FakeContext:
        self.calls.append(kwargs)
        error = "Page.goto: net::ERR_INVALID_AUTH_CREDENTIALS" if len(self.calls) == 1 else ""
        context = FakeContext(FakePage(error))
        self.contexts.append(context)
        return context


class DirectChromium:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def launch_persistent_context(self, **kwargs) -> FakeContext:
        self.calls.append(kwargs)
        return FakeContext(FakePage())


class FakePlaywright:
    def __init__(self, chromium) -> None:
        self.chromium = chromium


class ProxyCalibrationHotfixTests(unittest.TestCase):
    def test_percent_encoded_credentials_are_decoded(self) -> None:
        parsed = parse_raw_proxy("http://user:p%40ss%3Aword@proxy.example:8080")
        self.assertEqual(parsed.password, "p@ss:word")
        self.assertEqual(
            parsed.playwright_proxy,
            {
                "server": "http://proxy.example:8080",
                "username": "user",
                "password": "p@ss:word",
            },
        )

    def test_raw_special_characters_in_password_are_preserved(self) -> None:
        parsed = parse_raw_proxy("user:p@ss:word#x?y@proxy.example:8080")
        self.assertEqual(parsed.password, "p@ss:word#x?y")
        self.assertEqual(parsed.host, "proxy.example")

    def test_masked_password_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "脱敏值"):
            parse_raw_proxy("user:******@proxy.example:8080")

    def test_proxy_auth_error_is_recognized(self) -> None:
        self.assertTrue(automation_entry._is_proxy_auth_error("net::ERR_INVALID_AUTH_CREDENTIALS"))
        self.assertTrue(automation_entry._is_proxy_auth_error("407 Proxy Authentication Required"))
        self.assertFalse(automation_entry._is_proxy_auth_error("ERR_TIMED_OUT"))

    def test_calibration_retries_direct_after_proxy_auth_failure(self) -> None:
        chromium = AuthFailureThenDirectChromium()
        context, page, used_direct = automation_entry._open_calibration_browser(
            FakePlaywright(chromium),
            profile_path=Path("profile"),
            viewport={"width": 1200, "height": 900},
            target_id="telegram.main.menu",
            url="https://web.telegram.org/k/",
            raw_proxy="user:password@proxy.example:8080",
            save_locator=lambda _payload: None,
        )
        self.assertTrue(used_direct)
        self.assertEqual(len(chromium.calls), 2)
        self.assertIn("proxy", chromium.calls[0])
        self.assertNotIn("proxy", chromium.calls[1])
        self.assertTrue(chromium.contexts[0].closed)
        self.assertFalse(context.closed)
        self.assertEqual(page.url, "https://web.telegram.org/k/")

    def test_calibration_uses_direct_for_masked_proxy_config(self) -> None:
        chromium = DirectChromium()
        _context, page, used_direct = automation_entry._open_calibration_browser(
            FakePlaywright(chromium),
            profile_path=Path("profile"),
            viewport={"width": 1200, "height": 900},
            target_id="telegram.main.menu",
            url="https://web.telegram.org/k/",
            raw_proxy="user:******@proxy.example:8080",
            save_locator=lambda _payload: None,
        )
        self.assertTrue(used_direct)
        self.assertEqual(len(chromium.calls), 1)
        self.assertNotIn("proxy", chromium.calls[0])
        self.assertEqual(page.url, "https://web.telegram.org/k/")


if __name__ == "__main__":
    unittest.main()
