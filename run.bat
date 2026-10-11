@echo off
rem 소스로 바로 실행 (Python 설치 PC 용). 처음엔 pip install -r requirements.txt 필요.
cd /d "%~dp0"
start "" pythonw main.py
