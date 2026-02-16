@echo off

cd ..
del /Q "dist"
del /Q "src/micro_svm.egg-info"
python -m build

pause
