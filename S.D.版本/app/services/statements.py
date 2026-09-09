"""汇总计算与三大报表编制 v2：报表 = 复式分录汇总的确定性算法（G-10）。

与 v1 的区别：
- 数据源从「关键词单向映射」改为 ledger 复式记账内核（每张票据先转借贷分录）；
- 移除一切 max() 钳制——资产=负债+权益 的平衡校验真实反映数据质量；
- 每次上传后整体重算（实时性要求不变）。
"""
from __future__ import annotations

from datetime import datetime, timezone

from ..ledger import (
    ASSET_ACCOUNTS, COST_ACCOUNTS, EXPENSE_ACCOUNTS, INCOME_ACCOUNTS,
    LIABILITY_ACCOUNTS, account_balances, build_ledger, trial_balance_ok,
)
from ..schemas import Record, StatementLine, Statements


def _r2(x: float) -> float:
    return round(x + 1e-9, 2)


def compile_statements(records: list[Record]) -> Statements:
    """对暂存表有效记录（ok + review）整体重算三大报表。"""
    entries = build_ledger(records)
    bal = account_balances(entries)          # 借-贷 净值
    balanced, _diff = trial_balance_ok(entries)

    # 利润表（收入/负债类取贷方为正：-bal）
    revenue_by_acc = {a: _r2(-bal.get(a, 0.0)) for a in INCOME_ACCOUNTS}
    revenue = _r2(sum(revenue_by_acc.values()))
    cost = _r2(bal.get("主营业务成本", 0.0))
    expense_by_acc = {a: _r2(bal.get(a, 0.0)) for a in EXPENSE_ACCOUNTS if abs(bal.get(a, 0.0)) > 0.004}
    total_expense = _r2(sum(expense_by_acc.values()))
    net_profit = _r2(revenue - cost - total_expense)

    income_lines = [StatementLine("一、营业收入", revenue)]
    for acc, val in revenue_by_acc.items():
        if acc != "主营业务收入" and abs(val) > 0.004:
            income_lines.append(StatementLine(f"　其中：{acc}", val))
    income_lines.append(StatementLine("减：营业成本", cost))
    for acc in EXPENSE_ACCOUNTS:
        val = expense_by_acc.get(acc)
        if val:
            income_lines.append(StatementLine(f"减：{acc}", val))
    income_lines.append(StatementLine("二、净利润", net_profit))

    # 现金流量表（经营活动：货币资金账户的借贷发生额）
    cash_in = _r2(sum(e.debit for e in entries if e.account == "货币资金"))
    cash_out = _r2(sum(e.credit for e in entries if e.account == "货币资金"))
    cash_net = _r2(cash_in - cash_out)
    cashflow_lines = [
        StatementLine("销售商品、提供劳务收到的现金", cash_in),
        StatementLine("购买商品、接受劳务支付的现金", cash_out),
        StatementLine("经营活动产生的现金流量净额", cash_net),
        StatementLine("期末现金及现金等价物余额", _r2(bal.get("货币资金", 0.0))),
    ]

    # 资产负债表
    assets = [StatementLine(a, _r2(bal.get(a, 0.0))) for a in ASSET_ACCOUNTS]
    liabilities = [StatementLine(a, _r2(-bal.get(a, 0.0))) for a in LIABILITY_ACCOUNTS]
    equity = [StatementLine("未分配利润", net_profit)]
    total_assets = _r2(sum(l.amount for l in assets))
    total_liab = _r2(sum(l.amount for l in liabilities))
    total_equity = _r2(sum(l.amount for l in equity))
    total_le = _r2(total_liab + total_equity)
    balance_lines = (
        [StatementLine("—— 资产 ——", 0.0)] + assets
        + [StatementLine("资产总计", total_assets)]
        + [StatementLine("—— 负债 ——", 0.0)] + liabilities
        + [StatementLine("负债合计", total_liab)]
        + [StatementLine("—— 所有者权益 ——", 0.0)] + equity
        + [StatementLine("所有者权益合计", total_equity)]
        + [StatementLine("负债和所有者权益总计", total_le)]
    )

    # 双重校验：试算平衡（借贷合计相等）且 资产=负债+权益
    balance_check = balanced and abs(total_assets - total_le) < 0.005

    return Statements(
        generated_at=datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        record_count=len(records),
        balance_sheet=balance_lines,
        balance_check=balance_check,
        income_statement=income_lines,
        cashflow_statement=cashflow_lines,
    )
