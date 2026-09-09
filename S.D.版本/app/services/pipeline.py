"""端到端流水线 v2：上传 → 识别 → 清洗 → 暂存 → 汇总 → 三表 → 反馈。

v2 变更：
- 识别端口每次上传实时解析（管理后台改 key/换端口免重启）；
- 每次识别调用写入 api_usage 台账（token 用量 / 延迟 / 成败 / 重试次数）；
- 关键事件写操作日志（G-09）；
- 并发写库加锁（G-08 前置）。
"""
from __future__ import annotations

import hashlib
import threading
from datetime import datetime
from pathlib import Path

from ..config import get_settings
from ..db import StagingDB
from ..log import get_logger
from ..schemas import InvoiceFields, UploadResult
from .audit import audit
from .recognizer import get_recognizer
from .statements import compile_statements

_ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}


class Pipeline:
    def __init__(self, db: StagingDB | None = None, provider: str | None = None):
        self.db = db or StagingDB(get_settings().db_path)
        self._provider = provider       # None = 跟随配置实时切换
        self._lock = threading.Lock()

    def statements(self):
        return compile_statements(self.db.all_active())

    def _mean_amount(self) -> float:
        """历史有效记录的平均价税合计（审计 R9 异常值规则的上下文）。"""
        amounts = [
            r.fields.total_amount for r in self.db.all_active()
            if r.fields.total_amount is not None
        ]
        return sum(amounts) / len(amounts) if amounts else 0.0

    def process_upload(self, image_bytes: bytes, file_name: str) -> UploadResult:
        logger = get_logger()
        ext = Path(file_name).suffix.lower()
        if ext not in _ALLOWED_EXT:
            return UploadResult(status="failed", message=f"不支持的文件类型 {ext or '(无扩展名)'}，请上传图片")

        file_hash = hashlib.sha256(image_bytes).hexdigest()
        recognizer = get_recognizer(self._provider)

        # 识别（含重试与用量追踪）
        try:
            fields = recognizer.recognize(image_bytes, file_name)
        except Exception as exc:  # noqa: BLE001 — 任何识别失败都要给用户明确反馈
            self.db.log_usage(recognizer.last_usage.to_dict())
            logger.warning("识别失败 provider=%s file=%s error=%s", recognizer.name, file_name, exc)
            return UploadResult(status="failed", message=f"识别失败（已重试 {recognizer.last_usage.attempts} 次）：{exc}")
        finally:
            if recognizer.last_usage.success:
                self.db.log_usage(recognizer.last_usage.to_dict())

        # 查重（发票代码+号码 / 文件哈希）+ 审计 + 入库，串行保证一致性（G-08）
        with self._lock:
            dup = self.db.find_duplicate(file_hash, fields.invoice_code, fields.invoice_number)
            if dup is not None:
                logger.info("重复上传拦截 file=%s 与记录 #%s 重复", file_name, dup.id)
                return UploadResult(
                    status="duplicate",
                    message=f"与历史记录 #{dup.id}（{dup.file_name}）重复，未重复入账",
                    record=dup,
                    statements=self.statements(),
                )

            status, notes = audit(fields, context={"mean_amount": self._mean_amount()})

            # 归档原图（留痕）
            saved_name = f"{datetime.now():%Y%m%d_%H%M%S}_{file_hash[:10]}{ext}"
            (get_settings().upload_dir / saved_name).write_bytes(image_bytes)

            record = self.db.insert(
                status=status, file_name=file_name, file_hash=file_hash,
                fields=fields, audit_notes="；".join(notes),
            )
            statements = self.statements()

        logger.info(
            "入账 file=%s provider=%s status=%s category=%s total=%s latency=%dms",
            file_name, recognizer.name, status, fields.category, fields.total_amount,
            recognizer.last_usage.latency_ms,
        )

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
        status, notes = audit(new_fields, context={"mean_amount": self._mean_amount()})
        with self._lock:
            saved = self.db.correct(record_id, new_fields, new_status=status if updates.get("status") is None else updates["status"])
            statements = self.statements()
        get_logger().info("人工修正 record=%s keys=%s", record_id, ",".join(updates.keys()))
        return UploadResult(
            status="success",
            message=f"记录 #{record_id} 已修正（{'；'.join(notes) or '校验通过'}），三表已重算",
            record=saved, statements=statements,
        )
