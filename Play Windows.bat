@echo off
setlocal
if exist "%~dp0.venv\Scripts\python.exe" (
    "%~dp0.venv\Scripts\python.exe" "%~dp0launch_game.py" %*
    goto finished
)
where py >nul 2>nul
if not errorlevel 1 (
    for %%V in (3.11 3.12 3.10 3.9) do (
        py -%%V -c "import sys" >nul 2>nul
        if not errorlevel 1 (
            py -%%V "%~dp0launch_game.py" %*
            goto finished
        )
    )
)
python "%~dp0launch_game.py" %*
:finished
set result=%ERRORLEVEL%
if not "%result%"=="0" (
    echo.
    echo Install 64-bit Python 3.11 from https://www.python.org/downloads/ if Python was not found.
    pause
)
exit /b %result%
