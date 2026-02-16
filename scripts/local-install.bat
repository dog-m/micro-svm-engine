@echo off

cd ..
python -m pip uninstall -y micro-svm
for %%f in (dist\*.whl) do (
    pip install -U "%%f"
    pause
    goto :EOF
)

echo [ERROR] Build the project first!
pause
