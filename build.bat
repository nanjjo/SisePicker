@echo off
setlocal
cd /d "%~dp0"
if errorlevel 1 exit /b 1
rem Build PC: Python 3.12 x64. Target PC: no Python installation needed.
if not exist ".venv\Scripts\python.exe" (
    python -m venv --system-site-packages .venv
    if errorlevel 1 exit /b 1
)
set "BUILD_PY=%~dp0.venv\Scripts\python.exe"
"%BUILD_PY%" -m pip install --disable-pip-version-check -r requirements-build.txt
if errorlevel 1 exit /b 1
"%BUILD_PY%" -m unittest test_sisepicker test_workflow_changes test_naver_import test_web_gui -q
if errorlevel 1 exit /b 1
where node >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Node.js is required on the build PC for JavaScript checks.
    exit /b 1
)
node tests\test_web_extract.cjs
if errorlevel 1 exit /b 1
node tests\test_naver_extract.cjs
if errorlevel 1 exit /b 1
"%BUILD_PY%" -m PyInstaller SisePicker.spec --noconfirm --distpath dist --workpath build\windows
if errorlevel 1 exit /b 1
start "" /wait "%~dp0dist\SisePicker.exe" --smoke-test "%~dp0build\packaged-smoke.json"
if errorlevel 1 exit /b 1
echo Build complete: dist\SisePicker.exe
exit /b 0
