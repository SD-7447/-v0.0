"""汇总计算与三大报表编制（确定性规则引擎，每次上传后整体重算）。

对应会议纪要：
- 暂存表汇总 → 编制三表（资产负债表 / 利润表 / 现金流量表）；
- 每新增一张即触发一次更新（实时性），不做「一轮只算一次」；
- 小微企业简版口径：按会计科目映射报表行，全部本地确定性计算，可校验、可回溯。

说明：报表编制采用确定性科目映射（而非完全依赖第二次 LLM 调用），
保证结果可复算、可审计；后续如需 LLM 润色口径说明，可在此层之上叠加。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from ..schemas import Record, StatementLine, Statements

# ---- 科目 → 报表行 映射规则（关键词命中，可扩展）----
_REVENUE_KEYS = ("主营业务收入", "其他业务收入", "营业收入", "销售收入")
_COST_KEYS = ("主营业务成本", "原材料", "采购", "进货")
_EXPENSE_MAP = {
    "管理费用": ("管理费用", "服务费", "办公费", "房租", "水电"),
    "销售费用": ("销售费用", "广告", "推广", "运输费", "快递"),
    "差旅费": ("差旅费", "交通", "住宿", "出租车"),
    "财务费用": ("财务费用", "利息", "手续费"),
}
_RECEIVABLE_KEYS = ("应收账款",)
_PAYABLE_KEYS = ("应付账款",)
_CASH_METHODS = ("现金", "银行", "转账", "微信", "支付宝")


def _match(text: str, keys: Iterable[str]) -> bool:
    return any(k in text for k in keys)


def compile_statements(records: list[Record]) -> Statements:
    """对暂存表有效记录（ok + review）整体重算三大报表。"""
    revenue = cost = 0.0
    expense_lines: dict[str, float] = {}
    receivable = payable = 0.0
    cash_in = cash_out = 0.0

    for rec in records:
        f = rec.fields
        amount = f.total_amount if f.total_amount is not None else (f.amount or 0.0)
        cat = f.category or ""
        direction = f.direction
        is_cash_like = _match(f.payment_method or "", _CASH_METHODS)

        if direction == "收入":
            revenue += amount
            if not is_cash_like:
                receivable += amount
            else:
                cash_in += amount
        elif direction == "支出":
            if _match(cat, _RECEIVABLE_KEYS):
                receivable -= amount  # 应收账款核销/回收
                cash_in += amount
                continue
            if _match(cat, _PAYABLE_KEYS):
                payable -= amount  # 应付账款核销/支付
                cash_out += amount
                continue
            if _match(cat, _COST_KEYS):
                cost += amount
            else:
                for line, keys in _EXPENSE_MAP.items():
                    if _match(cat, keys):
                        expense_lines[line] = expense_lines.get(line, 0.0) + amount
                        break
                else:
                    expense_lines.setdefault("其他费用", 0.0)
                    expense_lines["其他费用"] += amount
            if is_cash_like:
                cash_out += amount
            else:
                payable += amount

    total_expense = sum(expense_lines.values())
    net_profit = revenue - cost - total_expense

    # ---- 利润表 ----
    income_lines = [StatementLine("一、营业收入", round(revenue, 2))]
    income_lines.append(StatementLine("减：营业成本", round(cost, 2)))
    for name in _EXPENSE_MAP:
        if expense_lines.get(name):
            income_lines.append(StatementLine(f"减：{name}", round(expense_lines[name], 2)))
    if expense_lines.get("其他费用"):
        income_lines.append(StatementLine("减：其他费用", round(expense_lines["其他费用"], 2)))
    income_lines.append(StatementLine("二、净利润", round(net_profit, 2)))

    # ---- 现金流量表（小微企业简版：仅经营活动）----
    cashflow_lines = [
        StatementLine("销售商品、提供劳务收到的现金", round(cash_in, 2)),
        StatementLine("购买商品、接受劳务支付的现金", round(cash_out, 2)),
        StatementLine("经营活动产生的现金流量净额", round(cash_in - cash_out, 2)),
        StatementLine("期末现金及现金等价物余额", round(cash_in - cash_out, 2)),
    ]

    # ---- 资产负债表（简版）----
    cash = cash_in - cash_out
    assets = [
        StatementLine("货币资金", round(cash, 2)),
        StatementLine("应收账款", round(max(receivable, 0.0), 2)),
    ]
    liabilities = [StatementLine("应付账款", round(max(payable, 0.0), 2))]
    equity = [StatementLine("未分配利润", round(net_profit, 2))]
    total_assets = sum(l.amount for l in assets)
    total_le = sum(l.amount for l in liabilities) + sum(l.amount for l in equity)
    balance_lines = (
        [StatementLine("—— 资产 ——", 0.0)] + assets
        + [StatementLine("资产总计", round(total_assets, 2))]
        + [StatementLine("—— 负债 ——", 0.0)] + liabilities
        + [StatementLine("—— 所有者权益 ——", 0.0)] + equity
        + [StatementLine("负债和所有者权益总计", round(total_le, 2))]
    )

    return Statements(
        generated_at=datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        record_count=len(records),
        balance_sheet=balance_lines,
        balance_check=abs(total_assets - total_le) < 0.02,
        income_statement=income_lines,
        cashflow_statement=cashflow_lines,
    )
