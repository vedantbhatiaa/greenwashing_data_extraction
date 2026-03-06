#!/bin/bash
# run_pipeline.sh — Cross-platform launcher (Mac/Linux)
# Windows users: run run_pipeline.bat instead (see below)

#set -e

#echo "============================================"
#echo "  Greenwashing Detection Pipeline — UCL MSIN0166"
#echo "============================================"

# Activate virtual environment if it exists
#if [ -f ".venv/bin/activate" ]; then
#    echo "Activating virtual environment..."
#    source .venv/bin/activate
#elif [ -f ".venv/Scripts/activate" ]; then
#    echo "Activating virtual environment (Git Bash)..."
#    source .venv/Scripts/activate
#else
#    echo "No .venv found — using system Python"
#fi

# Check Python available
#python --version || python3 --version

# Install dependencies if needed
#echo "Checking dependencies..."
#pip install -r requirements.txt -q

# Create output directories
#mkdir -p data/raw data/processed data/spark-temp

# Execute notebook
#echo "Running pipeline notebook..."
#jupyter nbconvert --to notebook --execute main.ipynb \
#    --output main_executed.ipynb \
#    --ExecutePreprocessor.timeout=1800

#echo ""
#echo "✅ Pipeline complete. Output: main_executed.ipynb"
#echo "============================================"