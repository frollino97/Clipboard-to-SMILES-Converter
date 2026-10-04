@echo off
setlocal
title Clipboard2Smiles
cd /d "%~dp0"

set "CONDA_EXE="
for /f "delims=" %%C in ('where conda.exe 2^>nul') do if not defined CONDA_EXE set "CONDA_EXE=%%C"

if not defined CONDA_EXE if exist "%LOCALAPPDATA%\miniconda3\Scripts\conda.exe" set "CONDA_EXE=%LOCALAPPDATA%\miniconda3\Scripts\conda.exe"
if not defined CONDA_EXE if exist "%USERPROFILE%\miniconda3\Scripts\conda.exe" set "CONDA_EXE=%USERPROFILE%\miniconda3\Scripts\conda.exe"
if not defined CONDA_EXE if exist "%USERPROFILE%\anaconda3\Scripts\conda.exe" set "CONDA_EXE=%USERPROFILE%\anaconda3\Scripts\conda.exe"
if not defined CONDA_EXE if exist "%ProgramData%\miniconda3\Scripts\conda.exe" set "CONDA_EXE=%ProgramData%\miniconda3\Scripts\conda.exe"
if not defined CONDA_EXE if exist "%ProgramData%\anaconda3\Scripts\conda.exe" set "CONDA_EXE=%ProgramData%\anaconda3\Scripts\conda.exe"

if not defined CONDA_EXE (
    echo Could not find Conda. Install Miniconda/Anaconda or add conda to PATH.
    pause
    exit /b 1
)

if not exist "%LOCALAPPDATA%\Clipboard2Smiles" mkdir "%LOCALAPPDATA%\Clipboard2Smiles"
set "LOG_FILE=%LOCALAPPDATA%\Clipboard2Smiles\launcher.log"
echo.>> "%LOG_FILE%"
echo ===== Starting Clipboard2Smiles: %date% %time% =====>> "%LOG_FILE%"

echo Starting Clipboard2Smiles. MolScribe may take a minute to load; its tray icon appears when ready.
"%CONDA_EXE%" run --no-capture-output --name clipboard2smiles python "%~dp0clipboard2smiles_windows.py" >> "%LOG_FILE%" 2>&1
set "APP_EXIT_CODE=%ERRORLEVEL%"

if errorlevel 1 (
    echo.
    echo Clipboard2Smiles failed to start. Details from this launch:
    type "%LOG_FILE%"
    pause
    exit /b %APP_EXIT_CODE%
)

echo.
echo Clipboard2Smiles exited. See "%LOG_FILE%" for details.
pause
endlocal
