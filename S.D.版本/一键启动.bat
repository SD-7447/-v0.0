@echo off
chcp 65001 >nul
title S.D. 智能财务系统 · 一键启动
cd /d "%~dp0"

echo ============================================
echo    S.D. 智能财务系统 · Phase 1 · 一键启动
echo ============================================
echo.

REM ---------- 1. 检查 Python ----------
where python >nul 2>nul
if errorlevel 1 (
    echo [错误] 未检测到 Python。
    echo        请先安装 Python 3.10 或更高版本（安装时勾选 Add to PATH）：
    echo        https://www.python.org/downloads/
    echo.
    start https://www.python.org/downloads/
    pause
    exit /b 1
)

REM ---------- 2. 创建虚拟环境（仅首次） ----------
if not exist ".venv\Scripts\python.exe" (
    echo [1/3] 首次运行，正在创建虚拟环境 .venv ...
    python -m venv .venv
    if errorlevel 1 (
        echo [错误] 虚拟环境创建失败，请确认 Python 安装完整。
        pause
        exit /b 1
    )
) else (
    echo [1/3] 虚拟环境已存在，跳过创建。
)

REM ---------- 3. 安装依赖（仅首次；requirements.txt 更新后删除 .venv\.deps_ok 重装） ----------
if not exist ".venv\.deps_ok" (
    echo [2/3] 正在安装依赖（优先使用清华镜像）...
    ".venv\Scripts\python.exe" -m pip install -q -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
    if errorlevel 1 (
        echo       镜像源失败，改用官方源重试...
        ".venv\Scripts\python.exe" -m pip install -q -r requirements.txt
        if errorlevel 1 (
            echo [错误] 依赖安装失败，请检查网络后重试。
            pause
            exit /b 1
        )
    )
    echo ok>".venv\.deps_ok"
) else (
    echo [2/3] 依赖已就绪，跳过安装。
)

REM ---------- 4. 启动 ----------
echo [3/3] 正在启动服务，浏览器将自动打开 http://127.0.0.1:8000 ...
echo.
".venv\Scripts\python.exe" run.py

echo.
echo 服务已停止。
pause
