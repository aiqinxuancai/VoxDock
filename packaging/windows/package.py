"""Assemble the portable Windows zip from the PyInstaller output.

    python packaging/windows/package.py [version]

Input : dist/VoxDock/            (pyinstaller packaging/windows/voxdock.spec)
Output: dist/VoxDock-<version>-windows-x64.zip
"""
from __future__ import annotations

import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def main(version: str) -> Path:
    src = ROOT / "dist" / "VoxDock"
    if not (src / "VoxDock.exe").is_file():
        sys.exit("dist/VoxDock/VoxDock.exe not found - run: pyinstaller packaging/windows/voxdock.spec")
    shutil.rmtree(src / "data", ignore_errors=True)  # never ship local test data
    shutil.copy2(ROOT / ".env.example", src / ".env.example")
    shutil.copy2(ROOT / "LICENSE", src / "LICENSE.txt")
    for doc in HERE.glob("*.txt"):
        shutil.copy2(doc, src / doc.name)

    name = f"VoxDock-{version}-windows-x64"
    out = ROOT / "dist" / f"{name}.zip"
    out.unlink(missing_ok=True)
    # zipfile stores non-ASCII names as UTF-8 (flag 0x800), so Chinese file names survive
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in sorted(src.rglob("*")):
            zf.write(path, f"{name}/{path.relative_to(src).as_posix()}")
    print(f"{out}  ({out.stat().st_size / 1024 / 1024:.1f} MB)")
    return out


if __name__ == "__main__":
    main((sys.argv[1] if len(sys.argv) > 1 else "local").lstrip("v"))
