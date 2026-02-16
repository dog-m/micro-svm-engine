@echo off

cd ..
set PYTHONPATH=src
python -m unittest discover -s tests

pause
