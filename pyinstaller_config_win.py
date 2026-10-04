import os
import sys
from pathlib import Path

import PyInstaller.__main__

from model_utils import find_molscribe_checkpoint

ROOT = Path(__file__).resolve().parent
MODEL_CHECKPOINT = find_molscribe_checkpoint(ROOT)
MODEL_DIR = MODEL_CHECKPOINT.parents[2]
OUTPUT_ROOT = ROOT.parent
DIST_DIR = OUTPUT_ROOT / "Clipboard2Smiles"
BUILD_DIR = Path(os.environ.get("TEMP", OUTPUT_ROOT)) / "Clipboard2Smiles-build"

if sys.platform != "win32":
    raise SystemExit("Build the Windows executable on Windows.")

PyInstaller.__main__.run(
    [
        str(ROOT / "clipboard2smiles_windows.py"),
        "--windowed",
        "--onedir",
        "--name=Clipboard2Smiles",
        "--noconfirm",
        "--clean",
        "--distpath",
        str(OUTPUT_ROOT),
        "--workpath",
        str(BUILD_DIR),
        "--specpath",
        str(BUILD_DIR),
        "--collect-all",
        "molscribe",
        "--add-data",
        f"{ROOT / 'pictograms'};pictograms",
        "--add-data",
        f"{MODEL_DIR};models--yujieq--MolScribe",
    ]
)
