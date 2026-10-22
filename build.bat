@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
    py -3.12 -m venv .venv
    if errorlevel 1 goto :failed
)
echo Installing build dependencies...
.venv\Scripts\python.exe -m pip install -r requirements-build.txt
if errorlevel 1 goto :failed
.venv\Scripts\python.exe -m unittest discover -s tests -v
if errorlevel 1 goto :failed
.venv\Scripts\python.exe -m PyInstaller build.spec --clean --noconfirm
if errorlevel 1 goto :failed
echo.
echo Done. Open dist\SpeedEditorCustomizer\SpeedEditorCustomizer.exe
echo Keep the entire folder, including _internal.
pause
exit /b 0
:failed
echo Build failed. See the error above. Python 3.12 is required for building.
pause
exit /b 1
