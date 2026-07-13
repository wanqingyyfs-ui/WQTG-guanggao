from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "app" / "vendor" / "tgapipldc" / "src"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SRC))

import profile_behavior_locator_bridge as bridge
import profile_behavior_workflow as workflow

bridge.ensure_locator_click_support()


class AtomicProfileStepContractTests(unittest.TestCase):
    def test_no_builtin_behavior_keeps_legacy_composite_step(self):
        legacy = {
            "photo.select_upload", "photo.crop_confirm", "profile.save",
            "photo.wait_settled", "name.update", "username.update",
            "bio.update", "folder.add",
        }
        behaviors = workflow.behavior_map({})
        for behavior_id in ("photo", "name", "username", "bio", "folder"):
            self.assertTrue(behaviors[behavior_id]["steps"])
            self.assertFalse(legacy.intersection(
                {item["type"] for item in behaviors[behavior_id]["steps"]}
            ))

    def test_every_builtin_page_action_has_workflow_target(self):
        behaviors = workflow.behavior_map({})
        for behavior_id in ("photo", "name", "username", "bio", "folder"):
            for item in behaviors[behavior_id]["steps"]:
                if item["type"] not in bridge.PAGE_STEP_TYPES:
                    continue
                self.assertEqual(
                    item["params"]["target_id"],
                    f"workflow.{behavior_id}.{item['id']}",
                )

    def test_profile_form_configuration_is_represented_as_steps(self):
        behaviors = workflow.behavior_map({})
        expected = {
            "photo": {"data.prepare_photo", "locator.upload"},
            "name": {"data.prepare_name", "locator.fill"},
            "username": {"data.prepare_username", "locator.fill"},
            "bio": {"data.prepare_bio", "locator.fill"},
            "folder": {"data.prepare_folder", "locator.fill"},
        }
        for behavior_id, required_types in expected.items():
            actual = {item["type"] for item in behaviors[behavior_id]["steps"]}
            self.assertTrue(required_types.issubset(actual))


if __name__ == "__main__":
    unittest.main()
