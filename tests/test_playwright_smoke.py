from __future__ import annotations

from pathlib import Path

import pytest


def test_persistent_chromium_can_launch(tmp_path) -> None:
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as runtime:
        executable = Path(runtime.chromium.executable_path)
        if not executable.exists():
            pytest.skip("Playwright Chromium is not installed in this environment")
        context = runtime.chromium.launch_persistent_context(
            user_data_dir=str(tmp_path / "profile"),
            headless=True,
            viewport={"width": 1280, "height": 720},
        )
        try:
            page = context.pages[0] if context.pages else context.new_page()
            page.set_content("<title>WQTG smoke</title><h1>ok</h1>")
            assert page.title() == "WQTG smoke"
            assert page.locator("h1").inner_text() == "ok"
        finally:
            context.close()
