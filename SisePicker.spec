# -*- mode: python ; coding: utf-8 -*-
# SisePicker PyInstaller spec — 단일 exe 에 Python 런타임 + 모든 라이브러리를 포함한다.
# 빌드:  build.bat   (또는  python -m PyInstaller SisePicker.spec --noconfirm)
from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = [], [], []
datas += [("web_extract.js", "."), ("web_picker.js", "."), ("naver_extract.js", "."), ("naver_picker.js", ".")]
# winocr 는 Windows 런타임 바인딩(winsdk 또는 winrt-*)을 지연 import 하므로 통째로 수집한다.
# RapidOCR(숫자 인식) 계열: onnxruntime + PaddleOCR onnx 모델(패키지 안 models/) + opencv + shapely/pyclipper
for pkg in ("winocr", "winsdk", "winrt", "pptx", "lxml", "PIL",
            "rapidocr_onnxruntime", "onnxruntime", "cv2", "shapely", "pyclipper", "yaml", "numpy"):
    try:
        d, b, h = collect_all(pkg)
    except Exception:
        continue
    datas += d
    binaries += b
    hiddenimports += h
# RapidOCR 한국어 인식 모델 (download_korean_model.py 로 받아 둔 경우에만 포함 → exe 에서 단지명 인식에 사용)
import glob as _glob
_ko_models = [f for f in _glob.glob("models/*") if f.endswith((".onnx", ".txt"))]
if _ko_models:
    datas += [(f, "models") for f in _ko_models]
hiddenimports += ["PIL.ImageGrab", "PIL.ImageTk", "PIL._tkinter_finder",
                  "win32com", "win32com.client", "pythoncom", "pywintypes"]   # 열려 있는 PowerPoint 에 COM 으로 추가

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
    excludes=['pandas', 'matplotlib', 'scipy', 'pytest', 'unittest', 'torch', 'tensorflow'],
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
