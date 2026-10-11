"""SisePicker 진입점 — 캡쳐 이미지 OCR → 시세 텍스트 → 클립보드/PPT.

실행:  python main.py   또는   dist\\SisePicker.exe
로그:  <앱 폴더>\\logs\\SisePicker.log
"""
import logging
import os
import sys
from logging.handlers import RotatingFileHandler

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app_paths import app_dir  # noqa: E402


def _setup_logging() -> None:
    log_dir = os.path.join(app_dir(), "logs")
    handlers: list[logging.Handler] = []
    try:
        os.makedirs(log_dir, exist_ok=True)
        handlers.append(RotatingFileHandler(
            os.path.join(log_dir, "SisePicker.log"), maxBytes=1_000_000,
            backupCount=3, encoding="utf-8"))
    except OSError:
        pass
    if sys.stderr is not None:  # windowed exe 에서는 None
        handlers.append(logging.StreamHandler())
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        handlers=handlers)


def main() -> int:
    if len(sys.argv)==3 and sys.argv[1]=="--smoke-test":
        from smoke_test import smoke_test
        return smoke_test(sys.argv[2])
    _setup_logging()
    logging.getLogger("SisePicker").info("시작 (frozen=%s)", getattr(sys, "frozen", False))
    from gui_app import run
    run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
