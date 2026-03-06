@echo off
REM run_pipeline.bat — Windows launcher
REM Double-click this file or run from Command Prompt

echo ============================================
echo   Greenwashing Detection Pipeline - UCL MSIN0166
echo ============================================

REM Activate virtual environment if it exists
IF EXIST ".venv\Scripts\activate.bat" (
    echo Activating virtual environment...
    call .venv\Scripts\activate.bat
) ELSE (
    echo No .venv found - using system Python
)

REM Check Python
python --version

REM Install dependencies
echo Checking dependencies...
pip install -r requirements.txt -q

REM Create output directories
if not exist "data\raw" mkdir data\raw
if not exist "data\processed" mkdir data\processed
if not exist "data\spark-temp" mkdir data\spark-temp

REM Execute notebook
echo Running pipeline notebook...
jupyter nbconvert --to notebook --execute main.ipynb --output main_executed.ipynb --ExecutePreprocessor.timeout=1800

echo.
echo Pipeline complete. Output: main_executed.ipynb
echo ============================================
pause