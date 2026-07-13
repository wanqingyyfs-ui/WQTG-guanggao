from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "app" / "vendor" / "tgapipldc" / "src"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SRC))

from app.services.tgapipldc_behavior_service import TgapipldcBehaviorService
from automation_locator_engine import LocatorConfigStore


class FakeWorkspace:
    def __init__(self) -> None:
        self.root = Path(tempfile.mkdtemp())
        self.src_dir = SRC
        self.data_dir = self.root / "data"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._config = {
            "update_photo": True,
            "update_name": True,
            "update_username": True,
            "update_bio": True,
            "add_chat_folder": True,
        }

    def ensure_structure(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def read_profile_maintenance_config(self):
        return dict(self._config)

    def save_profile_maintenance_config(self, config):
        self._config = dict(config)
        return dict(self._config)


class BehaviorLocatorSyncTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workspace = FakeWorkspace()
        self.service = TgapipldcBehaviorService(self.workspace)

    def _locator_targets(self):
        path = self.workspace.data_dir / "automation_locators.json"
        return LocatorConfigStore(path).load()["targets"]

    def test_saving_custom_click_step_creates_matching_locator_target(self):
        behaviors = self.service.load_behaviors()
        custom = {
            "id": "custom_flow",
            "name": "自定义流程",
            "enabled": True,
            "builtin": False,
            "failure_mode": "strict",
            "steps": [
                self.service.make_custom_click_step(
                    "custom_flow", "click_confirm", "点击确认按钮"
                )
            ],
        }
        behaviors.append(custom)
        self.service.save_behaviors(behaviors)

        target = self._locator_targets()["workflow.custom_flow.click_confirm"]
        self.assertEqual(target["category"], "行为：自定义流程")
        self.assertEqual(target["description"], "点击确认按钮")
        self.assertEqual(target["behavior_id"], "custom_flow")
        self.assertEqual(target["step_id"], "click_confirm")
        self.assertEqual(target["managed_by"], "profile_behavior_step")

    def test_removing_step_removes_only_managed_locator_target(self):
        behaviors = self.service.load_behaviors()
        behaviors.append({
            "id": "custom_flow",
            "name": "自定义流程",
            "enabled": True,
            "builtin": False,
            "failure_mode": "strict",
            "steps": [self.service.make_custom_click_step("custom_flow", "click_ok", "点击确定")],
        })
        saved = self.service.save_behaviors(behaviors)
        self.assertIn("workflow.custom_flow.click_ok", self._locator_targets())

        saved["profile_behaviors"] = [
            item for item in saved["profile_behaviors"]
            if item.get("id") != "custom_flow"
        ]
        self.service.save_behaviors(saved["profile_behaviors"])
        targets = self._locator_targets()
        self.assertNotIn("workflow.custom_flow.click_ok", targets)
        self.assertIn("telegram.profile.save", targets)

    def test_reset_managed_target_keeps_behavior_link_and_clears_capture(self):
        behaviors = self.service.load_behaviors()
        behaviors.append({
            "id": "custom_flow",
            "name": "自定义流程",
            "enabled": True,
            "builtin": False,
            "failure_mode": "strict",
            "steps": [self.service.make_custom_click_step("custom_flow", "click_ok", "点击确定")],
        })
        self.service.save_behaviors(behaviors)
        target_id = "workflow.custom_flow.click_ok"
        path = self.workspace.data_dir / "automation_locators.json"
        store = LocatorConfigStore(path)
        config = store.load()
        config["targets"][target_id]["locator_mode"] = "absolute_position"
        config["targets"][target_id]["absolute_position"].update(
            x=100, y=200, captured=True
        )
        store.save(config)

        self.assertTrue(self.service.reset_managed_locator_target(target_id))
        reset = self._locator_targets()[target_id]
        self.assertFalse(reset["absolute_position"]["captured"])
        self.assertEqual(reset["behavior_id"], "custom_flow")
        self.assertEqual(reset["step_id"], "click_ok")


if __name__ == "__main__":
    unittest.main()
