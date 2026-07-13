from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "app" / "vendor" / "tgapipldc" / "src"
sys.path.insert(0, str(SRC))

from automation_calibration_picker import calibration_picker_script
from automation_locator_engine import (
    LOCATOR_MODE_ABSOLUTE,
    LOCATOR_MODE_STRATEGIES,
    LocatorConfigStore,
    LocatorEngine,
    apply_calibration_payload,
    build_selector_for_element,
)


class FakeMouse:
    def __init__(self): self.clicks = []
    def click(self, x, y): self.clicks.append((x, y))


class FakeItem:
    def __init__(self): self.clicks = 0
    def is_visible(self, timeout=0): return True
    def scroll_into_view_if_needed(self, timeout=0): return None
    def click(self, timeout=0): self.clicks += 1


class FakeLocator:
    def __init__(self, item): self.item = item
    def count(self): return 1
    def nth(self, _index): return self.item
    def is_visible(self, timeout=0): return self.item.is_visible(timeout)
    def scroll_into_view_if_needed(self, timeout=0): self.item.scroll_into_view_if_needed(timeout)
    def click(self, timeout=0): self.item.click(timeout)


class FakePage:
    def __init__(self, forbid_selectors=False):
        self.viewport_size = {"width": 1200, "height": 900}
        self.mouse = FakeMouse(); self.forbid_selectors = forbid_selectors
        self.selector_calls = 0; self.item = FakeItem(); self.url = "https://web.telegram.org/k/"
    def wait_for_timeout(self, _delay): return None
    def _locator(self):
        if self.forbid_selectors: raise AssertionError("absolute mode must not query selectors")
        self.selector_calls += 1; return FakeLocator(self.item)
    def locator(self, _value): return self._locator()
    def get_by_role(self, *_args, **_kwargs): return self._locator()
    def get_by_text(self, *_args, **_kwargs): return self._locator()


class LocatorExplicitModeTests(unittest.TestCase):
    def _engine(self, override):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        path = Path(temp.name) / "locators.json"
        path.write_text(json.dumps({"targets": {"telegram.profile.edit": override}}), encoding="utf-8")
        return LocatorEngine(path, Path(temp.name) / "diagnostics")

    def test_absolute_mode_clicks_exact_pixel_without_selector_lookup(self):
        engine = self._engine({"locator_mode": LOCATOR_MODE_ABSOLUTE, "absolute_position": {"x": 1142, "y": 54, "viewport_width": 1200, "viewport_height": 900, "captured": True}})
        page = FakePage(forbid_selectors=True)
        self.assertTrue(engine.click(page, "telegram.profile.edit"))
        self.assertEqual(page.mouse.clicks, [(1142.0, 54.0)])
        self.assertEqual(page.selector_calls, 0)

    def test_strategies_mode_ignores_legacy_coordinate(self):
        engine = self._engine({"locator_mode": LOCATOR_MODE_STRATEGIES, "strategies": [{"type": "relative_coordinate", "x_ratio": .9, "y_ratio": .1, "enabled": True}, {"type": "css", "value": "button.edit", "enabled": True}]})
        page = FakePage()
        self.assertTrue(engine.click(page, "telegram.profile.edit"))
        self.assertEqual(page.mouse.clicks, [])
        self.assertEqual(page.item.clicks, 1)

    def test_legacy_relative_coordinate_migrates_to_absolute_pixels(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "locators.json"
            path.write_text(json.dumps({"viewport": {"width": 1200, "height": 900}, "targets": {"telegram.profile.edit": {"strategies": [{"type": "css", "value": "button.edit", "enabled": True}, {"type": "relative_coordinate", "x_ratio": .95, "y_ratio": .06, "enabled": True}]}}}), encoding="utf-8")
            target = LocatorConfigStore(path).load()["targets"]["telegram.profile.edit"]
        self.assertTrue(target["absolute_position"]["captured"])
        self.assertEqual(target["absolute_position"]["x"], 1140.0)
        self.assertEqual(target["absolute_position"]["y"], 54.0)

    def test_calibration_preserves_inactive_mode_data(self):
        original = {"locator_mode": LOCATOR_MODE_STRATEGIES, "strategies": [{"type": "css", "value": "button.old", "enabled": True}], "absolute_position": {"x": 10, "y": 20, "viewport_width": 1200, "viewport_height": 900, "captured": True}}
        absolute, _ = apply_calibration_payload(original, {"locatorMode": LOCATOR_MODE_ABSOLUTE, "x": 1111, "y": 55, "viewportWidth": 1200, "viewportHeight": 900})
        self.assertEqual(absolute["strategies"], original["strategies"])
        strategies, _ = apply_calibration_payload(absolute, {"locatorMode": LOCATOR_MODE_STRATEGIES, "tag": "button", "id": "edit-profile", "className": "btn", "text": "Edit", "attrs": {}})
        self.assertEqual(strategies["absolute_position"], absolute["absolute_position"])
        self.assertEqual(strategies["strategies"][0]["value"], "#edit-profile")

    def test_unchanged_entry_save_path_honors_absolute_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "locators.json"; store = LocatorConfigStore(path); store.save(store.load())
            old_strategies = list(store.load()["targets"]["telegram.profile.edit"]["strategies"])
            payload = {"targetId": "telegram.profile.edit", "locatorMode": LOCATOR_MODE_ABSOLUTE, "tag": "button", "className": "same", "text": "Edit", "attrs": {}, "x": 1100, "y": 60, "viewportWidth": 1200, "viewportHeight": 900, "xRatio": .9, "yRatio": .06}
            selector = build_selector_for_element(payload)
            target = store.load()["targets"]["telegram.profile.edit"]
            target["strategies"] = [{"type": "css", "value": selector, "enabled": True}, {"type": "relative_coordinate", "x_ratio": payload["xRatio"], "y_ratio": payload["yRatio"], "enabled": True}]
            store.save_target("telegram.profile.edit", target)
            saved = store.load()["targets"]["telegram.profile.edit"]
        self.assertEqual(saved["locator_mode"], LOCATOR_MODE_ABSOLUTE)
        self.assertEqual(saved["absolute_position"]["x"], 1100.0)
        self.assertEqual(saved["strategies"], old_strategies)

    def test_picker_has_both_modes_and_exact_click_coordinates(self):
        script = calibration_picker_script("telegram.profile.edit", LOCATOR_MODE_ABSOLUTE)
        self.assertIn("Strategies（元素特征）", script)
        self.assertIn("绝对位置（像素坐标）", script)
        self.assertIn("locatorMode", script)
        self.assertIn("e.clientX", script)
        self.assertIn("e.clientY", script)


if __name__ == "__main__": unittest.main()
