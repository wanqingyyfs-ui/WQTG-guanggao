from __future__ import annotations

import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "app" / "vendor" / "tgapipldc" / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from automation_locator_engine import calibration_init_script
from app.services.tgapipldc_locator_service import (
    LocatorProfileItem,
    TgapipldcLocatorService,
)
from app.services.tgapipldc_runner_service_cancel_safe import (
    CancelSafeTgapipldcRunnerService,
)


class CalibrationResilienceTests(unittest.TestCase):
    def test_picker_uses_window_capture_and_f8_mode(self):
        script = calibration_init_script("telegram.profile.edit")
        self.assertIn("window.addEventListener", script)
        self.assertIn("pointerdown", script)
        self.assertIn("mousedown", script)
        self.assertIn("composedPath", script)
        self.assertIn("event.key==='F8'", script)
        self.assertIn("stopImmediatePropagation", script)
        self.assertIn("wqtgSaveLocator", script)

    def test_picker_selects_actionable_ancestor_not_generic_div(self):
        script = calibration_init_script("telegram.profile.edit")
        self.assertIn("[role='button']", script)
        self.assertNotIn("button,a,input,[role],div", script)

    def test_calibration_is_direct_by_default(self):
        service = object.__new__(TgapipldcLocatorService)
        service.list_profiles = lambda: [
            LocatorProfileItem("profiles/a", "a", "user:pass@proxy:80")
        ]
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("WQTG_CALIBRATION_USE_PROXY", None)
            self.assertEqual(service.proxy_for_profile("profiles/a"), "")

    def test_calibration_proxy_requires_explicit_opt_in(self):
        service = object.__new__(TgapipldcLocatorService)
        service.list_profiles = lambda: [
            LocatorProfileItem("profiles/a", "a", "user:pass@proxy:80")
        ]
        with patch.dict(os.environ, {"WQTG_CALIBRATION_USE_PROXY": "1"}):
            self.assertEqual(
                service.proxy_for_profile("profiles/a"),
                "user:pass@proxy:80",
            )

    def test_cancelled_details_are_structured(self):
        details = CancelSafeTgapipldcRunnerService.build_cancelled_details(
            {},
            job_id="abc",
            job_type="locator-calibration",
        )
        self.assertEqual(details["status"], "cancelled")
        self.assertEqual(details["job_id"], "abc")
        self.assertEqual(details["error"], "用户主动停止")


if __name__ == "__main__":
    unittest.main()
