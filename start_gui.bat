@echo off
setlocal EnableExtensions

pushd "%~dp0" >nul || exit /b 1

if exist "TimelapseManager.exe" (
    "TimelapseManager.exe" gui
    goto finished
)

if not exist "timelapse.py" (
    echo Timelapse Manager launcher was not found in:
    echo %CD%
    goto failed
)

set "RUNTIME_CHECKER=%CD%\src\timelapse_manager\runtime_check.py"
if not exist "%RUNTIME_CHECKER%" (
    echo GUI runtime checker was not found:
    echo %RUNTIME_CHECKER%
    goto failed
)

set "GUI_PYTHON="
set "GUI_ENVIRONMENT="

if defined VIRTUAL_ENV if exist "%VIRTUAL_ENV%\Scripts\python.exe" (
    set "GUI_PYTHON=%VIRTUAL_ENV%\Scripts\python.exe"
    set "GUI_ENVIRONMENT=active environment %VIRTUAL_ENV%"
    goto environment_selected
)

if exist ".venv\Scripts\python.exe" (
    set "GUI_PYTHON=%CD%\.venv\Scripts\python.exe"
    set "GUI_ENVIRONMENT=project environment .venv"
    goto environment_selected
)

if exist "venv\Scripts\python.exe" (
    set "GUI_PYTHON=%CD%\venv\Scripts\python.exe"
    set "GUI_ENVIRONMENT=project environment venv"
    goto environment_selected
)

set "BOOTSTRAP_PYTHON="
where py >nul 2>&1
if not errorlevel 1 (
    py -3 -c "import sys; assert sys.version_info.__ge__((3, 10))" >nul 2>&1
    if not errorlevel 1 set "BOOTSTRAP_PYTHON=py"
)

if not defined BOOTSTRAP_PYTHON (
    where python >nul 2>&1
    if not errorlevel 1 (
        python -c "import sys; assert sys.version_info.__ge__((3, 10))" >nul 2>&1
        if not errorlevel 1 set "BOOTSTRAP_PYTHON=python"
    )
)

if not defined BOOTSTRAP_PYTHON (
    echo Python 3.10 or newer was not found.
    goto failed
)

echo Creating project virtual environment: %CD%\.venv
if "%BOOTSTRAP_PYTHON%"=="py" (
    py -3 -m venv ".venv"
) else (
    python -m venv ".venv"
)
if errorlevel 1 (
    echo Failed to create the project virtual environment.
    goto failed
)
set "GUI_PYTHON=%CD%\.venv\Scripts\python.exe"
set "GUI_ENVIRONMENT=new project environment .venv"

:environment_selected
"%GUI_PYTHON%" -c "import sys; assert sys.version_info.__ge__((3, 10))" >nul 2>&1
if errorlevel 1 (
    echo The selected virtual environment does not contain Python 3.10 or newer:
    echo %GUI_PYTHON%
    goto failed
)

echo Using %GUI_ENVIRONMENT%
echo Python: %GUI_PYTHON%

"%GUI_PYTHON%" "%RUNTIME_CHECKER%" packages >nul 2>&1
if errorlevel 1 (
    if not exist "requirements.txt" (
        echo requirements.txt was not found.
        goto failed
    )
    echo Installing missing runtime dependencies into the virtual environment...
    "%GUI_PYTHON%" -m pip install --disable-pip-version-check -r "requirements.txt"
    if errorlevel 1 (
        echo Failed to install runtime dependencies.
        goto failed
    )
    "%GUI_PYTHON%" "%RUNTIME_CHECKER%" packages >nul 2>&1
    if errorlevel 1 (
        echo Runtime dependencies are still unavailable after installation.
        goto failed
    )
)

"%GUI_PYTHON%" "%RUNTIME_CHECKER%" tkinter >nul 2>&1
if errorlevel 1 (
    echo The selected Python does not include a working Tkinter runtime.
    echo Re-run the Python installer, enable "tcl/tk and IDLE", then recreate the virtual environment.
    goto failed
)

"%GUI_PYTHON%" "%RUNTIME_CHECKER%" runtime >nul 2>&1
if errorlevel 1 (
    echo The GUI runtime could not be imported after dependency checks.
    goto failed
)

"%GUI_PYTHON%" timelapse.py gui
goto finished

:finished
set "LAUNCH_EXIT_CODE=%ERRORLEVEL%"
if not "%LAUNCH_EXIT_CODE%"=="0" (
    echo.
    echo Timelapse Manager exited with code %LAUNCH_EXIT_CODE%.
    pause
)
popd >nul
exit /b %LAUNCH_EXIT_CODE%

:failed
echo.
pause
popd >nul
exit /b 1
