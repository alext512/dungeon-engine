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
        echo Creating local editor environment...
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
        echo Creating local editor environment...
        python -m venv .venv
        if errorlevel 1 goto :error
        set "PYTHON_EXE=.venv\Scripts\python.exe"
    )
)

echo Checking editor dependencies...
"%PYTHON_EXE%" -c "import PySide6, area_editor" >nul 2>&1
if errorlevel 1 (
    echo Installing editor dependencies...
    "%PYTHON_EXE%" -m pip install -r requirements.txt
    if errorlevel 1 goto :error
)

echo Launching Editor...
"%PYTHON_EXE%" -m area_editor %*
if errorlevel 1 goto :error

goto :end

:error
echo.
echo Launch failed.

:pause
pause

:end
endlocal
