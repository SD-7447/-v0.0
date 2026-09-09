"""审计 Agent v2（G-11 规则扩充；确定性规则，LLM 不参与核对）。

参考 invoice-ap-agent 架构：LLM 只做抽取，核对交给确定性代码；
硬性失败 → rejected；软性异常 / 低置信度 → review（人工介入窗口）。

规则清单：
  R1 硬性：金额缺失 → rejected
  R2 勾稽：金额+税额 ≠ 价税合计 → review
  R3 置信度低于阈值 → review
  R4 科目缺失 → review
  R5 收支方向不明 → review
  R6 金额为负（红冲/退款嫌疑）→ review
  R7 发票号码格式（8 位或 20 位数字）→ review
  R8 开票日期异常（未来 / 超过 10 年前）→ review
  R9 金额异常值（超过历史均值 10 倍且 >1 万元）→ review
  R10 税率反推不在常见档位（0/1/3/5/6/9/13%）→ review
  R11 schema 校验留痕非空（模型输出不规范）→ review
"""
from __future__ import annotations

import re
from datetime import date
from typing import Optional

from ..schemas import InvoiceFields

CONFIDENCE_THRESHOLD = 0.6
_COMMON_TAX_RATES = (0.0, 0.01, 0.03, 0.05, 0.06, 0.09, 0.13)


def audit(fields: InvoiceFields, context: Optional[dict] = None) -> tuple[str, list[str]]:
    """返回 (status, notes)。status ∈ {ok, review, rejected}。

    context（可选）：{"mean_amount": 历史平均金额}
    """
    notes: list[str] = []

    # R1 硬性失败：关键信息缺失
    if fields.total_amount is None and fields.amount is None:
        notes.append("R1 缺少金额信息，无法入账")
        return "rejected", notes

    # R2 勾稽校验：金额 + 税额 ≈ 价税合计
    if fields.amount is not None and fields.tax_amount is not None and fields.total_amount is not None:
        if abs(fields.amount + fields.tax_amount - fields.total_amount) > 0.02:
            notes.append(
                f"R2 勾稽不符：金额 {fields.amount} + 税额 {fields.tax_amount} ≠ 价税合计 {fields.total_amount}"
            )

    # R3 置信度
    if fields.confidence < CONFIDENCE_THRESHOLD:
        notes.append(f"R3 置信度 {fields.confidence:.2f} 低于阈值 {CONFIDENCE_THRESHOLD}，建议人工复核")

    # R4 科目 / R5 方向
    if not fields.category:
        notes.append("R4 会计科目未识别，需人工指定")
    if fields.direction not in ("收入", "支出"):
        notes.append("R5 收支方向不明确，需人工确认")

    # R6 负金额
    check_amount = fields.total_amount if fields.total_amount is not None else fields.amount
    if check_amount is not None and check_amount < 0:
        notes.append("R6 金额为负，请确认是否为红冲/退款票据")

    # R7 发票号码格式（传统 8 位 / 数电票 20 位）
    if fields.invoice_number and not re.fullmatch(r"\d{8}|\d{20}", fields.invoice_number.strip()):
        notes.append(f"R7 发票号码「{fields.invoice_number}」格式异常（应为 8 位或 20 位数字）")

    # R8 开票日期合理性
    if fields.invoice_date:
        try:
            d = date.fromisoformat(fields.invoice_date.strip()[:10])
            today = date.today()
            if d > today:
                notes.append(f"R8 开票日期 {d} 晚于今天，疑似识别错误")
            elif (today - d).days > 3650:
                notes.append(f"R8 开票日期 {d} 距今超过 10 年，疑似识别错误")
        except ValueError:
            notes.append(f"R8 开票日期「{fields.invoice_date}」无法解析")

    # R9 金额异常值
    if context and check_amount is not None:
        mean = context.get("mean_amount") or 0.0
        if mean > 0 and check_amount > max(mean * 10, 10000):
            notes.append(f"R9 金额 {check_amount} 超过历史均值 10 倍，疑似异常值")

    # R10 税率反推
    if fields.amount and fields.tax_amount is not None and fields.amount > 0:
        rate = fields.tax_amount / fields.amount
        if not any(abs(rate - r) < 0.005 for r in _COMMON_TAX_RATES):
            notes.append(f"R10 反推税率 {rate:.2%} 不在常见档位（0/1/3/5/6/9/13%）")

    # R11 schema 校验留痕
    if fields.validation_notes:
        notes.append(f"R11 模型输出不规范：{fields.validation_notes}")

    # 发票状态非"正常"（红冲/作废）也要人工确认
    if fields.invoice_status and fields.invoice_status not in ("正常", "有效"):
        notes.append(f"发票状态为「{fields.invoice_status}」，需人工确认是否入账")

    return ("review", notes) if notes else ("ok", notes)
