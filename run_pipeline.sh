#!/bin/bash
echo "Starting Greenwashing Detection Pipeline"
echo "Activating environment..."
source .venv/Scripts/activate 2>/dev/null || source .venv/bin/activate 2>/dev/null
echo "Running pipeline notebook..."
jupyter nbconvert --to notebook --execute main.ipynb --output main_executed.ipynb
echo "Pipeline complete."