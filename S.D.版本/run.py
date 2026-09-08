"""本地启动入口：启动服务并自动打开浏览器。

    python run.py            # 默认 http://127.0.0.1:8000
    python run.py --port 9000
"""
from __future__ import annotations

import argparse
import socket
import threading
import time
import webbrowser

import uvicorn


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def _open_browser_when_ready(url: str, port: int, timeout: float = 15.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                webbrowser.open(url)
                return
        time.sleep(0.3)


def main() -> None:
    parser = argparse.ArgumentParser(description="S.D. 智能财务系统 · Phase 1")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    args = parser.parse_args()

    if not _port_free(args.port):
        print(f"⚠️  端口 {args.port} 已被占用（可能是系统已在运行）。")
        print(f"    直接访问 http://127.0.0.1:{args.port} 或换端口：python run.py --port {args.port + 1}")
        raise SystemExit(1)

    url = f"http://127.0.0.1:{args.port}"
    print("=" * 46)
    print("  S.D. 智能财务系统 · Phase 1")
    print(f"  地址: {url}")
    print("  停止: 按 Ctrl + C")
    print("=" * 46)

    if not args.no_browser:
        threading.Thread(target=_open_browser_when_ready, args=(url, args.port), daemon=True).start()

    uvicorn.run("app.main:app", host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
