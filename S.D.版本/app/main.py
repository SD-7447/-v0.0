"""Web App 壳子 v2（应用层）：图片接收 · API 调用编排 · 汇总计算 · 实时反馈 · 管理后台。

对应会议纪要：
- Web 端只接收图片、不做拍摄（拍摄交给手机微信侧）；
- 每上传一张即返回处理状态 + 最新三表（实时反馈）；
- 提供人工介入窗口接口（复核队列 / 修正回流）。
v2 新增：管理后台路由（/api/admin/*）、暂存表导出（/api/records/export）。
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .db import StagingDB
from .routers import admin, bot
from .schemas import FIELD_LABELS
from .services.exporter import export_csv, export_xlsx
from .services.pipeline import Pipeline

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="AI 中小微企业智能财务系统 · Phase 1（S.D.版本 v0.4）")
_db = StagingDB(get_settings().db_path)
_pipeline = Pipeline(db=_db)
admin.bind(_db)
bot.bind(_pipeline, _db)
app.include_router(admin.router)
app.include_router(bot.router)


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "recognizer": _pipeline_recognizer_name(),
        "record_count": _db.stats()["records"]["total"],
    }


def _pipeline_recognizer_name() -> str:
    from .services.recognizer import get_recognizer
    return get_recognizer().name


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


@app.get("/api/records/export")
def records_export(format: str = "xlsx") -> Response:
    """导出暂存表（G-07）：format=xlsx | csv。"""
    if format == "csv":
        return Response(export_csv(_db), media_type="text/csv",
                        headers={"Content-Disposition": "attachment; filename=records.csv"})
    if format == "xlsx":
        return Response(export_xlsx(_db), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": "attachment; filename=records.xlsx"})
    raise HTTPException(status_code=400, detail="format 须为 xlsx 或 csv")


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
    """人工复核队列（低置信度 / 勾稽异常 / 科目缺失等记录）。"""
    rows = _db.list_records(limit=500, status="review")
    return {"count": len(rows), "records": [r.to_dict() for r in rows]}


@app.get("/api/statements")
def statements() -> dict:
    """当前三大报表（每次调用实时重算）。"""
    return _pipeline.statements().to_dict()


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/admin")
def admin_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "admin.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
