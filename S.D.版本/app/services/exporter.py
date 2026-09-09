"""数据导出（G-07）：暂存表导出为 xlsx / csv。"""
from __future__ import annotations

import csv
import io

from openpyxl import Workbook
from openpyxl.styles import Font

from ..db import StagingDB
from ..schemas import PRESET_FIELD_DEFS

# 导出列：预设字段（备注放最后）+ 留痕元数据
_EXPORT_KEYS = [k for k, _, _, _ in PRESET_FIELD_DEFS if k != "remarks"] + [
    "remarks", "confidence", "status", "audit_notes", "created_at",
]
_HEADERS = [label for k, label, _, _ in PRESET_FIELD_DEFS if k != "remarks"] + [
    "备注/其他", "置信度", "状态", "审计提示", "入库时间",
]


def _rows(db: StagingDB) -> list[list]:
    out = []
    for rec in reversed(db.list_records(limit=100000)):  # 时间正序
        f = rec.fields.to_dict()
        out.append([
            *[f.get(k) for k in _EXPORT_KEYS[: len(_EXPORT_KEYS) - 5]],
            f.get("remarks"), f.get("confidence"),
            rec.status, rec.audit_notes, rec.created_at,
        ])
    return out


def export_csv(db: StagingDB) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(_HEADERS)
    writer.writerows(_rows(db))
    return b"\xef\xbb\xbf" + buf.getvalue().encode("utf-8")  # BOM 保证 Excel 中文不乱码


def export_xlsx(db: StagingDB) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "暂存明细"
    ws.append(_HEADERS)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    ws.freeze_panes = "A2"
    for row in _rows(db):
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
