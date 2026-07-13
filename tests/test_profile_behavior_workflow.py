from __future__ import annotations

import sys
import tempfile
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "app" / "vendor" / "tgapipldc" / "src"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SRC))

import profile_behavior_locator_bridge as bridge
import profile_behavior_workflow as workflow

bridge.ensure_locator_click_support()


class FakeModule:
    DEFAULT_CONFIG = {
        "update_photo": True,
        "update_name": True,
        "update_username": True,
        "update_bio": True,
        "add_chat_folder": True,
    }
    STEP_STATUS_FIELDS = {
        "photo": "photo_status", "name": "name_status",
        "username": "username_status", "bio": "bio_status",
        "folder": "folder_status",
    }

    @staticmethod
    def normalize_config(raw):
        value = dict(FakeModule.DEFAULT_CONFIG)
        value.update(dict(raw or {}))
        return value

    @staticmethod
    def safe_status_row(account, action):
        return {
            "phone": account.get("phone", ""), "action": action,
            "photo_status": "skipped", "name_status": "skipped",
            "username_status": "skipped", "bio_status": "skipped",
            "folder_status": "skipped", "final_status": "pending", "note": "",
        }


class WorkflowConfigTests(unittest.TestCase):
    def test_photo_is_split_into_numbered_atomic_steps(self):
        photo = workflow.behavior_map({})["photo"]
        self.assertEqual(
            [item["id"] for item in photo["steps"]],
            [
                "step01_prepare_photo",
                "step02_open_main_menu",
                "step03_open_settings",
                "step04_open_profile_edit",
                "step05_upload_photo",
                "step06_confirm_crop",
                "step07_save_profile",
                "step08_verify_photo",
            ],
        )
        self.assertEqual(photo["steps"][4]["type"], "locator.upload")
        self.assertEqual(photo["steps"][5]["type"], "locator.click")
        self.assertEqual(photo["steps"][6]["type"], "locator.click")

    def test_name_username_bio_and_folder_include_config_data_steps(self):
        behaviors = workflow.behavior_map({})
        self.assertEqual(behaviors["name"]["steps"][0]["type"], "data.prepare_name")
        self.assertEqual(behaviors["username"]["steps"][0]["type"], "data.prepare_username")
        self.assertEqual(behaviors["bio"]["steps"][0]["type"], "data.prepare_bio")
        self.assertEqual(behaviors["folder"]["steps"][0]["type"], "data.prepare_folder")
        self.assertIn("locator.fill", {item["type"] for item in behaviors["name"]["steps"]})
        self.assertIn("locator.fill", {item["type"] for item in behaviors["username"]["steps"]})
        self.assertIn("locator.fill", {item["type"] for item in behaviors["bio"]["steps"]})
        self.assertIn("locator.fill", {item["type"] for item in behaviors["folder"]["steps"]})

    def test_custom_behaviors_and_steps_keep_order(self):
        config = workflow.normalize_workflow_config({
            "profile_behaviors": [{
                "id": "custom_flow", "name": "自定义流程", "builtin": False,
                "enabled": True, "failure_mode": "continue",
                "steps": [
                    {"id": "wait_a", "type": "wait", "params": {"milliseconds": 100}},
                    {"id": "run_photo", "type": "behavior.run", "params": {"behavior_id": "photo"}},
                ],
            }],
        })
        custom = workflow.behavior_map(config)["custom_flow"]
        self.assertEqual([item["id"] for item in custom["steps"]], ["wait_a", "run_photo"])
        self.assertEqual(custom["failure_mode"], "continue")

    def test_legacy_flags_control_builtin_enabled_state(self):
        self.assertFalse(workflow.behavior_map({"update_photo": False})["photo"]["enabled"])

    def test_install_replaces_fixed_process_with_atomic_workflow(self):
        module = FakeModule()
        module.process_account = lambda *args: {"legacy": True}
        module.action_steps = lambda *args: ["legacy"]
        module.failed_steps_from_result = lambda *args: ["legacy"]
        module.unfinished_steps_from_result = lambda *args: ["legacy"]
        workflow.install_profile_behavior_workflow(module)
        self.assertTrue(module._wqtg_behavior_workflow_installed)
        self.assertTrue(getattr(module.process_account, "_wqtg_behavior_workflow", False))
        self.assertEqual(module.action_steps("name", module.normalize_config({}))[:3], [
            "data.prepare_name", "locator.click", "locator.click",
        ])

    def test_cycle_reference_is_rejected(self):
        config = workflow.normalize_workflow_config({
            "profile_behaviors": [
                {"id": "a", "steps": [{"id": "to_b", "type": "behavior.run", "params": {"behavior_id": "b"}}]},
                {"id": "b", "steps": [{"id": "to_a", "type": "behavior.run", "params": {"behavior_id": "a"}}]},
            ],
        })
        state = {"account": {}, "account_index": 1, "used_photos": set(), "step_results": [], "domain_statuses": {}}
        with self.assertRaisesRegex(RuntimeError, "循环引用"):
            workflow._execute_behavior(types.SimpleNamespace(log=lambda *_: None), object(), "a", state, config)


if __name__ == "__main__":
    unittest.main()
