@echo off

cd ..
del /Q dist
python -m build

pause
