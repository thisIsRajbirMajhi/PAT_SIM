@echo off
REM Set PYTHONPATH so `python -m fsoc_tracker.main` also works without install
set PYTHONPATH=%~dp0src;%PYTHONPATH%
REM Preferred direct launch (works without PYTHONPATH)
python "%~dp0src\fsoc_tracker\main.py"
if errorlevel 1 (
  echo Trying fallback via module...
  python -m fsoc_tracker.main
)
pause
