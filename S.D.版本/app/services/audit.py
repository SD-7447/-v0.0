"""审计 Agent（确定性规则，LLM 不参与核对）。

参考 invoice-ap-agent 架构：LLM 只做抽取，核对交给确定性代码；
硬性失败 → rejected；软性异常 / 低置信度 → review（人工介入窗口）。
"""
from __future__ import annotations

from ..schemas import InvoiceFields

# 置信度阈值：低于该值进入人工复核队列
CONFIDENCE_THRESHOLD = 0.6


def audit(fields: InvoiceFields) -> tuple[str, list[str]]:
    """返回 (status, notes)。status ∈ {ok, review, rejected}。"""
    notes: list[str] = []

    # 硬性失败：关键信息缺失
    if fields.total_amount is None and fields.amount is None:
        notes.append("缺少金额信息，无法入账")
        return "rejected", notes

    # 勾稽校验：金额 + 税额 ≈ 价税合计
    if fields.amount is not None and fields.tax_amount is not None and fields.total_amount is not None:
        if abs(fields.amount + fields.tax_amount - fields.total_amount) > 0.02:
            notes.append(
                f"勾稽不符：金额 {fields.amount} + 税额 {fields.tax_amount} ≠ 价税合计 {fields.total_amount}"
            )
            return "review", notes

    # 软性异常 → 人工复核
    if fields.confidence < CONFIDENCE_THRESHOLD:
        notes.append(f"置信度 {fields.confidence:.2f} 低于阈值 {CONFIDENCE_THRESHOLD}，建议人工复核")
    if not fields.category:
        notes.append("会计科目未识别，需人工指定")
    if fields.direction not in ("收入", "支出"):
        notes.append("收支方向不明确，需人工确认")
    if fields.total_amount is not None and fields.total_amount < 0:
        notes.append("金额为负，请确认是否为红冲/退款票据")

    return ("review", notes) if notes else ("ok", notes)
