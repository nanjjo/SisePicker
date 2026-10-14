# -*- mode: python ; coding: utf-8 -*-
# SisePicker PyInstaller spec — 단일 exe 에 Python 런타임 + 모든 라이브러리를 포함한다.
# 빌드:  build.bat   (또는  python -m PyInstaller SisePicker.spec --noconfirm)
from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = [], [], []
datas += [("web_extract.js", "."), ("web_picker.js", "."), ("naver_extract.js", "."), ("naver_picker.js", ".")]
# Web-only v2.0. Pillow remains a python-pptx dependency.
hiddenimports += ["win32com", "win32com.client", "pythoncom", "pywintypes"]

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # 테스트 코드는 별도 파일(test_sisepicker.py)이므로 unittest 를 제외해도 안전하다.
    excludes=['pandas', 'matplotlib', 'scipy', 'pytest', 'unittest', 'torch', 'tensorflow', 'ocr_engine', 'cell_reader', 'rapidocr_onnxruntime', 'onnxruntime', 'cv2', 'numpy', 'shapely', 'pyclipper', 'winocr', 'winsdk', 'winrt'],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='SisePicker',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=None,
)
