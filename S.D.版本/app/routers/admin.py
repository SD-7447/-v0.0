"""管理后台 API：API KEY 更换、token 检测、用量统计、系统状态、日志查看。

安全说明：
- 配置读取一律返回掩码值（sk-****…****），完整密钥永不出接口；
- 可修改键受 config.EDITABLE_KEYS 白名单约束；
- 所有数据仅存本机 data/ 目录。
"""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from .. import config as cfg
from ..db import StagingDB
from ..log import read_recent_logs
from ..services.recognizer import get_recognizer, test_provider

VERSION = "0.2.0"

router = APIRouter(prefix="/api/admin", tags=["admin"])

_db: StagingDB | None = None


def bind(db: StagingDB) -> None:
    global _db
    _db = db


def _require_db() -> StagingDB:
    if _db is None:
        raise HTTPException(status_code=500, detail="后台未初始化")
    return _db


@router.get("/config")
def get_config() -> dict:
    """当前生效配置（密钥掩码）+ 覆盖层状态。"""
    overrides = cfg._read_overrides()
    keys = sorted(cfg.EDITABLE_KEYS)
    return {
        "config": {k: cfg.masked(k) for k in keys},
        "overridden": [k for k in keys if k in overrides],
        "active_recognizer": get_recognizer().name,
    }


@router.put("/config")
async def put_config(patch: dict) -> dict:
    """更换配置（空字符串 = 清除覆盖回退默认）。改后立即生效，无需重启。"""
    try:
        cfg.update_overrides(patch)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "active_recognizer": get_recognizer().name, "config": get_config()["config"]}


@router.post("/test-provider")
async def test_provider_api(body: dict) -> dict:
    """Token/密钥检测：对指定端口发起真实 /models 调用。"""
    provider = str(body.get("provider", "")).lower()
    if provider not in ("qwen", "deepseek", "mock"):
        raise HTTPException(status_code=400, detail="provider 须为 qwen / deepseek / mock")
    return test_provider(provider)


@router.get("/usage")
def usage(days: int = 30) -> dict:
    """Token 用量台账：按端口聚合 + 最近 20 次调用明细。"""
    return _require_db().usage_stats(days=min(max(days, 1), 365))


@router.get("/stats")
def stats() -> dict:
    """系统概览：记录数、复核数、修正数、存储占用、版本。"""
    db = _require_db()
    s = get_settings = cfg.get_settings()
    upload_size = sum(f.stat().st_size for f in s.upload_dir.glob("*") if f.is_file())
    db_size = s.db_path.stat().st_size if s.db_path.exists() else 0
    return {
        "version": VERSION,
        "python": sys.version.split()[0],
        "active_recognizer": get_recognizer().name,
        **db.stats(),
        "storage": {"upload_bytes": upload_size, "db_bytes": db_size},
        "paths": {"db": str(s.db_path), "uploads": str(s.upload_dir)},
    }


@router.get("/logs")
def logs(lines: int = 100) -> dict:
    """最近操作日志（倒序返回）。"""
    recent = read_recent_logs(min(max(lines, 1), 500))
    return {"count": len(recent), "lines": list(reversed(recent))}


@router.delete("/data/records")
def clear_records(confirm: str = "") -> JSONResponse:
    """清空暂存表（高危操作，需 confirm=清空 确认）。原图归档不删除。"""
    if confirm != "清空":
        raise HTTPException(status_code=400, detail="高危操作：请传 confirm=清空 以确认")
    db = _require_db()
    db.conn.execute("DELETE FROM records")
    db.conn.commit()
    return JSONResponse({"ok": True, "message": "暂存表已清空（原图归档保留在 data/uploads）"})
