import json
import shutil
import subprocess
import sys
from pathlib import Path

import pyinstaller_versionfile
from packaging.version import Version


def get_install_tree_library_path():
    lib_base = Path("lib")
    python_paths = list(lib_base.glob("python3.*"))
    if len(python_paths) > 1:
        raise RuntimeError("Multiple python installs found")
    return python_paths[0] / "site-packages"


def get_install_languages():
    share_base = Path("share")
    mo_paths = (share_base / "locale").glob("*/LC_MESSAGES/meld.mo")
    return [p.parents[1].name for p in mo_paths]


def get_repo_path():
    return subprocess.run(["git", "rev-parse", "--show-toplevel"],
        encoding="utf-8",
        capture_output=True,
        text=True,
    ).stdout.strip("\n")

# NOTE: First attempt in path handling was to do this nicely and find the repo
# root and do meson introspection and file copying relative to that. This
# didn't work because the absolute paths somehow got mangled from being
# msys-root-based paths to being /c/home/whatever style paths. In the end,
# just using "../.." worked.

def get_version() -> Version:
    cwd = get_repo_path()

    projectinfo = json.loads(
        subprocess.run(
            ["meson", "introspect", "meson.build", "--projectinfo"],
            cwd="../..",
            encoding="utf-8",
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    )
    return Version(projectinfo["version"])


def copy_repo_files():
    shutil.copy2(
        "../../data/icons/org.gnome.meld.ico",
        "./meld.ico",
    )


copy_repo_files()
version = get_version()
version_string = f"{version.major}.{version.minor}.{version.micro}"
copyright = "Copyright © 2002-2006 Stephen Kennedy, 2008-2025 Kai Willadsen"

# Insert the site-packages path that's been installed by meson/ninja into
# PYTHONPATH so that pyinstaller finds the meld package from there.
sys.path.insert(0, str(get_install_tree_library_path()))

a = Analysis(
    ["bin/meld"],
    binaries=[],
    datas=[
        ("meld.ico", "."),
        ("share", "share"),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={
        "gi": {
            "icons": ["Adwaita"],
            "themes": ["Adwaita"],
            "languages": get_install_languages(),
            "module-versions": {
                "Gtk": "3.0",
                "GtkSource": "4",
            },
        },
    },
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

pyinstaller_versionfile.create_versionfile(
    output_file="file_version_info.txt",
    version=version_string,
    company_name="Meld",
    file_description="Meld",
    internal_name="Meld",
    legal_copyright=copyright,
    original_filename="meld.exe",
    product_name="Meld",
)

with open("version.nsh", "w") as f:
    print(f'!define VERSION "{version_string}"', file=f)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="meld",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    icon="meld.ico",
    version="file_version_info.txt",
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="meld",
)
