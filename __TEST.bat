@echo off

set PYTHONPATH=src
python -m unittest discover -s tests

pause
