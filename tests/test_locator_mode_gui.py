from __future__ import annotations

import json, os, sys, unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication
from app.gui.pages.tgapipldc_locator_page import MODE_ABSOLUTE, MODE_STRATEGIES, TgapipldcLocatorPage


class LocatorModeGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.page = TgapipldcLocatorPage()
        self.page.set_targets({"telegram.profile.edit": {"category": "账号资料", "description": "右上角编辑资料按钮", "timeout_ms": 10000, "locator_mode": MODE_STRATEGIES, "strategies": [{"type": "css", "value": "button.edit", "enabled": True}], "absolute_position": {"x": 1142, "y": 54, "viewport_width": 1200, "viewport_height": 900, "captured": True}}})
        self.page.set_profiles([{"profile_dir": "profiles/a", "display_name": "A"}])

    def tearDown(self): self.page.close()

    def test_mode_combo_preserves_both_data_sets(self):
        self.page.locator_mode_combo.setCurrentIndex(self.page.locator_mode_combo.findData(MODE_ABSOLUTE))
        target = json.loads(self.page.current_target_json())
        self.assertEqual(target["locator_mode"], MODE_ABSOLUTE)
        self.assertEqual(target["strategies"][0]["value"], "button.edit")
        self.assertEqual(target["absolute_position"]["x"], 1142.0)

    def test_manual_absolute_fields_mark_captured(self):
        self.page.absolute_x_spinbox.setValue(1110); self.page.absolute_y_spinbox.setValue(60)
        target = json.loads(self.page.current_target_json())
        self.assertTrue(target["absolute_position"]["captured"])
        self.assertEqual(target["absolute_position"]["x"], 1110.0)

    def test_calibrate_saves_selected_mode_before_opening(self):
        saved, calibrated = [], []
        self.page.save_target_requested.connect(lambda target_id, raw: saved.append((target_id, raw)))
        self.page.calibrate_requested.connect(lambda target_id, profile, url: calibrated.append((target_id, profile, url)))
        self.page.locator_mode_combo.setCurrentIndex(self.page.locator_mode_combo.findData(MODE_ABSOLUTE))
        self.page._emit_calibrate()
        self.assertEqual(json.loads(saved[0][1])["locator_mode"], MODE_ABSOLUTE)
        self.assertEqual(calibrated[0][0], "telegram.profile.edit")
        self.assertEqual(calibrated[0][1], "profiles/a")


if __name__ == "__main__": unittest.main()
