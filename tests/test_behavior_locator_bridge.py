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


class BehaviorLocatorBridgeTests(unittest.TestCase):
    def test_custom_step_generates_same_locator_target_id(self):
        item = bridge.make_custom_click_step("photo", "click_extra_save", "点击额外保存")
        self.assertEqual(item["type"], "locator.click")
        self.assertEqual(
            item["params"]["target_id"],
            "workflow.photo.click_extra_save",
        )
        self.assertEqual(
            bridge.locator_target_for_step("photo", item),
            "workflow.photo.click_extra_save",
        )

    def test_builtin_click_steps_resolve_existing_locator_targets(self):
        self.assertEqual(
            bridge.locator_target_for_step("photo", {"type": "photo.crop_confirm"}),
            "telegram.photo.editor_save",
        )
        self.assertEqual(
            bridge.locator_target_for_step("photo", {"type": "profile.save"}),
            "telegram.profile.save",
        )

    def test_custom_locator_click_is_preserved_by_workflow_normalization(self):
        bridge.ensure_locator_click_support()
        config = workflow.normalize_workflow_config({
            "profile_behaviors": [{
                "id": "custom",
                "name": "自定义",
                "steps": [bridge.make_custom_click_step("custom", "click_ok", "点击确定")],
            }],
        })
        item = workflow.behavior_map(config)["custom"]["steps"][0]
        self.assertEqual(item["type"], "locator.click")
        self.assertEqual(item["params"]["target_id"], "workflow.custom.click_ok")

    def test_custom_locator_click_executes_exact_target(self):
        bridge.ensure_locator_click_support()
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

    def test_invalid_freeform_step_id_is_rejected(self):
        with self.assertRaises(ValueError):
            bridge.make_custom_click_step("photo", "中文 步骤", "错误步骤")


if __name__ == "__main__":
    unittest.main()
