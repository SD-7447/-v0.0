"""端到端流水线：上传 → 识别 → 清洗 → 暂存 → 汇总 → 三表 → 反馈。

每处理一张图片即完整走一遍并向调用方返回最新三表（实时反馈）。
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path

from ..config import settings
from ..db import StagingDB
from ..schemas import InvoiceFields, UploadResult
from .audit import audit
from .recognizer import get_recognizer
from .statements import compile_statements

_ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}


class Pipeline:
    def __init__(self, db: StagingDB | None = None, provider: str | None = None):
        self.db = db or StagingDB(settings.db_path)
        self.recognizer = get_recognizer(provider)

    def statements(self):
        return compile_statements(self.db.all_active())

    def process_upload(self, image_bytes: bytes, file_name: str) -> UploadResult:
        ext = Path(file_name).suffix.lower()
        if ext not in _ALLOWED_EXT:
            return UploadResult(status="failed", message=f"不支持的文件类型 {ext or '(无扩展名)'}，请上传图片")

        file_hash = hashlib.sha256(image_bytes).hexdigest()

        # 识别
        try:
            fields = self.recognizer.recognize(image_bytes, file_name)
        except Exception as exc:  # noqa: BLE001 — 任何识别失败都要给用户明确反馈
            return UploadResult(status="failed", message=f"识别失败：{exc}")

        # 查重（发票代码+号码 / 文件哈希）
        dup = self.db.find_duplicate(file_hash, fields.invoice_code, fields.invoice_number)
        if dup is not None:
            return UploadResult(
                status="duplicate",
                message=f"与历史记录 #{dup.id}（{dup.file_name}）重复，未重复入账",
                record=dup,
                statements=self.statements(),
            )

        # 审计（确定性规则）
        status, notes = audit(fields)

        # 归档原图（留痕）
        saved_name = f"{datetime.now():%Y%m%d_%H%M%S}_{file_hash[:10]}{ext}"
        (settings.upload_dir / saved_name).write_bytes(image_bytes)

        record = self.db.insert(
            status=status, file_name=file_name, file_hash=file_hash,
            fields=fields, audit_notes="；".join(notes),
        )
        statements = self.statements()

        if status == "ok":
            message = f"上传成功：{fields.category or '未分类'} ¥{fields.total_amount or 0:.2f}，三表已实时更新"
        elif status == "review":
            message = f"已入账但需人工复核：{'；'.join(notes)}"
        else:
            message = f"已拒收：{'；'.join(notes)}"
        return UploadResult(
            status="success" if status == "ok" else status,
            message=message, record=record, statements=statements,
        )

    def correct_record(self, record_id: int, updates: dict) -> UploadResult:
        """人工介入窗口：修正字段并回流（corrections 表留痕），随后重算三表。"""
        record = self.db.get(record_id)
        if record is None:
            return UploadResult(status="failed", message=f"记录 #{record_id} 不存在")
        merged = record.fields.to_dict()
        merged.update(updates)
        new_fields = InvoiceFields.from_raw(merged)
        status, notes = audit(new_fields)
        saved = self.db.correct(record_id, new_fields, new_status=status if updates.get("status") is None else updates["status"])
        return UploadResult(
            status="success",
            message=f"记录 #{record_id} 已修正（{'；'.join(notes) or '校验通过'}），三表已重算",
            record=saved, statements=self.statements(),
        )
