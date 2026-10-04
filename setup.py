from setuptools import setup
import sys
from pathlib import Path

sys.setrecursionlimit(5000)

ROOT = Path(__file__).resolve().parent
APP = ['clipboard2smiles.py']
DATA_FILES = ['smiles.csv', 'pictograms', 'image_generated',
              'image_output', 'image_queue', 'models--yujieq--MolScribe']
OPTIONS = {
    'argv_emulation': True,
    'plist': {'LSUIElement': True}, 
    'packages': ['rumps', 'certifi', 'requests'],
    'iconfile': str(ROOT / 'pictograms' / 'carlos_helper_logo.icns')}

setup(
    app=APP,
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)