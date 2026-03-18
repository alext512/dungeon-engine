@echo off
setlocal

cd /d "%~dp0"

set "PYTHON_EXE="

if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
)

if not defined PYTHON_EXE (
    where py >nul 2>&1
    if not errorlevel 1 (
        echo Creating local virtual environment...
        py -3.11 -m venv .venv
        if errorlevel 1 goto :error
        set "PYTHON_EXE=.venv\Scripts\python.exe"
    ) else (
        where python >nul 2>&1
        if errorlevel 1 (
            echo Python 3.11+ was not found on this machine.
            echo Install Python and then run this launcher again.
            goto :pause
        )
        echo Creating local virtual environment...
        python -m venv .venv
        if errorlevel 1 goto :error
        set "PYTHON_EXE=.venv\Scripts\python.exe"
    )
)

echo Checking dependencies...
"%PYTHON_EXE%" -c "import pygame, puzzle_dungeon" >nul 2>&1
if errorlevel 1 (
    echo Installing dependencies...
    "%PYTHON_EXE%" -m pip install -e .
    if errorlevel 1 goto :error
)

echo Launching Python Puzzle Engine...
"%PYTHON_EXE%" main.py %*
if errorlevel 1 goto :error

goto :end

:error
echo.
echo Launch failed.

:pause
pause

:end
endlocal
