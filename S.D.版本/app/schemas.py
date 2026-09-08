"""数据模型与预设字段清单（纯标准库 dataclass，核心逻辑零三方依赖）。

会议纪要要求：
- 结构化结果使用固定字段，缺失字段留空；
- 与预设字段无关但可能有价值的信息不删除，统一归入「备注/其他」字段，保留追溯能力。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional

# ---- 预设字段清单（无对应项则留空）----
# (字段名, 中文名)
PRESET_FIELDS: list[tuple[str, str]] = [
    ("invoice_type", "发票/票据类型"),
    ("invoice_code", "发票代码"),
    ("invoice_number", "发票号码"),
    ("invoice_date", "开票日期"),
    ("buyer_name", "购买方名称"),
    ("buyer_tax_id", "购买方税号"),
    ("seller_name", "销售方名称"),
    ("seller_tax_id", "销售方税号"),
    ("item_name", "货物或服务名称"),
    ("amount", "金额(不含税)"),
    ("tax_amount", "税额"),
    ("total_amount", "价税合计"),
    ("category", "会计科目"),
    ("direction", "收支方向"),
    ("payment_method", "收付款方式"),
    ("remarks", "备注/其他"),
]

FIELD_LABELS: dict[str, str] = dict(PRESET_FIELDS)


@dataclass
class InvoiceFields:
    """单张票据的结构化识别结果（预设字段 + 备注）。"""

    invoice_type: str = ""
    invoice_code: str = ""
    invoice_number: str = ""
    invoice_date: str = ""
    buyer_name: str = ""
    buyer_tax_id: str = ""
    seller_name: str = ""
    seller_tax_id: str = ""
    item_name: str = ""
    amount: Optional[float] = None
    tax_amount: Optional[float] = None
    total_amount: Optional[float] = None
    category: str = ""           # 会计科目
    direction: str = ""          # 收入 / 支出
    payment_method: str = ""
    remarks: str = ""            # 多余信息统一归入此处，不删除
    confidence: float = 0.0

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> "InvoiceFields":
        """把模型输出的任意 dict 清洗进预设字段：多余键合并进 remarks。"""
        known = {k for k, _ in PRESET_FIELDS} | {"confidence"}
        cleaned: dict[str, Any] = {}
        extras: list[str] = []
        for key, value in raw.items():
            if key in known:
                cleaned[key] = value
            elif value not in (None, "", []):
                extras.append(f"{key}={value}")
        for num_key in ("amount", "tax_amount", "total_amount"):
            if num_key in cleaned:
                cleaned[num_key] = _to_float(cleaned[num_key])
        if "confidence" in cleaned:
            cleaned["confidence"] = min(1.0, max(0.0, _to_float(cleaned["confidence"]) or 0.0))
        obj = cls(**cleaned)
        if extras:
            extra_text = "；".join(str(e) for e in extras)
            obj.remarks = f"{obj.remarks}；{extra_text}".strip("；")
        return obj

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _to_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).replace(",", "").replace("¥", "").replace("￥", "").replace("元", "").strip()
    try:
        return float(text)
    except ValueError:
        return None


@dataclass
class Record:
    """暂存表一行记录（含留痕元数据）。status: ok / review / rejected"""

    id: int
    status: str
    file_name: str
    file_hash: str
    created_at: str
    updated_at: str
    audit_notes: str
    fields: InvoiceFields = field(default_factory=InvoiceFields)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["fields"] = self.fields.to_dict()
        return d


@dataclass
class StatementLine:
    label: str
    amount: float


@dataclass
class Statements:
    """三大报表输出（每次上传后整体重算）。"""

    generated_at: str
    record_count: int
    balance_sheet: list[StatementLine]
    balance_check: bool           # 资产 = 负债 + 所有者权益 校验
    income_statement: list[StatementLine]
    cashflow_statement: list[StatementLine]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class UploadResult:
    """每上传一张即返回的处理反馈（实时性要求）。status: success / review / duplicate / failed"""

    status: str
    message: str
    record: Optional[Record] = None
    statements: Optional[Statements] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "message": self.message,
            "record": self.record.to_dict() if self.record else None,
            "statements": self.statements.to_dict() if self.statements else None,
        }
