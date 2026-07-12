from __future__ import annotations

import os
import sys


# Playwright's documented PyInstaller bundle mode stores browser binaries next
# to the package and resolves them through PLAYWRIGHT_BROWSERS_PATH=0.
if getattr(sys, "frozen", False):
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "0")
