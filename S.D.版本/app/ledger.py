"""简版复式记账内核（G-10，参考 beancount 设计独立实现，避开 GPL）。

设计要点：
- 每张票据 → 一组借贷平衡的分录（Entry: 借方账户/贷方账户/金额）；
- 科目体系为小微企业五级简版账户树（资产/负债/权益/收入/成本费用）；
- 三表 = 分录汇总的确定性算法，无任何钳制——平衡校验真实反映数据质量；
- 价税分离：有不含税金额+税额时拆「净额 + 应交税费」两行，否则按价税合计全额入账。

记账规则（收付实现与权责发生按支付方式自动区分）：
  收入·现金类   借:货币资金   贷:主营业务收入(+应交税费-销项)
  收入·非现金   借:应收账款   贷:主营业务收入(+应交税费-销项)
  支出·现金类   借:费用/成本(+应交税费-进项)   贷:货币资金
  支出·非现金   借:费用/成本(+应交税费-进项)   贷:应付账款
  收回应收     借:货币资金   贷:应收账款
  支付应付     借:应付账款   贷:货币资金
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from .schemas import Record

# ---- 科目 → 账户映射（关键词命中，可扩展）----
_EXPENSE_ACCOUNTS: dict[str, tuple[str, ...]] = {
    "管理费用": ("管理费用", "服务费", "办公费", "房租", "水电"),
    "销售费用": ("销售费用", "广告", "推广", "运输费", "快递"),
    "差旅费": ("差旅费", "交通", "住宿", "出租车"),
    "财务费用": ("财务费用", "利息", "手续费"),
}
_COST_KEYS = ("主营业务成本", "原材料", "采购", "进货")
_REVENUE_ACCOUNTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("主营业务收入", ("主营业务收入", "销售收入", "产品销售", "营业收入")),
    ("其他业务收入", ("其他业务收入",)),
)
_RECEIVABLE_KEYS = ("应收账款",)
_PAYABLE_KEYS = ("应付账款",)
_CASH_METHODS = ("现金", "银行", "转账", "微信", "支付宝")

ASSET_ACCOUNTS = ("货币资金", "应收账款")
LIABILITY_ACCOUNTS = ("应付账款", "应交税费")
INCOME_ACCOUNTS = tuple(a for a, _ in _REVENUE_ACCOUNTS)
COST_ACCOUNTS = ("主营业务成本",)
EXPENSE_ACCOUNTS = tuple(_EXPENSE_ACCOUNTS) + ("其他费用",)


@dataclass(frozen=True)
class Entry:
    """一条复式分录行（同一票据的多行合起来借贷必平衡）。"""

    account: str
    debit: float   # 借方金额
    credit: float  # 贷方金额
    record_id: int
    memo: str


def _match(text: str, keys: Iterable[str]) -> bool:
    return any(k in text for k in keys)


def map_expense_account(category: str) -> str:
    for account, keys in _EXPENSE_ACCOUNTS.items():
        if _match(category, keys):
            return account
    return "其他费用"


def map_revenue_account(category: str) -> str:
    for account, keys in _REVENUE_ACCOUNTS:
        if _match(category, keys):
            return account
    return "主营业务收入"


def _r2(x: float) -> float:
    return round(x + 1e-9, 2)


def entries_for_record(rec: Record) -> list[Entry]:
    """把一张票据转成借贷分录组。无法确定方向/金额的返回空组（不该发生，审计已拦截）。"""
    f = rec.fields
    total = f.total_amount if f.total_amount is not None else f.amount
    if total is None or f.direction not in ("收入", "支出"):
        return []
    total = _r2(total)
    net = _r2(f.amount) if f.amount is not None else total
    tax = _r2(total - net) if f.amount is not None else 0.0
    rid, cat = rec.id, f.category or ""
    cash_like = _match(f.payment_method or "", _CASH_METHODS)
    memo = f"#{rid} {f.item_name or cat or f.invoice_type or '票据'}"
    entries: list[Entry] = []

    if f.direction == "收入":
        rev_acc = map_revenue_account(cat)
        debit_acc = "货币资金" if cash_like else "应收账款"
        entries.append(Entry(debit_acc, total, 0.0, rid, memo))
        entries.append(Entry(rev_acc, 0.0, net, rid, memo))
        if tax:
            entries.append(Entry("应交税费", 0.0, tax, rid, memo + " 销项税"))
    else:
        if _match(cat, _RECEIVABLE_KEYS):   # 收回应收
            entries.append(Entry("货币资金", total, 0.0, rid, memo))
            entries.append(Entry("应收账款", 0.0, total, rid, memo))
        elif _match(cat, _PAYABLE_KEYS):    # 支付应付
            entries.append(Entry("应付账款", total, 0.0, rid, memo))
            entries.append(Entry("货币资金", 0.0, total, rid, memo))
        else:
            exp_acc = "主营业务成本" if _match(cat, _COST_KEYS) else map_expense_account(cat)
            credit_acc = "货币资金" if cash_like else "应付账款"
            entries.append(Entry(exp_acc, net, 0.0, rid, memo))
            if tax:
                entries.append(Entry("应交税费", tax, 0.0, rid, memo + " 进项税"))
            entries.append(Entry(credit_acc, 0.0, total, rid, memo))
    return entries


def build_ledger(records: list[Record]) -> list[Entry]:
    entries: list[Entry] = []
    for rec in records:
        entries.extend(entries_for_record(rec))
    return entries


def account_balances(entries: list[Entry]) -> dict[str, float]:
    """账户余额：资产/成本费用 借正贷负；负债/权益/收入 贷正借负（此处先算 借-贷 净值，由调用方按类别取号）。"""
    balances: dict[str, float] = {}
    for e in entries:
        balances[e.account] = _r2(balances.get(e.account, 0.0) + e.debit - e.credit)
    return balances


def trial_balance_ok(entries: list[Entry]) -> tuple[bool, float]:
    """试算平衡：全部借方合计 == 全部贷方合计。"""
    debit = _r2(sum(e.debit for e in entries))
    credit = _r2(sum(e.credit for e in entries))
    return abs(debit - credit) < 0.005, _r2(debit - credit)
