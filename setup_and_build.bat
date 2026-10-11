@echo off
rem ============================================================
rem  SisePicker one-click setup:
rem    1) install Python 3.12 (user scope, no admin) if missing
rem    2) pip install requirements
rem    3) build dist\SisePicker.exe with PyInstaller
rem  Double-click this file. Needs internet for step 1/2 only.
rem  The window stays open when finished (cmd /k) and everything
rem  is also written to setup_log.txt next to this file.
rem ============================================================
if "%~1"=="" (
    cd /d "%~dp0"
    echo ==== %date% %time% setup_and_build start ==== >> "%~dp0setup_log.txt"
    cmd /k ""%~f0" run"
    exit /b
)

cd /d "%~dp0"
set "LOG=%~dp0setup_log.txt"
set "PYVER=3.12.10"
set "PYDIR=%LOCALAPPDATA%\Programs\Python\Python312"
set "PY="

echo ============================================
echo  SisePicker setup + build
echo  log: %LOG%
echo ============================================
echo.

rem ---- 1. find an existing python ----
if exist "%PYDIR%\python.exe" set "PY=%PYDIR%\python.exe"
if not defined PY (
    py -3 -c "import sys" >nul 2>&1
    if not errorlevel 1 set "PY=py -3"
)
if not defined PY (
    python -c "import sys" >nul 2>&1
    if not errorlevel 1 set "PY=python"
)
if defined PY (
    echo [INFO] Python found: %PY%
    echo [INFO] Python found: %PY% >> "%LOG%"
    %PY% --version
    goto :deps
)

rem ---- 2. install python ----
echo [INFO] Python not found. Installing Python %PYVER% for current user...
echo [INFO] Python not found, installing >> "%LOG%"
set "INSTALLER=%TEMP%\python-%PYVER%-amd64.exe"

set "PYURL=https://www.python.org/ftp/python/%PYVER%/python-%PYVER%-amd64.exe"
echo [INFO] Downloading from python.org - about 25 MB...
echo [INFO] downloading %PYURL% >> "%LOG%"
if exist "%INSTALLER%" del /f /q "%INSTALLER%"
where curl >nul 2>&1
if not errorlevel 1 (
    curl -L -# -o "%INSTALLER%" "%PYURL%"
) else (
    echo [INFO] curl not available, using PowerShell...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol='Tls12'; Invoke-WebRequest -Uri '%PYURL%' -OutFile '%INSTALLER%'"
)
if not exist "%INSTALLER%" (
    echo [ERROR] Download failed. >> "%LOG%"
    echo [ERROR] Download failed. Check the internet connection, or install Python manually from
    echo         https://www.python.org/downloads/  - tick "Add python.exe to PATH" -
    echo         then run build.bat.
    goto :fail
)
for %%A in ("%INSTALLER%") do echo [INFO] downloaded %%~zA bytes >> "%LOG%"
echo [INFO] Running installer silently (1-2 minutes, no window appears)...
"%INSTALLER%" /quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_test=0 Include_tcltk=1
set "RC=%errorlevel%"
echo [INFO] installer exit code %RC% >> "%LOG%"
if not "%RC%"=="0" (
    echo [ERROR] Python installer returned code %RC%.
    goto :fail
)
del /f /q "%INSTALLER%" >nul 2>&1
if not exist "%PYDIR%\python.exe" (
    echo [ERROR] python.exe not found at %PYDIR% after install. >> "%LOG%"
    echo [ERROR] python.exe not found at %PYDIR% after install.
    goto :fail
)
set "PY=%PYDIR%\python.exe"
echo [INFO] Python installed: %PY%
echo [INFO] Python installed: %PY% >> "%LOG%"
"%PY%" --version
set "PATH=%PYDIR%;%PYDIR%\Scripts;%PATH%"

:deps
echo.
echo [INFO] Installing dependencies (winocr, python-pptx, Pillow, PyInstaller)...
%PY% -m pip install --upgrade pip --quiet
%PY% -m pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo [ERROR] pip install failed. >> "%LOG%"
    echo [ERROR] pip install failed. Check the internet connection and retry.
    goto :fail
)
echo [INFO] dependencies installed >> "%LOG%"

echo.
echo [INFO] Running unit tests...
%PY% -m unittest test_sisepicker
if errorlevel 1 (
    echo [WARN] Some tests failed. Continuing with the build anyway.
    echo [WARN] tests failed >> "%LOG%"
)

echo.
echo [INFO] Building exe (2-5 minutes)...
if exist dist\SisePicker.exe del /f /q dist\SisePicker.exe
if exist build\SisePicker rmdir /s /q build\SisePicker
%PY% -m PyInstaller SisePicker.spec --noconfirm
if errorlevel 1 (
    echo [ERROR] PyInstaller build failed. >> "%LOG%"
    echo [ERROR] Build failed. See messages above.
    goto :fail
)

echo.
echo ============================================
echo  DONE: %~dp0dist\SisePicker.exe
echo ============================================
for %%A in (dist\SisePicker.exe) do echo  Size: %%~zA bytes
for %%A in (dist\SisePicker.exe) do echo [INFO] DONE dist\SisePicker.exe %%~zA bytes >> "%LOG%"
echo.
echo  Copy dist\SisePicker.exe to any PC (no Python needed).
echo  Each PC needs the Windows Korean language pack for OCR.
echo  You can close this window now.
exit /b 0

:fail
echo.
echo  FAILED. Send setup_log.txt (or a screenshot of this window) to Claude.
exit /b 1
