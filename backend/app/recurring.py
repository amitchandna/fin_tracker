"""Detect recurring payments (subscriptions, bills, rent, memberships).

Expenses are grouped by normalised merchant. A group is recurring when its
charges arrive on a regular cadence (weekly ... yearly) with consistent amounts.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from statistics import median

from .models import Kind, Transaction

# name, typical days between charges, tolerance in days, occurrences per month
FREQUENCIES = [
    ("weekly", 7, 2, 52 / 12),
    ("biweekly", 14, 3, 26 / 12),
    ("monthly", 30.4, 5, 1.0),
    ("quarterly", 91, 12, 1 / 3),
    ("yearly", 365, 20, 1 / 12),
]

# Everyday categories where frequent, similar-sized purchases are habits rather
# than bills. They need near-identical amounts to count as recurring.
HABIT_CATEGORIES = {"Groceries", "Dining", "Auto & Gas", "Shopping", "Transportation", "Cash & ATM",
                    "Peer-to-Peer"}
EXPLICIT_HINT = re.compile(r"RECURRING|SUBSCRIPTION|MEMBERSHIP|AUTOPAY|AUTO-PAY|MONTHLY", re.I)


@dataclass
class RecurringSeries:
    id: str
    merchant: str
    category: str
    frequency: str
    average_amount: float
    last_amount: float
    monthly_cost: float
    occurrences: int
    first_date: date
    last_date: date
    next_expected: date
    active: bool
    fixed_amount: bool
    payment_methods: list[str] = field(default_factory=list)
    accounts: list[str] = field(default_factory=list)
    transaction_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "merchant": self.merchant,
            "category": self.category,
            "frequency": self.frequency,
            "average_amount": round(self.average_amount, 2),
            "last_amount": round(self.last_amount, 2),
            "monthly_cost": round(self.monthly_cost, 2),
            "occurrences": self.occurrences,
            "first_date": self.first_date.isoformat(),
            "last_date": self.last_date.isoformat(),
            "next_expected": self.next_expected.isoformat(),
            "active": self.active,
            "fixed_amount": self.fixed_amount,
            "payment_methods": self.payment_methods,
            "accounts": self.accounts,
            "transaction_ids": self.transaction_ids,
        }


def _match_frequency(intervals: list[int]) -> tuple[str, float, float] | None:
    if not intervals:
        return None
    med = median(intervals)
    for name, days, tol, per_month in FREQUENCIES:
        if abs(med - days) <= tol:
            regular = sum(abs(i - days) <= tol * 1.5 for i in intervals)
            if regular / len(intervals) >= 0.7:
                return name, days, per_month
    return None


def _amount_spread(amounts: list[float]) -> float:
    med = median(amounts)
    if med == 0:
        return 1.0
    return median(abs(a - med) for a in amounts) / med


def detect_recurring(transactions: list[Transaction], as_of: date | None = None) -> list[RecurringSeries]:
    expenses = [t for t in transactions if t.kind == Kind.EXPENSE]
    if not expenses:
        return []
    as_of = as_of or max(t.date for t in transactions)

    groups: dict[str, list[Transaction]] = {}
    for t in expenses:
        groups.setdefault(t.merchant.lower(), []).append(t)

    series: list[RecurringSeries] = []
    for key, txns in groups.items():
        txns.sort(key=lambda t: t.date)
        # Collapse same-day duplicates (e.g. split authorisations) into one occurrence.
        by_day: dict[date, list[Transaction]] = {}
        for t in txns:
            by_day.setdefault(t.date, []).append(t)
        days = sorted(by_day)
        explicit = any(EXPLICIT_HINT.search(t.description) for t in txns)
        min_occurrences = 2 if explicit else 3
        if len(days) < min_occurrences:
            continue

        intervals = [(b - a).days for a, b in zip(days, days[1:])]
        freq = _match_frequency(intervals)
        if freq is None:
            continue
        name, period, per_month = freq

        amounts = [sum(t.abs_amount for t in by_day[d]) for d in days]
        spread = _amount_spread(amounts)
        category = max({t.category for t in txns}, key=lambda c: sum(t.category == c for t in txns))
        limit = 0.03 if category in HABIT_CATEGORIES else 0.25
        if spread > limit:
            continue
        # A weekly coffee at the same price is a habit, not a bill.
        if category in HABIT_CATEGORIES and name in ("weekly", "biweekly") and not explicit:
            continue

        recent = amounts[-min(3, len(amounts)):]
        avg_amount = sum(recent) / len(recent)
        last = days[-1]
        next_expected = last + timedelta(days=round(period))
        active = (as_of - last).days <= period * 1.5 + 3
        sid = hashlib.sha1(key.encode()).hexdigest()[:12]
        series.append(RecurringSeries(
            id=sid,
            merchant=txns[-1].merchant,
            category=category,
            frequency=name,
            average_amount=avg_amount,
            last_amount=amounts[-1],
            monthly_cost=avg_amount * per_month,
            occurrences=len(days),
            first_date=days[0],
            last_date=last,
            next_expected=next_expected,
            active=active,
            fixed_amount=spread <= 0.02,
            payment_methods=sorted({t.payment_method.value for t in txns}),
            accounts=sorted({t.account for t in txns}),
            transaction_ids=[t.id for t in txns],
        ))

    series.sort(key=lambda s: (not s.active, -s.monthly_cost))
    return series
