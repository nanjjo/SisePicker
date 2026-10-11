"""앱 기준 경로 — config/로그는 전부 이 폴더를 기준으로 잡는다.

PyInstaller 단일 파일 exe 는 __file__ 이 임시 해제 폴더(_MEIxxxx)를 가리키므로
frozen 이면 exe 가 있는 폴더를, 아니면 소스 폴더를 돌려준다.
"""
import os
import sys


def app_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))
