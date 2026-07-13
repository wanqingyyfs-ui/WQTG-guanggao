from __future__ import annotations

import sys
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


class BehaviorLocatorBridgeTests(unittest.TestCase):
    def test_custom_page_steps_generate_same_locator_target_id(self):
        for step_type in ("locator.click", "locator.fill", "locator.upload"):
            item = bridge.make_custom_page_step(
                "photo", "step09_extra", "额外步骤", step_type,
                value_source="state.photo_path",
            )
            self.assertEqual(item["type"], step_type)
            self.assertEqual(
                item["params"]["target_id"],
                "workflow.photo.step09_extra",
            )
            self.assertEqual(
                bridge.locator_target_for_step("photo", item),
                "workflow.photo.step09_extra",
            )

    def test_all_builtin_page_steps_have_independent_targets(self):
        defaults = {item["id"]: item for item in bridge.atomic_default_behaviors({})}
        name_steps = defaults["name"]["steps"]
        page_steps = [item for item in name_steps if item["type"] in bridge.PAGE_STEP_TYPES]
        self.assertEqual(
            [item["id"] for item in page_steps],
            [
                "step02_open_main_menu",
                "step03_open_settings",
                "step04_open_profile_edit",
                "step05_input_first_name",
                "step06_input_last_name",
                "step07_save_name",
            ],
        )
        self.assertEqual(
            [item["params"]["target_id"] for item in page_steps],
            [f"workflow.name.{item['id']}" for item in page_steps],
        )

    def test_legacy_name_update_migrates_to_numbered_atomic_steps(self):
        config = workflow.normalize_workflow_config({
            "profile_behaviors": [{
                "id": "name",
                "name": "修改昵称",
                "builtin": True,
                "steps": [{
                    "id": "update",
                    "name": "修改昵称",
                    "type": "name.update",
                }],
            }],
        })
        steps = workflow.behavior_map(config)["name"]["steps"]
        self.assertEqual(len(steps), 8)
        self.assertEqual(steps[0]["type"], "data.prepare_name")
        self.assertEqual(steps[4]["type"], "locator.fill")
        self.assertEqual(steps[6]["type"], "locator.click")
        self.assertNotIn("name.update", {item["type"] for item in steps})

    def test_custom_locator_click_executes_exact_target(self):
        calls = []
        original_click = workflow.locator_click
        workflow.locator_click = lambda module, page, target_id: calls.append(target_id) or True
        try:
            item = bridge.make_custom_click_step("custom", "click_ok", "点击确定")
            status = workflow.execute_step(
                types.SimpleNamespace(),
                object(),
                item,
                {"account": {}, "account_index": 1, "used_photos": set()},
                {},
                ("custom",),
            )
        finally:
            workflow.locator_click = original_click
        self.assertEqual(status, "success")
        self.assertEqual(calls, ["workflow.custom.click_ok"])

    def test_data_steps_read_profile_maintenance_configuration(self):
        state = {"account": {}, "account_index": 2, "used_photos": set()}
        module = types.SimpleNamespace(
            select_name=lambda config: ("Alice", "Smith"),
            username_for_account=lambda config, index: f"user{index:03d}",
            validate_username=lambda value: True,
        )
        name_status = workflow.execute_step(
            module, object(),
            bridge.function_step("step01_name", bridge.DATA_PREPARE_NAME, "读取昵称", domain="name"),
            state, {"name_pool": ["Alice,Smith"]}, ("name",),
        )
        username_status = workflow.execute_step(
            module, object(),
            bridge.function_step("step01_username", bridge.DATA_PREPARE_USERNAME, "生成用户名", domain="username"),
            state, {"username_keyword": "user"}, ("username",),
        )
        bio_status = workflow.execute_step(
            module, object(),
            bridge.function_step("step01_bio", bridge.DATA_PREPARE_BIO, "读取签名", domain="bio"),
            state, {"bio_text": "hello"}, ("bio",),
        )
        self.assertEqual((name_status, username_status, bio_status), ("success", "success", "success"))
        self.assertEqual(state["first_name"], "Alice")
        self.assertEqual(state["last_name"], "Smith")
        self.assertEqual(state["username"], "user002")
        self.assertEqual(state["bio_text"], "hello")

    def test_invalid_freeform_step_id_is_rejected(self):
        with self.assertRaises(ValueError):
            bridge.make_custom_click_step("photo", "中文 步骤", "错误步骤")


if __name__ == "__main__":
    unittest.main()
