@echo off
setlocal
set BUILD_VENV=build\build_standalone_build_env


REM Default Python path
set "PYTHON_EXEC_PATH=py"

REM Parse command line arguments
:parse_args
if "%~1"=="" goto end_args
if "%~1"=="--base-python-path" (
    set "PYTHON_EXEC_PATH=%~2"
    shift
    shift
    goto parse_args
)
if "%~1"=="--venv-path" (
    set "BUILD_VENV=%~2"
    shift
    shift
    goto parse_args
)
set "REMAINING_ARGS=%REMAINING_ARGS% "%~1""
shift
goto parse_args

goto:end_args

:create_venv
    %PYTHON_EXEC_PATH% -m venv %BUILD_VENV%
    %BUILD_VENV%\Scripts\python -m pip install pip --upgrade
    %BUILD_VENV%\Scripts\python -m pip install -r %~dp0\requirements.txt
    goto :eof

:create_standalone
     set PYTHONPATH=%~dp0
     %BUILD_VENV%\Scripts\python -m package_speedwagon %REMAINING_ARGS%
     if %ERRORLEVEL% NEQ 0 exit /B %ERRORLEVEL%
     goto :eof

:end_args
REM Output the Python path being used
echo Using Python path: %PYTHON_EXEC_PATH%

REM Example of running a Python script with the specified Python path
call :create_venv
call :create_standalone
endlocal