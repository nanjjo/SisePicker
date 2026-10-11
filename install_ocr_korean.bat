@echo off
rem Install the Windows OCR language pack for Korean (needs admin; asks for UAC).
rem Equivalent GUI path: Settings > Time and language > Language and region >
rem   Korean > Language options > Optical character recognition.
net session >nul 2>&1
if errorlevel 1 (
    echo Requesting administrator rights...
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)
echo Installing Windows OCR pack: Language.OCR~~~ko-KR~0.0.1.0  (internet required, 1-3 minutes)
powershell -NoProfile -Command "Add-WindowsCapability -Online -Name 'Language.OCR~~~ko-KR~0.0.1.0'"
echo.
echo Installed OCR packs:
powershell -NoProfile -Command "Get-WindowsCapability -Online -Name 'Language.OCR*' | Where-Object State -eq 'Installed' | Select-Object -ExpandProperty Name"
echo.
echo Done. Start SisePicker again.
pause
