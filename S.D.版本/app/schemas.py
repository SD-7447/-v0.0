"""数据模型与预设字段清单 v3（G-02 强校验 / G-03 字段扩充至 30+）。

会议纪要要求：
- 结构化结果使用固定字段，缺失字段留空；
- 与预设字段无关但可能有价值的信息不删除，统一归入「备注/其他」字段，保留追溯能力。

整改变更：
- 字段分三级：core（核心必填倾向）/ normal（常规可空）/ extra（扩展追溯），合计 30+；
- from_raw 做 schema 强校验：类型不符 → 置空并记 validation_notes；
  未知字段 → 归入 remarks 并标记 schema_violation，不再静默吞掉。
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

# ---- 预设字段清单（无对应项则留空）----
# (字段名, 中文名, 级别, 类型)   级别: core / normal / extra   类型: str / num / date
PRESET_FIELD_DEFS: list[tuple[str, str, str, str]] = [
    # 核心
    ("invoice_type", "发票/票据类型", "core", "str"),
    ("invoice_number", "发票号码", "core", "str"),
    ("invoice_date", "开票日期", "core", "date"),
    ("total_amount", "价税合计", "core", "num"),
    ("category", "会计科目", "core", "str"),
    ("direction", "收支方向", "core", "str"),
    # 常规
    ("invoice_code", "发票代码", "normal", "str"),
    ("buyer_name", "购买方名称", "normal", "str"),
    ("buyer_tax_id", "购买方税号", "normal", "str"),
    ("seller_name", "销售方名称", "normal", "str"),
    ("seller_tax_id", "销售方税号", "normal", "str"),
    ("item_name", "货物或服务名称", "normal", "str"),
    ("amount", "金额(不含税)", "normal", "num"),
    ("tax_amount", "税额", "normal", "num"),
    ("tax_rate", "税率", "normal", "num"),
    ("payment_method", "收付款方式", "normal", "str"),
    ("quantity", "数量", "normal", "num"),
    ("unit_price", "单价", "normal", "num"),
    ("expense_type", "费用类型", "normal", "str"),
    ("invoice_status", "发票状态(正常/红冲/作废)", "normal", "str"),
    # 扩展追溯
    ("unit", "计量单位", "extra", "str"),
    ("spec_model", "规格型号", "extra", "str"),
    ("buyer_bank", "购买方开户行及账号", "extra", "str"),
    ("seller_bank", "销售方开户行及账号", "extra", "str"),
    ("buyer_addr", "购买方地址电话", "extra", "str"),
    ("seller_addr", "销售方地址电话", "extra", "str"),
    ("payee", "收款人", "extra", "str"),
    ("reviewer", "复核人", "extra", "str"),
    ("drawer", "开票人", "extra", "str"),
    ("check_code", "校验码", "extra", "str"),
    ("currency", "币种", "extra", "str"),
    # 兜底
    ("remarks", "备注/其他", "core", "str"),
]

PRESET_FIELDS: list[tuple[str, str]] = [(k, label) for k, label, _, _ in PRESET_FIELD_DEFS]
FIELD_LABELS: dict[str, str] = dict(PRESET_FIELDS)
FIELD_TYPES: dict[str, str] = {k: t for k, _, _, t in PRESET_FIELD_DEFS}
NUM_FIELDS = {k for k, t in FIELD_TYPES.items() if t == "num"}


@dataclass
class InvoiceFields:
    """单张票据的结构化识别结果（预设字段 + 备注 + 校验留痕）。"""

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
    tax_rate: Optional[float] = None
    category: str = ""           # 会计科目
    direction: str = ""          # 收入 / 支出
    payment_method: str = ""
    quantity: Optional[float] = None
    unit_price: Optional[float] = None
    expense_type: str = ""
    invoice_status: str = ""
    unit: str = ""
    spec_model: str = ""
    buyer_bank: str = ""
    seller_bank: str = ""
    buyer_addr: str = ""
    seller_addr: str = ""
    payee: str = ""
    reviewer: str = ""
    drawer: str = ""
    check_code: str = ""
    currency: str = ""
    remarks: str = ""            # 多余信息统一归入此处，不删除
    confidence: float = 0.0
    validation_notes: str = ""   # schema 校验留痕（G-02）

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> "InvoiceFields":
        """把模型输出的任意 dict 清洗进预设字段，并做强校验留痕。

        - 未知键 → 合并进 remarks，记 schema_violation；
        - 数字字段类型不符（如字符串无法解析）→ 置空并记录；
        - 字符串字段收到非字符串 → 强制 str()。
        """
        known = {k for k, _ in PRESET_FIELDS} | {"confidence", "validation_notes"}
        cleaned: dict[str, Any] = {}
        extras: list[str] = []
        notes: list[str] = []
        for key, value in raw.items():
            if key in known:
                cleaned[key] = value
            elif value not in (None, "", []):
                extras.append(f"{key}={json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value}")
        if extras:
            notes.append(f"schema_violation: {len(extras)} 个未知字段已归入备注")

        for key in list(cleaned):
            ftype = FIELD_TYPES.get(key)
            if ftype == "num":
                parsed = _to_float(cleaned[key])
                if cleaned[key] not in (None, "") and parsed is None:
                    notes.append(f"字段 {key} 类型不符已置空（原值: {cleaned[key]}）")
                cleaned[key] = parsed
            elif ftype in ("str", "date") and cleaned[key] is not None and not isinstance(cleaned[key], str):
                cleaned[key] = str(cleaned[key])

        if "confidence" in cleaned:
            cleaned["confidence"] = min(1.0, max(0.0, _to_float(cleaned["confidence"]) or 0.0))
        obj = cls(**cleaned)
        if extras:
            extra_text = "；".join(extras)
            obj.remarks = f"{obj.remarks}；{extra_text}".strip("；")
        if notes:
            obj.validation_notes = "；".join(notes)
        return obj

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _to_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).replace(",", "").replace("¥", "").replace("￥", "").replace("元", "").strip()
    if text.endswith("%"):  # 税率 "13%" → 0.13
        try:
            return float(text[:-1]) / 100
        except ValueError:
            return None
    try:
        return float(text)
    except ValueError:
        return None


@dataclass
class Record:
    """暂存表一行记录（含留痕元数据）。status: ok / review / rejected；source: web / wechat"""

    id: int
    status: str
    file_name: str
    file_hash: str
    created_at: str
    updated_at: str
    audit_notes: str
    fields: InvoiceFields = field(default_factory=InvoiceFields)
    source: str = "web"

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
