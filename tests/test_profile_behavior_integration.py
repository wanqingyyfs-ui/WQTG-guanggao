from __future__ import annotations

import os
import sys
import tempfile
import types
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "app" / "vendor" / "tgapipldc" / "src"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SRC))


class FakeWorkspace:
    def __init__(self):
        root = Path(tempfile.mkdtemp())
        self.workspace_dir = root
        self.src_dir = SRC
        self.data_dir = root / "data"
        self.data_dir.mkdir()
        self.profiles_dir = root / "profiles"
        self.profiles_dir.mkdir()
        self.account_proxy_map_csv_path = self.data_dir / "account_proxy_map.csv"
        self._config = {"bio_text": "old", "update_photo": True}

    def ensure_structure(self):
        return None

    def read_profile_maintenance_config(self):
        return dict(self._config)

    def save_profile_maintenance_config(self, config):
        self._config = dict(config)
        return dict(self._config)


workspace_module = types.ModuleType("app.services.tgapipldc_workspace_service")
workspace_module.TgapipldcWorkspaceService = FakeWorkspace
sys.modules.setdefault("app.services.tgapipldc_workspace_service", workspace_module)

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget

from app.services.tgapipldc_behavior_service import TgapipldcBehaviorService
from app.services.tgapipldc_locator_service import TgapipldcLocatorService


class FakeProfilePage(QWidget):
    profile_maintenance_requested = Signal(str, dict)

    def __init__(self):
        super().__init__()
        self.setLayout(QVBoxLayout())
        self.config = {"bio_text": "from-form", "update_photo": True}
        self.logs = []

    def get_profile_maintenance_config(self):
        return dict(self.config)

    def set_profile_maintenance_config(self, config):
        self.config = dict(config)

    def append_log(self, message):
        self.logs.append(str(message))


class FakeWindow(QWidget):
    def __init__(self, profile_page):
        super().__init__()
        self.runtime_service = object()
        layout = QVBoxLayout(self)
        layout.addWidget(profile_page)


class BehaviorIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_service_save_preserves_base_fields_and_behaviors(self):
        workspace = FakeWorkspace()
        service = TgapipldcBehaviorService(workspace)
        behaviors = service.load_behaviors()
        behaviors.append({
            "id": "custom_flow", "name": "自定义流程", "enabled": True,
            "builtin": False, "failure_mode": "strict", "steps": [],
        })
        saved = service.save_behaviors(behaviors, {"bio_text": "new"})
        self.assertEqual(saved["bio_text"], "new")
        self.assertIn("custom_flow", {item["id"] for item in saved["profile_behaviors"]})

    def test_manager_button_installs_and_legacy_form_preserves_workflow(self):
        bootstrap = types.ModuleType("app.gui.tgapipldc_panel_bootstrap")
        bootstrap._run_profile_maintenance = lambda window, action, config: None
        previous = sys.modules.get("app.gui.tgapipldc_panel_bootstrap")
        sys.modules["app.gui.tgapipldc_panel_bootstrap"] = bootstrap
        try:
            workspace = FakeWorkspace()
            workspace.save_profile_maintenance_config(TgapipldcBehaviorService(workspace).load_config())
            page = FakeProfilePage()
            window = FakeWindow(page)
            window.show()
            self.app.processEvents()

            service = TgapipldcLocatorService(workspace)
            self.assertIsNotNone(service)
            self.assertTrue(hasattr(page, "behavior_manager_button"))
            self.assertEqual(page.behavior_manager_button.text(), "行为与步骤管理")
            merged = page.get_profile_maintenance_config()
            self.assertEqual(merged["bio_text"], "from-form")
            self.assertIn("profile_behaviors", merged)
            window.close()
        finally:
            if previous is None:
                sys.modules.pop("app.gui.tgapipldc_panel_bootstrap", None)
            else:
                sys.modules["app.gui.tgapipldc_panel_bootstrap"] = previous


if __name__ == "__main__":
    unittest.main()
