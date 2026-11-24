# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for the portable Windows build.
#   pip install -r requirements.txt pyinstaller
#   pyinstaller packaging/windows/voxdock.spec --noconfirm --clean
# Output: dist/VoxDock/VoxDock.exe
import os
import re
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).resolve().parents[1]  # noqa: F821 - SPECPATH is injected by PyInstaller
HERE = ROOT / "packaging" / "windows"

# ------------------------------------------------------------------ version
raw_version = os.environ.get("VOXDOCK_VERSION", "1.0.0").lstrip("v")
nums = [int(n) for n in re.findall(r"\d+", raw_version)[:4]] + [0, 0, 0, 0]
ver_tuple = tuple(nums[:4])

version_info = None
try:
    from PyInstaller.utils.win32.versioninfo import (
        FixedFileInfo, StringFileInfo, StringStruct, StringTable, VarFileInfo, VarStruct, VSVersionInfo,
    )

    version_info = VSVersionInfo(
        ffi=FixedFileInfo(filevers=ver_tuple, prodvers=ver_tuple),
        kids=[
            StringFileInfo([StringTable("080404B0", [
                StringStruct("CompanyName", "VoxDock"),
                StringStruct("FileDescription", "VoxDock 多平台声音克隆聚合平台"),
                StringStruct("FileVersion", raw_version),
                StringStruct("InternalName", "VoxDock"),
                StringStruct("OriginalFilename", "VoxDock.exe"),
                StringStruct("ProductName", "VoxDock"),
                StringStruct("ProductVersion", raw_version),
                StringStruct("LegalCopyright", "MIT License"),
            ])]),
            VarFileInfo([VarStruct("Translation", [0x0804, 1200])]),
        ],
    )
except Exception:  # noqa: BLE001 - version resource is optional
    version_info = None

# ----------------------------------------------------------------- analysis
hiddenimports = (
    collect_submodules("uvicorn")
    + [
        "app.main",
        "sqlalchemy.dialects.sqlite.aiosqlite",
        "aiosqlite",
        "greenlet",
        "python_multipart",
        "multipart",
    ]
)

a = Analysis(
    [str(HERE / "entry.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[(str(ROOT / "app" / "static"), "app/static")],
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "pytest", "respx", "uvloop", "IPython", "matplotlib", "numpy", "PIL"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="VoxDock",
    console=True,
    icon=str(HERE / "voxdock.ico"),
    version=version_info,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="VoxDock")
