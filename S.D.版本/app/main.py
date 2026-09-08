"""Web App 壳子（应用层）：图片接收 · API 调用编排 · 汇总计算 · 实时反馈。

对应会议纪要：
- Web 端只接收图片、不做拍摄（拍摄交给手机微信侧）；
- 每上传一张即返回处理状态 + 最新三表（实时反馈）；
- 提供人工介入窗口接口（复核队列 / 修正回流）。
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .db import StagingDB
from .schemas import FIELD_LABELS
from .services.pipeline import Pipeline

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="AI 中小微企业智能财务系统 · Phase 1（S.D.版本）")
_db = StagingDB(settings.db_path)
_pipeline = Pipeline(db=_db)


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "recognizer": _pipeline.recognizer.name,
        "record_count": len(_db.list_records(limit=10000)),
    }


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)) -> JSONResponse:
    """上传一张票据图片：识别 → 暂存 → 汇总 → 返回最新三表。"""
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="空文件")
    result = _pipeline.process_upload(data, file.filename or "upload.jpg")
    status_code = 200 if result.status != "failed" else 422
    return JSONResponse(result.to_dict(), status_code=status_code)


@app.get("/api/records")
def records(status: str | None = None, limit: int = 200, offset: int = 0) -> dict:
    """暂存明细（历史记录查询，时间倒序）。"""
    rows = _db.list_records(limit=limit, offset=offset, status=status)
    return {"field_labels": FIELD_LABELS, "records": [r.to_dict() for r in rows]}


@app.get("/api/records/{record_id}")
def record_detail(record_id: int) -> dict:
    rec = _db.get(record_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="记录不存在")
    return {"record": rec.to_dict(), "corrections": _db.list_corrections(record_id)}


@app.patch("/api/records/{record_id}")
async def correct_record(record_id: int, updates: dict) -> dict:
    """人工介入窗口：修正字段 → 回流留痕 → 重算三表。"""
    result = _pipeline.correct_record(record_id, updates)
    if result.status == "failed":
        raise HTTPException(status_code=404, detail=result.message)
    return result.to_dict()


@app.get("/api/review")
def review_queue() -> dict:
    """人工复核队列（低置信度 / 勾稽异常 / 科目缺失的记录）。"""
    rows = _db.list_records(limit=500, status="review")
    return {"count": len(rows), "records": [r.to_dict() for r in rows]}


@app.get("/api/statements")
def statements() -> dict:
    """当前三大报表（每次调用实时重算）。"""
    return _pipeline.statements().to_dict()


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
