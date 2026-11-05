@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\pythonw.exe" (
    start "RoboAVA Luna" ".venv\Scripts\pythonw.exe" "robo_ava_gui.py"
) else (
    python "robo_ava_gui.py"
)
