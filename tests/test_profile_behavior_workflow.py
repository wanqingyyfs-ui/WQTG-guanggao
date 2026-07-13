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

import profile_behavior_workflow as workflow


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
    def test_photo_has_crop_then_second_profile_save(self):
        photo = workflow.behavior_map({})["photo"]
        kinds = [item["type"] for item in photo["steps"]]
        self.assertEqual(kinds, [
            "photo.select_upload", "photo.crop_confirm",
            "profile.save", "photo.wait_settled",
        ])
        self.assertLess(kinds.index("photo.crop_confirm"), kinds.index("profile.save"))

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

    def test_install_replaces_fixed_process_with_generic_workflow(self):
        module = FakeModule()
        module.process_account = lambda *args: {"legacy": True}
        module.action_steps = lambda *args: ["legacy"]
        module.failed_steps_from_result = lambda *args: ["legacy"]
        module.unfinished_steps_from_result = lambda *args: ["legacy"]
        workflow.install_profile_behavior_workflow(module)
        self.assertTrue(module._wqtg_behavior_workflow_installed)
        self.assertTrue(getattr(module.process_account, "_wqtg_behavior_workflow", False))
        self.assertEqual(module.action_steps("photo", module.normalize_config({}))[:2], [
            "photo.select_upload", "photo.crop_confirm",
        ])

    def test_photo_execution_clicks_crop_then_profile_save(self):
        calls = []
        photo = Path(tempfile.mkdtemp()) / "avatar.png"
        photo.write_bytes(b"png")

        class Page:
            def wait_for_timeout(self, milliseconds):
                calls.append(("wait", milliseconds))

        class Engine:
            def click(self, page, target_id, diagnose_on_failure=False):
                calls.append(target_id)
                return True

        module = types.SimpleNamespace(
            log=lambda message: calls.append(("log", message)),
            select_photo=lambda config, account_index, used: photo,
            open_settings=lambda page: calls.append("settings") or True,
            click_profile_edit_icon_button=lambda page: calls.append("edit") or True,
            click_profile_avatar_for_upload=lambda page, path: calls.append("upload"),
            wait_media_editor_closed=lambda page, timeout=30000: calls.append("editor_closed") or True,
            click_profile_save_button_multi=lambda *args, **kwargs: calls.append("fallback_save") or True,
            wait_photo_save_ui_settled=lambda page, timeout_ms=15000: calls.append("settled") or True,
        )
        old_engine = workflow._locator_engine
        workflow._locator_engine = lambda _module: Engine()
        try:
            state = {
                "account": {}, "account_index": 1, "used_photos": set(),
                "photo_path": None, "step_results": [], "domain_statuses": {},
            }
            status = workflow._execute_behavior(module, Page(), "photo", state, workflow.normalize_workflow_config({}))
        finally:
            workflow._locator_engine = old_engine
        self.assertEqual(status, "success")
        self.assertLess(calls.index("telegram.photo.editor_save"), calls.index("telegram.profile.save"))
        self.assertNotIn("fallback_save", calls)

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
