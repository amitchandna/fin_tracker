"""Aggregations over classified transactions.

Spending is always *net*: expenses minus refunds. Savings for a month is
income minus spending: whatever came in and wasn't spent is assumed saved. Transfers (card payments,
moves between your own accounts) never count as spending or income, so paying a
credit card bill from checking isn't counted twice.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date

from .models import Kind, Transaction
from .recurring import RecurringSeries


def _r(x: float) -> float:
    return round(x + 0.0, 2)


def spend_value(t: Transaction) -> float:
    """Contribution of a transaction to spending (positive = spent)."""
    if t.kind == Kind.EXPENSE:
        return -t.amount
    if t.kind == Kind.REFUND:
        return -t.amount  # refunds are positive amounts, so this reduces spending
    return 0.0


def _rounded(d: dict[str, float]) -> dict[str, float]:
    return {k: _r(v) for k, v in sorted(d.items(), key=lambda kv: -kv[1]) if abs(v) >= 0.005}


def budgeted(transactions: list[Transaction]) -> list[Transaction]:
    """Transactions the user hasn't scrubbed from the budget."""
    return [t for t in transactions if not t.excluded]


def monthly_summary(transactions: list[Transaction]) -> list[dict]:
    transactions = budgeted(transactions)
    months: dict[str, dict] = {}
    for t in transactions:
        m = months.setdefault(t.month, {
            "month": t.month, "gross_spending": 0.0, "refunds": 0.0, "income": 0.0, "transfers": 0.0,
            "recurring": 0.0, "one_time": 0.0, "transactions": 0,
            "by_category": defaultdict(float), "by_payment_method": defaultdict(float),
            "by_account": defaultdict(float), "by_account_type": defaultdict(float),
            "by_income_source": defaultdict(float),
        })
        m["transactions"] += 1
        if t.kind == Kind.EXPENSE:
            m["gross_spending"] += -t.amount
        elif t.kind == Kind.REFUND:
            m["refunds"] += t.amount
        elif t.kind == Kind.INCOME:
            m["income"] += t.amount
            m["by_income_source"][t.merchant] += t.amount
        else:
            m["transfers"] += abs(t.amount)
        v = spend_value(t)
        if v:
            m["by_category"][t.category] += v
            m["by_payment_method"][t.payment_method.value] += v
            m["by_account"][t.account] += v
            m["by_account_type"][t.account_type.value] += v
            m["recurring" if t.is_recurring else "one_time"] += v

    out = []
    cumulative = 0.0
    for key in sorted(months):
        m = months[key]
        net = m["gross_spending"] - m["refunds"]
        # Assumption: whatever income isn't spent in a month is saved. Transfers to a
        # savings or brokerage account are not spending, so they count as saved too.
        savings = m["income"] - net
        cumulative += savings
        out.append({
            "month": key,
            "spending": _r(net),
            "gross_spending": _r(m["gross_spending"]),
            "refunds": _r(m["refunds"]),
            "income": _r(m["income"]),
            "net_cashflow": _r(savings),
            "savings": _r(savings),
            "savings_rate": round(savings / m["income"], 4) if m["income"] > 0.005 else None,
            "cumulative_savings": _r(cumulative),
            "transfers": _r(m["transfers"]),
            "recurring": _r(m["recurring"]),
            "one_time": _r(m["one_time"]),
            "transactions": m["transactions"],
            "by_category": _rounded(m["by_category"]),
            "by_payment_method": _rounded(m["by_payment_method"]),
            "by_account": _rounded(m["by_account"]),
            "by_account_type": _rounded(m["by_account_type"]),
            "by_income_source": _rounded(m["by_income_source"]),
        })
    return out


def category_breakdown(transactions: list[Transaction]) -> list[dict]:
    transactions = budgeted(transactions)
    totals: dict[str, dict] = {}
    for t in transactions:
        v = spend_value(t)
        if not v:
            continue
        c = totals.setdefault(t.category, {"category": t.category, "spending": 0.0, "transactions": 0,
                                           "recurring": 0.0, "by_payment_method": defaultdict(float)})
        c["spending"] += v
        c["transactions"] += 1
        if t.is_recurring:
            c["recurring"] += v
        c["by_payment_method"][t.payment_method.value] += v
    total = sum(c["spending"] for c in totals.values()) or 1.0
    rows = []
    for c in sorted(totals.values(), key=lambda c: -c["spending"]):
        rows.append({**c, "spending": _r(c["spending"]), "recurring": _r(c["recurring"]),
                     "share": round(c["spending"] / total, 4), "by_payment_method": _rounded(c["by_payment_method"])})
    return rows


def income_sources(transactions: list[Transaction]) -> list[dict]:
    """Where money comes in from, grouped by payer (normalised description)."""
    transactions = budgeted(transactions)
    sources: dict[str, dict] = {}
    months = {t.month for t in transactions}
    for t in transactions:
        if t.kind != Kind.INCOME:
            continue
        s = sources.setdefault(t.merchant, {"source": t.merchant, "category": t.category, "amount": 0.0,
                                            "transactions": 0, "accounts": set(), "months": set(),
                                            "last_date": t.date})
        s["amount"] += t.amount
        s["transactions"] += 1
        s["accounts"].add(t.account)
        s["months"].add(t.month)
        s["last_date"] = max(s["last_date"], t.date)
    total = sum(s["amount"] for s in sources.values()) or 1.0
    rows = []
    for s in sorted(sources.values(), key=lambda s: -s["amount"]):
        rows.append({
            "source": s["source"],
            "category": s["category"],
            "amount": _r(s["amount"]),
            "transactions": s["transactions"],
            "share": round(s["amount"] / total, 4),
            "accounts": sorted(s["accounts"]),
            "months_received": len(s["months"]),
            "average_monthly": _r(s["amount"] / max(len(months), 1)),
            "last_date": s["last_date"].isoformat(),
        })
    return rows


def overview(transactions: list[Transaction], recurring: list[RecurringSeries]) -> dict:
    excluded = [t for t in transactions if t.excluded]
    excluded_stats = {"excluded_count": len(excluded),
                      "excluded_amount": _r(sum(abs(t.amount) for t in excluded))}
    transactions = budgeted(transactions)
    months = monthly_summary(transactions)
    if not months:
        return {"months": 0, "first_month": None, "last_month": None, "total_spending": 0, "total_income": 0,
                "average_monthly_spending": 0, "average_monthly_income": 0, "recurring_monthly_cost": 0,
                "active_recurring": 0, "latest_month": None, "previous_month": None, "top_categories": [],
                "by_payment_method": {}, "transactions": 0, "uncategorized": 0, "total_savings": 0,
                "average_monthly_savings": 0, "savings_rate": None, "months_saved": 0, "months_overspent": 0,
                **excluded_stats}
    # Partial months at either end distort averages, so average over full months when we have them.
    full = _full_months(transactions, months)
    basis = full or months
    total_spending = sum(m["spending"] for m in months)
    total_income = sum(m["income"] for m in months)
    basis_income = sum(m["income"] for m in basis)
    basis_savings = sum(m["savings"] for m in basis)
    by_method: dict[str, float] = defaultdict(float)
    for m in months:
        for k, v in m["by_payment_method"].items():
            by_method[k] += v
    return {
        "months": len(months),
        "first_month": months[0]["month"],
        "last_month": months[-1]["month"],
        "transactions": len(transactions),
        "total_spending": _r(total_spending),
        "total_income": _r(total_income),
        "average_monthly_spending": _r(sum(m["spending"] for m in basis) / len(basis)),
        "average_monthly_income": _r(sum(m["income"] for m in basis) / len(basis)),
        "average_basis_months": len(basis),
        "total_savings": _r(total_income - total_spending),
        "average_monthly_savings": _r(basis_savings / len(basis)),
        "savings_rate": round(basis_savings / basis_income, 4) if basis_income > 0.005 else None,
        "months_saved": sum(1 for m in months if m["savings"] > 0),
        "months_overspent": sum(1 for m in months if m["savings"] < 0),
        **excluded_stats,
        "recurring_monthly_cost": _r(sum(s.monthly_cost for s in recurring if s.active)),
        "active_recurring": sum(1 for s in recurring if s.active),
        "latest_month": months[-1],
        "previous_month": months[-2] if len(months) > 1 else None,
        "top_categories": category_breakdown(transactions)[:8],
        "by_payment_method": _rounded(by_method),
        "uncategorized": sum(1 for t in transactions if t.category == "Uncategorized" and t.kind == Kind.EXPENSE),
    }


def _full_months(transactions: list[Transaction], months: list[dict]) -> list[dict]:
    if len(months) <= 2:
        return []
    first: date = min(t.date for t in transactions)
    last: date = max(t.date for t in transactions)
    drop = set()
    if first.day > 7:
        drop.add(months[0]["month"])
    if last.day < 21:
        drop.add(months[-1]["month"])
    return [m for m in months if m["month"] not in drop]
