@echo off
chcp 65001 >nul 2>&1
title SN管理面板插件后端
cd /d "%~dp0"

set "PYCMD="
where python >nul 2>&1 && set "PYCMD=python"
if not defined PYCMD where python3 >nul 2>&1 && set "PYCMD=python3"
if not defined PYCMD (
    for %%p in (C:\Python312\python.exe C:\Python311\python.exe C:\Python310\python.exe C:\Python39\python.exe "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" "%LOCALAPPDATA%\Programs\Python\Python310\python.exe") do (
        if exist %%p if not defined PYCMD set "PYCMD=%%~p"
    )
)
if not defined PYCMD (
    echo [错误] 未找到 Python，请先安装 Python 3.8+
    pause
    exit /b 1
)

%PYCMD% -m pip install flask playwright -q 2>nul

echo ========================================
echo   SN管理面板插件后端
echo   访问地址: http://localhost
echo ========================================
echo.
echo 启动中，请稍候...
start "" cmd /c "timeout /t 2 /nobreak >nul && start http://localhost"
%PYCMD% server.py
pause
