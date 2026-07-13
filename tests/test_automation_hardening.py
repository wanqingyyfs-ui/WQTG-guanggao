from __future__ import annotations

import csv
import json
import multiprocessing as mp
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "app" / "vendor" / "tgapipldc" / "src"
sys.path.insert(0, str(SRC))

from automation_atomic_io import atomic_write_csv, read_csv_rows
from automation_locator_engine import LocatorConfigStore, LocatorEngine
from profile_lock import ProfileBusyError, ProfileLock


class FakeLocator:
    def __init__(self, visible=True):
        self.visible = visible
        self.clicked = 0
    def count(self): return 1
    def nth(self, index): return self
    def is_visible(self, timeout=0): return self.visible
    def scroll_into_view_if_needed(self, timeout=0): return None
    def click(self, timeout=0): self.clicked += 1


class FakeMouse:
    def __init__(self): self.clicks = []
    def click(self, x, y): self.clicks.append((x, y))


class FakePage:
    def __init__(self):
        self.css = FakeLocator(True)
        self.mouse = FakeMouse()
        self.viewport_size = {"width": 1000, "height": 500}
        self.url = "https://example.test"
    def locator(self, value): return self.css
    def get_by_role(self, role, name=None): return FakeLocator(False)
    def get_by_text(self, value): return FakeLocator(False)
    def wait_for_timeout(self, ms): return None
    def screenshot(self, **kwargs): Path(kwargs["path"]).write_bytes(b"png")
    def content(self): return "<html></html>"


def hold_lock(profile: str, root: str, ready: mp.Queue, release: mp.Queue):
    with ProfileLock(profile, root):
        ready.put(True)
        release.get(timeout=10)


class HardeningTests(unittest.TestCase):
    def test_config_store_creates_defaults_and_persists_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "locators.json"
            store = LocatorConfigStore(path)
            config = store.load()
            self.assertIn("telegram.profile.save", config["targets"])
            target = dict(config["targets"]["telegram.profile.save"])
            target["timeout_ms"] = 9999
            store.save_target("telegram.profile.save", target)
            self.assertEqual(store.load()["targets"]["telegram.profile.save"]["timeout_ms"], 9999)
            self.assertTrue(path.exists())

    def test_invalid_coordinate_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = LocatorConfigStore(Path(tmp) / "locators.json")
            config = store.load()
            config["targets"]["telegram.profile.save"]["strategies"].append(
                {"type": "relative_coordinate", "x_ratio": 2, "y_ratio": 0.5, "enabled": True}
            )
            with self.assertRaises(ValueError):
                store.validate(config)

    def test_locator_prefers_css_before_coordinate(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "locators.json"
            store = LocatorConfigStore(path)
            config = store.load()
            config["targets"]["telegram.profile.save"] = {
                "category": "test", "description": "test", "timeout_ms": 1000,
                "strategies": [
                    {"type": "css", "value": "button.save", "enabled": True},
                    {"type": "relative_coordinate", "x_ratio": 0.9, "y_ratio": 0.9, "enabled": True},
                ],
            }
            store.save(config)
            page = FakePage()
            engine = LocatorEngine(path, Path(tmp) / "diag")
            self.assertTrue(engine.click(page, "telegram.profile.save"))
            self.assertEqual(page.css.clicked, 1)
            self.assertEqual(page.mouse.clicks, [])

    def test_atomic_csv_write_and_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "data.csv"
            atomic_write_csv(path, ["a", "b"], [{"a": "1", "b": "2"}])
            atomic_write_csv(path, ["a", "b"], [{"a": "3", "b": "4"}])
            fields, rows = read_csv_rows(path)
            self.assertEqual(fields, ["a", "b"])
            self.assertEqual(rows[0]["a"], "3")
            self.assertTrue(path.with_suffix(".csv.bak").exists())

    def test_profile_lock_is_cross_process(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile = str(Path(tmp) / "profile")
            root = str(Path(tmp) / "locks")
            ready, release = mp.Queue(), mp.Queue()
            process = mp.Process(target=hold_lock, args=(profile, root, ready, release))
            process.start()
            self.assertTrue(ready.get(timeout=10))
            try:
                with self.assertRaises(ProfileBusyError):
                    ProfileLock(profile, root, timeout_seconds=0).acquire()
            finally:
                release.put(True)
                process.join(timeout=10)
            self.assertEqual(process.exitcode, 0)

    def test_profile_all_continues_when_stop_on_error_false(self):
        import automation_entry

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            calls = []
            rows_written = []
            fake = types.ModuleType("update_telegram_profile")
            fake.BASE_DIR = base
            fake.__file__ = str(base / "update_telegram_profile.py")
            fake.load_config = lambda: {"stop_on_error": False, "account_delay_ms": 0}
            fake.read_account_proxy_map = lambda: [
                {"phone": "1", "country": "US", "profile_dir": "profiles/a", "raw_proxy": ""},
                {"phone": "2", "country": "US", "profile_dir": "profiles/b", "raw_proxy": ""},
            ]
            fake.split_phone_for_telegram = lambda phone, country: (phone, "+1", phone)
            fake.safe_status_row = lambda account, action: {"phone": account["phone"], "profile_dir": account["profile_dir"], "action": action}
            def process_account(action, config, account, index, total, used):
                calls.append(account["phone"])
                return {"phone": account["phone"], "profile_dir": account["profile_dir"], "action": action,
                        "final_status": "failed" if account["phone"] == "1" else "success", "note": ""}
            fake.process_account = process_account
            fake.write_result = lambda row: rows_written.append(dict(row))
            fake.action_steps = lambda action, config: ["name"]
            fake.failed_steps_from_result = lambda row: ["name"] if row.get("final_status") != "success" else []
            fake.unfinished_steps_from_result = lambda row, steps: []
            fake.write_failed = lambda row: None
            fake.now_text = lambda: "now"
            fake.log = lambda message: None
            sys.modules["update_telegram_profile"] = fake
            result_path = base / "result.json"
            old = os.environ.get("WQTG_JOB_RESULT")
            os.environ["WQTG_JOB_RESULT"] = str(result_path)
            try:
                code = automation_entry.run_profile("all")
            finally:
                if old is None: os.environ.pop("WQTG_JOB_RESULT", None)
                else: os.environ["WQTG_JOB_RESULT"] = old
                sys.modules.pop("update_telegram_profile", None)
            self.assertEqual(code, 2)
            self.assertEqual(calls, ["1", "2"])
            summary = json.loads(result_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["status"], "partial_success")


if __name__ == "__main__":
    unittest.main()
