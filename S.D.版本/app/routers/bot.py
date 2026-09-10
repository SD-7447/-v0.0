"""微信 ClawBot 通道入口：接收 OpenClaw 转发的票据图片，直接走全链路入账。

对应会议纪要「ClawBot 只做传话筒」：
- OpenClaw 侧不做 AI 分析，收到微信图片原样 POST 到本接口（application/octet-stream）；
- 鉴权：管理后台配置 BOT_TOKEN 后，请求头 X-Bot-Token 必须一致；未配置则放行（仅本机使用时）；
- 入账后返回 {status, reply}，reply 文本由 ClawBot 原样回复到微信；
- 记录来源标记为 wechat，暂存明细中可与网页上传区分。

连接检测（v0.4 连接链路重构）：
- GET /api/bot/status 启动自检：Node 环境 / OpenClaw Gateway 端口探活 / BOT_TOKEN 配置 / 最近一次微信入账；
- GET /api/bot/ping    令牌回环自检（ClawBot 侧脚本可用来验证令牌配对，不产生入账记录）。

请求头约定（见 wechat_bot/ 目录的 OpenClaw 侧脚本）：
  X-Bot-Token: 管理后台配置的 BOT_TOKEN
  X-User:      微信发送者标识（留痕用）
  X-File-Name: 原始文件名（缺省 wechat.jpg）
"""
from __future__ import annotations

import shutil
import socket
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..config import get
from ..db import StagingDB
from ..log import get_logger
from ..services.pipeline import Pipeline

router = APIRouter(prefix="/api/bot", tags=["bot"])

_pipeline: Pipeline | None = None
_db: StagingDB | None = None

GATEWAY_HOST = "127.0.0.1"
GATEWAY_PORT = 18789  # OpenClaw Gateway 默认监听端口


def bind(pipeline: Pipeline, db: Optional[StagingDB] = None) -> None:
    global _pipeline, _db
    _pipeline = pipeline
    _db = db


def handle_bot_upload(data: bytes, *, token: str, user: str, file_name: str) -> tuple[int, dict]:
    """核心逻辑（与 HTTP 层解耦，便于测试）。返回 (http_status, body)。"""
    logger = get_logger()
    expected = get("BOT_TOKEN")
    if expected and token != expected:
        logger.warning("Bot 上传鉴权失败 user=%s", user)
        return 403, {"status": "failed", "reply": "❌ 鉴权失败：BOT_TOKEN 不匹配"}
    if not expected:
        logger.info("BOT_TOKEN 未配置，Bot 上传未鉴权（user=%s）。建议在管理后台配置。", user)
    if _pipeline is None:
        return 500, {"status": "failed", "reply": "❌ 服务未初始化"}
    if not data:
        return 400, {"status": "failed", "reply": "❌ 收到空文件，请重新发送图片"}

    result = _pipeline.process_upload(data, file_name or "wechat.jpg", source="wechat")
    icon = {"success": "✅", "review": "⚠️", "duplicate": "🔁", "failed": "❌"}.get(result.status, "❌")
    logger.info("Bot 上传 user=%s file=%s status=%s", user, file_name, result.status)
    return (200 if result.status != "failed" else 422), {
        "status": result.status,
        "reply": f"{icon} {result.message}",
        "record_id": result.record.id if result.record else None,
    }


@router.post("/upload")
async def bot_upload(request: Request) -> JSONResponse:
    """接收 ClawBot 转发的图片（原始字节流）。"""
    data = await request.body()
    status, body = handle_bot_upload(
        data,
        token=request.headers.get("X-Bot-Token", ""),
        user=request.headers.get("X-User", "wechat"),
        file_name=request.headers.get("X-File-Name", "wechat.jpg"),
    )
    return JSONResponse(body, status_code=status)


# ---------- 连接链路自检（v0.4） ----------

def probe_gateway(host: str = GATEWAY_HOST, port: int = GATEWAY_PORT, timeout: float = 0.8) -> bool:
    """TCP 探活 OpenClaw Gateway（默认 127.0.0.1:18789）。"""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def build_status() -> dict:
    """汇总连接链路各环节状态，供启动自检与连接向导轮询。"""
    node_available = shutil.which("node") is not None
    gateway_reachable = probe_gateway()
    token_configured = bool(get("BOT_TOKEN"))
    last_wechat_at = None
    wechat_count = 0
    if _db is not None:
        info = _db.source_stats("wechat")
        last_wechat_at = info["last_at"]
        wechat_count = info["count"]
    # 判定：Gateway 可达 + 令牌已配置 = 完整连接；未配令牌则降级为「未加密连接」
    connected = gateway_reachable and token_configured
    return {
        "connected": connected,
        "partial": gateway_reachable and not token_configured,
        "steps": {
            "node": node_available,
            "gateway": gateway_reachable,
            "token": token_configured,
        },
        "gateway_addr": f"{GATEWAY_HOST}:{GATEWAY_PORT}",
        "wechat_count": wechat_count,
        "last_wechat_at": last_wechat_at,
        "upload_endpoint": "/api/bot/upload",
    }


@router.get("/status")
def bot_status() -> dict:
    """启动自检：前端据此决定是否弹出连接向导。"""
    return build_status()


def handle_ping(token: str) -> tuple[int, dict]:
    """令牌回环自检核心逻辑（与 HTTP 层解耦，便于测试）。"""
    expected = get("BOT_TOKEN")
    if not expected:
        return 200, {"ok": True, "secured": False, "reply": "✅ 通道可达（未配置令牌，当前不鉴权）"}
    if token == expected:
        return 200, {"ok": True, "secured": True, "reply": "✅ 令牌配对成功，通道已加密"}
    return 403, {"ok": False, "secured": True, "reply": "❌ 令牌不匹配，请核对 SD_BOT_TOKEN"}


@router.get("/ping")
def bot_ping(request: Request) -> JSONResponse:
    """令牌回环自检：ClawBot 侧脚本验证配对，不产生任何入账记录。"""
    status, body = handle_ping(request.headers.get("X-Bot-Token", ""))
    return JSONResponse(body, status_code=status)
