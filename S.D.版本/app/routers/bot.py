"""微信 ClawBot 通道入口：接收 OpenClaw 转发的票据图片，直接走全链路入账。

对应会议纪要「ClawBot 只做传话筒」：
- OpenClaw 侧不做 AI 分析，收到微信图片原样 POST 到本接口（application/octet-stream）；
- 鉴权：管理后台配置 BOT_TOKEN 后，请求头 X-Bot-Token 必须一致；未配置则放行（仅本机使用时）；
- 入账后返回 {status, reply}，reply 文本由 ClawBot 原样回复到微信；
- 记录来源标记为 wechat，暂存明细中可与网页上传区分。

请求头约定（见 wechat_bot/ 目录的 OpenClaw 侧脚本）：
  X-Bot-Token: 管理后台配置的 BOT_TOKEN
  X-User:      微信发送者标识（留痕用）
  X-File-Name: 原始文件名（缺省 wechat.jpg）
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..config import get
from ..log import get_logger
from ..services.pipeline import Pipeline

router = APIRouter(prefix="/api/bot", tags=["bot"])

_pipeline: Pipeline | None = None


def bind(pipeline: Pipeline) -> None:
    global _pipeline
    _pipeline = pipeline


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
