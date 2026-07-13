from __future__ import annotations

import sys
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "app" / "vendor" / "tgapipldc" / "src"
sys.path.insert(0, str(SRC))

from automation_calibration_picker import CalibrationPickerInstaller, calibration_picker_script
import automation_entry


class FakePage:
    def __init__(self) -> None:
        self.events: list[str] = []
        self.evaluated: list[str] = []
        self.closed = False
        self.url = "https://web.telegram.org/k/"

    def on(self, name, _callback) -> None:
        self.events.append(name)

    def evaluate(self, script):
        self.evaluated.append(script)
        if str(script).startswith("Boolean("):
            return True
        return {"installed": True}

    def wait_for_timeout(self, _milliseconds: int) -> None:
        return None

    def is_closed(self) -> bool:
        return self.closed


class FakeContext:
    def __init__(self, page: FakePage) -> None:
        self.pages = [page]
        self.exposed: list[str] = []
        self.init_scripts: list[str] = []
        self.events: list[str] = []

    def expose_function(self, name, _callback) -> None:
        self.exposed.append(name)

    def add_init_script(self, script) -> None:
        self.init_scripts.append(script)

    def on(self, name, _callback) -> None:
        self.events.append(name)


class CalibrationPickerInjectionTests(unittest.TestCase):
    def test_script_has_visible_button_and_keyboard_fallbacks(self) -> None:
        script = calibration_picker_script("telegram.profile.edit")
        self.assertIn("开始拾取", script)
        self.assertIn("event.key === 'F8'", script)
        self.assertIn("'pointerdown'", script)
        self.assertIn("wqtgLocatorReady", script)
        self.assertNotIn("panel.addEventListener('click', stopEvent", script)
        self.assertNotIn("previous.version === VERSION", script)

    def test_restored_current_page_is_explicitly_injected(self) -> None:
        page = FakePage()
        context = FakeContext(page)
        logs: list[str] = []
        installer = CalibrationPickerInstaller(
            "telegram.profile.edit",
            lambda _payload: None,
            logs.append,
        )

        installer.configure_context(context)
        self.assertIn("wqtgSaveLocator", context.exposed)
        self.assertIn("wqtgLocatorReady", context.exposed)
        self.assertTrue(hasattr(installer._ready_bridge, "__dict__"))
        self.assertTrue(hasattr(installer._save_bridge, "__dict__"))
        self.assertEqual(len(context.init_scripts), 1)
        self.assertTrue(installer.ensure_page(page))
        self.assertGreaterEqual(len(page.evaluated), 2)
        self.assertTrue(any("已注入当前页面" in message for message in logs))

    def test_tunnel_error_is_proxy_navigation_error(self) -> None:
        self.assertTrue(
            automation_entry._is_proxy_navigation_error(
                "net::ERR_TUNNEL_CONNECTION_FAILED"
            )
        )
        self.assertTrue(
            automation_entry._is_proxy_navigation_error(
                "net::ERR_INVALID_AUTH_CREDENTIALS"
            )
        )
        self.assertFalse(
            automation_entry._is_proxy_navigation_error("net::ERR_TIMED_OUT")
        )


if __name__ == "__main__":
    unittest.main()
