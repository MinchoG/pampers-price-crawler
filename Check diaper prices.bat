@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\price-check.exe" goto browser
py -3 -c "import sys; sys.exit(sys.version_info < (3, 11))"
if errorlevel 1 (
    echo Install Python 3.11 or newer with the Python launcher from https://www.python.org/downloads/windows/ and open this file again.
    goto done
)
py -3 -m venv .venv || goto done
".venv\Scripts\python.exe" -m pip install -e . || goto done
:browser
".venv\Scripts\playwright.exe" install chromium || goto done
".venv\Scripts\python.exe" -m pampers_prices.quick_check
:done
pause
