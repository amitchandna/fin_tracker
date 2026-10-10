"""Monthly budgets per category, and progress against them.

Spending here is exactly the spending shown everywhere else in the app: net of
refunds and pay-backs, without transfers, card payments or anything excluded
from the budget.
"""

from __future__ import annotations

import calendar
import math
from collections import defaultdict
from datetime import date

from .analytics import budgeted, spend_value
from .models import Transaction


def spending_by_category(transactions: list[Transaction], month: str) -> dict[str, float]:
    totals: dict[str, float] = defaultdict(float)
    for t in budgeted(transactions):
        if t.month == month:
            v = spend_value(t)
            if v:
                totals[t.category] += v
    return dict(totals)


def suggest(transactions: list[Transaction], months: int = 3) -> dict[str, dict]:
    """Average monthly spending per category over the last ``months`` complete months,
    rounded up to the next $10, as a starting point for a budget."""
    all_months = sorted({t.month for t in budgeted(transactions)})
    if not all_months:
        return {}
    last_date = max(t.date for t in transactions)
    # Skip the latest month when it is still in progress (data stops before its last week).
    complete = all_months[:-1] if last_date.day < 21 and len(all_months) > 1 else all_months
    window = complete[-months:]
    sums: dict[str, float] = defaultdict(float)
    for m in window:
        for cat, v in spending_by_category(transactions, m).items():
            sums[cat] += v
    out = {}
    for cat, total in sums.items():
        avg = total / len(window)
        if avg > 0.5:
            out[cat] = {"average": round(avg, 2), "suggested": float(math.ceil(avg / 10) * 10),
                        "months": len(window)}
    return out


def _usual_rest_of_month(transactions: list[Transaction], month: str, day: int,
                         lookback: int = 3) -> dict[str, float] | None:
    """Average spending per category after ``day`` of the month, over recent earlier months.
    None when there is no earlier month to learn from."""
    earlier = sorted({t.month for t in budgeted(transactions) if t.month < month})[-lookback:]
    if not earlier:
        return None
    totals: dict[str, float] = defaultdict(float)
    for t in budgeted(transactions):
        if t.month in earlier and t.date.day > day:
            v = spend_value(t)
            if v:
                totals[t.category] += v
    return {c: v / len(earlier) for c, v in totals.items()}


def _status(spent: float, budget: float, projected: float, in_progress: bool) -> str:
    if spent > budget + 0.005:
        return "over"
    # "At risk": not over yet, but on course to be. Only while the month can still go either way.
    if in_progress and projected > budget + 0.005:
        return "at_risk"
    return "on_track"


def progress(transactions: list[Transaction], budgets: dict[str, float], month: str) -> dict:
    """Spent vs budget for every budgeted category in ``month``.

    For the month the data is currently in, ``elapsed`` is how far through the month
    the data goes and ``pace`` is how much of each budget an even rate would have used
    by now. ``projected`` is spending so far plus what you usually spend in the rest of
    the month (from recent months), or a straight-line estimate when there's no history."""
    y, m = (int(x) for x in month.split("-"))
    days = calendar.monthrange(y, m)[1]
    data_through = max((t.date for t in transactions), default=None)
    if data_through and (data_through.year, data_through.month) == (y, m) and data_through.day < days:
        elapsed = data_through.day / days
        in_progress = True
    else:
        elapsed = 1.0
        in_progress = False

    spent_by_cat = spending_by_category(transactions, month)
    rest = _usual_rest_of_month(transactions, month, data_through.day) if in_progress else {}
    rows = []
    for cat, budget in sorted(budgets.items(), key=lambda kv: -kv[1]):
        spent = spent_by_cat.get(cat, 0.0)
        if not in_progress:
            projected = spent
        elif rest is not None:
            # What's spent so far plus what you usually spend in the rest of the month. Handles
            # lumpy bills: rent paid on the 1st isn't projected again, a weekly shop is.
            projected = spent + rest.get(cat, 0.0)
        else:
            projected = spent / elapsed if elapsed > 0 else spent
        rows.append({
            "category": cat,
            "budget": round(budget, 2),
            "spent": round(spent, 2),
            "remaining": round(budget - spent, 2),
            "used": round(spent / budget, 4) if budget else None,
            "pace": round(budget * elapsed, 2),
            "projected": round(projected, 2),
            "status": _status(spent, budget, projected, in_progress),
        })
    # Net figures, so a category can be negative when pay-backs exceed what was spent that month
    # (a friend repaying last month's tickets). Keeping those makes the totals add up to real spending.
    unbudgeted = sorted(
        ({"category": c, "spent": round(v, 2)} for c, v in spent_by_cat.items()
         if c not in budgets and abs(v) > 0.005),
        key=lambda r: -r["spent"],
    )
    total_budget = sum(budgets.values())
    total_spent = sum(r["spent"] for r in rows)
    total_projected = sum(r["projected"] for r in rows)
    return {
        "month": month,
        "in_progress": in_progress,
        "data_through": data_through.isoformat() if data_through else None,
        "elapsed": round(elapsed, 4),
        "categories": rows,
        "unbudgeted": unbudgeted,
        "totals": {
            "budget": round(total_budget, 2),
            "spent": round(total_spent, 2),
            "remaining": round(total_budget - total_spent, 2),
            "projected": round(total_projected, 2),
            "unbudgeted": round(sum(r["spent"] for r in unbudgeted), 2),
            "over": sum(1 for r in rows if r["status"] == "over"),
            "at_risk": sum(1 for r in rows if r["status"] == "at_risk"),
            "status": _status(total_spent, total_budget, total_projected, in_progress) if total_budget else None,
        },
    }


def history(transactions: list[Transaction], budgets: dict[str, float], months: list[str]) -> list[dict]:
    """Spent vs budget per budgeted category for each month in ``months``."""
    out = []
    for month in months:
        spent = spending_by_category(transactions, month)
        cats = {c: round(spent.get(c, 0.0), 2) for c in budgets}
        out.append({
            "month": month,
            "spent": cats,
            "total_spent": round(sum(cats.values()), 2),
            "total_budget": round(sum(budgets.values()), 2),
            "over": [c for c, v in cats.items() if v > budgets[c] + 0.005],
        })
    return out


def current_month(today: date | None = None) -> str:
    return (today or date.today()).strftime("%Y-%m")
