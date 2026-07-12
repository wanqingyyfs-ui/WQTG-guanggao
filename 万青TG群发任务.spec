# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata


project_root = Path.cwd()
app_icon = project_root / "app.ico"
vendor_src = project_root / "app" / "vendor" / "tgapipldc" / "src"

# PyInstaller data files are read-only templates in one-file mode. At runtime
# TgapipldcWorkspaceService copies these scripts to LocalAppData before execution.
datas = []
if app_icon.exists():
    datas.append((str(app_icon), "."))
if vendor_src.exists():
    datas.append((str(vendor_src), "app/vendor/tgapipldc/src"))

# Playwright officially supports bundling Chromium with PyInstaller when the
# browser is installed with PLAYWRIGHT_BROWSERS_PATH=0 before the build.
datas += collect_data_files("playwright")
datas += copy_metadata("playwright")

hiddenimports = []
hiddenimports += collect_submodules("telethon")
hiddenimports += collect_submodules("playwright")


a = Analysis(
    ["main.py"],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(project_root / "hooks" / "runtime_playwright.py")],
    excludes=[
        "tkinter",
        "unittest",
        "pytest",
        "IPython",
        "notebook",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="万青TG群发任务",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(app_icon) if app_icon.exists() else None,
)
