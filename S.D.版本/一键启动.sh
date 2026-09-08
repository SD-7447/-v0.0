#!/usr/bin/env bash
# S.D. 智能财务系统 · 一键启动（macOS / Linux）
set -e
cd "$(dirname "$0")"

echo "============================================"
echo "   S.D. 智能财务系统 · Phase 1 · 一键启动"
echo "============================================"

PY=python3
command -v python3 >/dev/null 2>&1 || PY=python
if ! command -v "$PY" >/dev/null 2>&1; then
  echo "[错误] 未检测到 Python，请先安装 Python 3.10+：https://www.python.org/downloads/"
  exit 1
fi

if [ ! -x ".venv/bin/python" ]; then
  echo "[1/3] 首次运行，正在创建虚拟环境 .venv ..."
  "$PY" -m venv .venv
else
  echo "[1/3] 虚拟环境已存在，跳过创建。"
fi

if [ ! -f ".venv/.deps_ok" ]; then
  echo "[2/3] 正在安装依赖 ..."
  ".venv/bin/python" -m pip install -q -r requirements.txt \
    || ".venv/bin/python" -m pip install -q -r requirements.txt -i https://pypi.org/simple
  touch ".venv/.deps_ok"
else
  echo "[2/3] 依赖已就绪，跳过安装。"
fi

echo "[3/3] 正在启动服务，浏览器将自动打开 http://127.0.0.1:8000 ..."
echo ""
".venv/bin/python" run.py
