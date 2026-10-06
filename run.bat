@echo off

if "%1"=="test" (
    python -m unittest discover -s tests -v
    exit /b %errorlevel%
)

python -m src.main %* 
