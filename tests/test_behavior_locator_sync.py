from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "app" / "vendor" / "tgapipldc" / "src"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SRC))

from app.services.tgapipldc_behavior_service_v2 import TgapipldcBehaviorService
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

    def test_builtin_atomic_page_steps_are_created_in_locator_settings(self):
        self.service.load_config()
        targets = self._locator_targets()
        expected = {
            "workflow.name.step02_open_main_menu",
            "workflow.name.step03_open_settings",
            "workflow.name.step04_open_profile_edit",
            "workflow.name.step05_input_first_name",
            "workflow.name.step06_input_last_name",
            "workflow.name.step07_save_name",
            "workflow.photo.step05_upload_photo",
            "workflow.folder.step03_input_folder_link",
        }
        self.assertTrue(expected.issubset(targets))
        self.assertEqual(
            targets["workflow.name.step05_input_first_name"]["step_type"],
            "locator.fill",
        )
        self.assertEqual(
            targets["workflow.photo.step05_upload_photo"]["step_type"],
            "locator.upload",
        )

    def test_saving_custom_fill_step_creates_matching_locator_target(self):
        behaviors = self.service.load_behaviors()
        custom = {
            "id": "custom_flow",
            "name": "自定义流程",
            "enabled": True,
            "builtin": False,
            "failure_mode": "strict",
            "steps": [
                self.service.make_custom_page_step(
                    "custom_flow",
                    "input_value",
                    "输入配置值",
                    "locator.fill",
                    "config.bio_text",
                )
            ],
        }
        behaviors.append(custom)
        self.service.save_behaviors(behaviors)

        target = self._locator_targets()["workflow.custom_flow.input_value"]
        self.assertEqual(target["category"], "行为：自定义流程")
        self.assertEqual(target["description"], "输入配置值")
        self.assertEqual(target["behavior_id"], "custom_flow")
        self.assertEqual(target["step_id"], "input_value")
        self.assertEqual(target["step_type"], "locator.fill")
        self.assertEqual(target["managed_by"], "profile_behavior_step")

    def test_removing_step_removes_only_its_managed_locator_target(self):
        behaviors = self.service.load_behaviors()
        custom = {
            "id": "custom_flow",
            "name": "自定义流程",
            "enabled": True,
            "builtin": False,
            "failure_mode": "strict",
            "steps": [self.service.make_custom_click_step("custom_flow", "click_ok", "点击确定")],
        }
        behaviors.append(custom)
        saved = self.service.save_behaviors(behaviors)
        self.assertIn("workflow.custom_flow.click_ok", self._locator_targets())

        saved["profile_behaviors"] = [
            item for item in saved["profile_behaviors"]
            if item.get("id") != "custom_flow"
        ]
        self.service.save_behaviors(saved["profile_behaviors"])
        targets = self._locator_targets()
        self.assertNotIn("workflow.custom_flow.click_ok", targets)
        self.assertIn("workflow.name.step07_save_name", targets)
        self.assertIn("telegram.profile.save", targets)

    def test_reset_managed_target_keeps_atomic_step_link_and_clears_capture(self):
        self.service.load_config()
        target_id = "workflow.name.step07_save_name"
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
        self.assertEqual(reset["behavior_id"], "name")
        self.assertEqual(reset["step_id"], "step07_save_name")
        self.assertEqual(reset["step_type"], "locator.click")


if __name__ == "__main__":
    unittest.main()
