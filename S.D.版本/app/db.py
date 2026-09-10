"""暂存表（SQLite）：逐张留痕、时间序、历史查询、发票代码+号码查重、人工修正回流。

对应会议纪要：
- 「暂存表不可跳步」：识别结果先入暂存库留痕，再汇总编表；
- 每张图片一行记录，承担缓存、历史记录与数据追溯功能；
- 查重：发票代码+号码唯一索引；无号码时退化到文件哈希查重。
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .schemas import InvoiceFields, Record

SCHEMA = """
CREATE TABLE IF NOT EXISTS records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    status TEXT NOT NULL DEFAULT 'ok',          -- ok / review / rejected
    file_name TEXT NOT NULL,
    file_hash TEXT NOT NULL,
    invoice_code TEXT NOT NULL DEFAULT '',
    invoice_number TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT '',
    total_amount REAL,
    fields_json TEXT NOT NULL,                  -- 完整 InvoiceFields JSON（含 remarks 追溯信息）
    audit_notes TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT 'web',         -- 来源：web（网页上传）/ wechat（微信 ClawBot）
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_records_invoice_no
    ON records(invoice_code, invoice_number)
    WHERE invoice_number != '';
CREATE INDEX IF NOT EXISTS idx_records_created ON records(created_at);

CREATE TABLE IF NOT EXISTS corrections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id INTEGER NOT NULL REFERENCES records(id),
    before_json TEXT NOT NULL,
    after_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS api_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    model TEXT NOT NULL DEFAULT '',
    operation TEXT NOT NULL DEFAULT 'recognize',
    prompt_tokens INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    latency_ms INTEGER NOT NULL DEFAULT 0,
    success INTEGER NOT NULL DEFAULT 0,
    error TEXT NOT NULL DEFAULT '',
    attempts INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_usage_created ON api_usage(created_at);
"""


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


class StagingDB:
    def __init__(self, db_path: Path | str):
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self._migrate()
        self.conn.commit()

    def _migrate(self) -> None:
        """老库升级：v0.1 的 records 表没有 source 列，补上（幂等）。"""
        cols = {r["name"] for r in self.conn.execute("PRAGMA table_info(records)").fetchall()}
        if "source" not in cols:
            self.conn.execute("ALTER TABLE records ADD COLUMN source TEXT NOT NULL DEFAULT 'web'")

    def close(self) -> None:
        self.conn.close()

    # ---- 查重 ----
    def find_duplicate(self, file_hash: str, invoice_code: str, invoice_number: str) -> Optional[Record]:
        if invoice_number:
            row = self.conn.execute(
                "SELECT * FROM records WHERE invoice_code=? AND invoice_number=?",
                (invoice_code, invoice_number),
            ).fetchone()
            if row:
                return self._to_record(row)
        row = self.conn.execute("SELECT * FROM records WHERE file_hash=?", (file_hash,)).fetchone()
        return self._to_record(row) if row else None

    # ---- 入库（留痕）----
    def insert(self, *, status: str, file_name: str, file_hash: str,
               fields: InvoiceFields, audit_notes: str = "", source: str = "web") -> Record:
        now = _now()
        cur = self.conn.execute(
            """INSERT INTO records
               (status, file_name, file_hash, invoice_code, invoice_number,
                category, total_amount, fields_json, audit_notes, source, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (status, file_name, file_hash, fields.invoice_code, fields.invoice_number,
             fields.category, fields.total_amount, json.dumps(fields.to_dict(), ensure_ascii=False),
             audit_notes, source, now, now),
        )
        self.conn.commit()
        return self.get(cur.lastrowid)  # type: ignore[return-value]

    def get(self, record_id: int) -> Optional[Record]:
        row = self.conn.execute("SELECT * FROM records WHERE id=?", (record_id,)).fetchone()
        return self._to_record(row) if row else None

    def list_records(self, *, limit: int = 200, offset: int = 0,
                     status: Optional[str] = None) -> list[Record]:
        sql = "SELECT * FROM records"
        params: list = []
        if status:
            sql += " WHERE status=?"
            params.append(status)
        sql += " ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?"
        params += [limit, offset]
        return [self._to_record(r) for r in self.conn.execute(sql, params).fetchall()]

    def all_active(self) -> list[Record]:
        """参与汇总/编表的有效记录（rejected 不计入）。"""
        rows = self.conn.execute(
            "SELECT * FROM records WHERE status != 'rejected' ORDER BY created_at ASC, id ASC"
        ).fetchall()
        return [self._to_record(r) for r in rows]

    # ---- 人工介入窗口：修正回流 ----
    def correct(self, record_id: int, new_fields: InvoiceFields, *, new_status: str = "ok") -> Optional[Record]:
        old = self.get(record_id)
        if old is None:
            return None
        self.conn.execute(
            "INSERT INTO corrections (record_id, before_json, after_json, created_at) VALUES (?,?,?,?)",
            (record_id, json.dumps(old.fields.to_dict(), ensure_ascii=False),
             json.dumps(new_fields.to_dict(), ensure_ascii=False), _now()),
        )
        self.conn.execute(
            """UPDATE records SET status=?, invoice_code=?, invoice_number=?, category=?,
               total_amount=?, fields_json=?, updated_at=? WHERE id=?""",
            (new_status, new_fields.invoice_code, new_fields.invoice_number, new_fields.category,
             new_fields.total_amount, json.dumps(new_fields.to_dict(), ensure_ascii=False),
             _now(), record_id),
        )
        self.conn.commit()
        return self.get(record_id)

    def list_corrections(self, record_id: int) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM corrections WHERE record_id=? ORDER BY id ASC", (record_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    # ---- API 用量台账（管理后台 token 统计）----
    def log_usage(self, usage: dict) -> None:
        self.conn.execute(
            """INSERT INTO api_usage
               (provider, model, operation, prompt_tokens, completion_tokens,
                latency_ms, success, error, attempts, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (usage.get("provider", ""), usage.get("model", ""), usage.get("operation", "recognize"),
             usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0),
             usage.get("latency_ms", 0), 1 if usage.get("success") else 0,
             usage.get("error", ""), usage.get("attempts", 1), _now()),
        )
        self.conn.commit()

    def usage_stats(self, days: int = 30) -> dict:
        rows = self.conn.execute(
            """SELECT provider,
                      COUNT(*) AS calls,
                      SUM(success) AS successes,
                      SUM(prompt_tokens) AS prompt_tokens,
                      SUM(completion_tokens) AS completion_tokens,
                      ROUND(AVG(latency_ms)) AS avg_latency_ms
               FROM api_usage
               WHERE created_at >= datetime('now', ?)
               GROUP BY provider""",
            (f"-{days} days",),
        ).fetchall()
        by_provider = {r["provider"]: dict(r) for r in rows}
        recent = self.conn.execute(
            "SELECT * FROM api_usage ORDER BY id DESC LIMIT 20"
        ).fetchall()
        return {
            "days": days,
            "by_provider": by_provider,
            "recent": [dict(r) for r in recent],
        }

    def stats(self) -> dict:
        """系统概览（管理后台首页）。"""
        row = self.conn.execute(
            """SELECT COUNT(*) AS total,
                      SUM(CASE WHEN status='ok' THEN 1 ELSE 0 END) AS ok,
                      SUM(CASE WHEN status='review' THEN 1 ELSE 0 END) AS review,
                      SUM(CASE WHEN status='rejected' THEN 1 ELSE 0 END) AS rejected
               FROM records"""
        ).fetchone()
        corrections = self.conn.execute("SELECT COUNT(*) AS c FROM corrections").fetchone()["c"]
        return {"records": dict(row), "corrections": corrections}

    @staticmethod
    def _to_record(row: sqlite3.Row) -> Record:
        return Record(
            id=row["id"], status=row["status"], file_name=row["file_name"],
            file_hash=row["file_hash"], created_at=row["created_at"], updated_at=row["updated_at"],
            audit_notes=row["audit_notes"],
            fields=InvoiceFields(**json.loads(row["fields_json"])),
            source=row["source"] if "source" in row.keys() else "web",
        )
