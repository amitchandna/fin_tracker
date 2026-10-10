"""Expected income: pay schedules the user enters, the paydays they produce, and
matching those paydays to real deposits.

A deposit that matches an expected paycheck (close in date and amount, and in
the right account / with the right description when the schedule says so) is
treated as confirmed income, so regular pay never needs reviewing by hand.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date, timedelta

from .models import Kind, Transaction

FREQUENCIES = ("weekly", "biweekly", "semimonthly", "monthly")
MATCH_WINDOW_DAYS = 4  # deposits can land a few days either side of payday


@dataclass
class PaySchedule:
    id: str
    name: str
    amount: float  # what actually lands in the account (take-home)
    frequency: str  # weekly | biweekly | semimonthly | monthly
    # weekly / biweekly: any one real payday, the rest are every 7/14 days from it.
    anchor_date: str | None = None
    # semimonthly: two days of the month; monthly: one. 31 means "last day of the month".
    days: list[int] = field(default_factory=list)
    weekend: str = "before"  # payday on a weekend moves to the Friday before | after (Monday) | none
    account: str | None = None  # only match deposits into this account
    match_text: str | None = None  # only match deposits whose description or memo contains this
    tolerance: float = 0.1  # how far the deposit may differ from `amount` (fraction)
    start_date: str | None = None
    end_date: str | None = None

    def to_dict(self) -> dict:
        return dict(self.__dict__)

    @property
    def monthly_amount(self) -> float:
        per_month = {"weekly": 52 / 12, "biweekly": 26 / 12, "semimonthly": 2, "monthly": 1}[self.frequency]
        return self.amount * per_month


def _adjust(d: date, weekend: str) -> date:
    if weekend == "none" or d.weekday() < 5:
        return d
    if weekend == "after":
        return d + timedelta(days=7 - d.weekday())
    return d - timedelta(days=d.weekday() - 4)


def _month_iter(start: date, end: date):
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def paydays(s: PaySchedule, start: date, end: date) -> list[date]:
    """Every payday for schedule ``s`` between ``start`` and ``end`` inclusive."""
    lo = max(start, date.fromisoformat(s.start_date)) if s.start_date else start
    hi = min(end, date.fromisoformat(s.end_date)) if s.end_date else end
    if lo > hi:
        return []
    raw: list[date] = []
    if s.frequency in ("weekly", "biweekly"):
        if not s.anchor_date:
            return []
        step = 7 if s.frequency == "weekly" else 14
        anchor = date.fromisoformat(s.anchor_date)
        # First payday on/after lo-7 (so a weekend shift into range still counts).
        offset = ((lo - timedelta(days=7)) - anchor).days
        d = anchor + timedelta(days=-(-offset // step) * step)
        while d <= hi + timedelta(days=7):
            raw.append(d)
            d += timedelta(days=step)
    else:
        for y, m in _month_iter(lo - timedelta(days=7), hi + timedelta(days=7)):
            last = calendar.monthrange(y, m)[1]
            for day in s.days:
                raw.append(date(y, m, min(max(day, 1), last)))
    return sorted({p for p in (_adjust(d, s.weekend) for d in raw) if lo <= p <= hi})


@dataclass
class ExpectedPay:
    schedule_id: str
    name: str
    date: date
    amount: float
    transaction_id: str | None = None
    actual_amount: float | None = None
    actual_date: date | None = None

    def status(self, today: date) -> str:
        if self.transaction_id:
            return "received"
        if self.date > today:
            return "upcoming"
        if (today - self.date).days <= MATCH_WINDOW_DAYS:
            return "due"
        return "missed"

    def to_dict(self, today: date) -> dict:
        return {
            "schedule_id": self.schedule_id,
            "name": self.name,
            "date": self.date.isoformat(),
            "month": self.date.strftime("%Y-%m"),
            "amount": round(self.amount, 2),
            "status": self.status(today),
            "transaction_id": self.transaction_id,
            "actual_amount": None if self.actual_amount is None else round(self.actual_amount, 2),
            "actual_date": self.actual_date.isoformat() if self.actual_date else None,
        }


def _candidate(t: Transaction, s: PaySchedule) -> bool:
    if t.amount <= 0 or t.excluded or t.kind == Kind.TRANSFER:
        return False
    # A deposit the user labelled as something other than income is never a paycheck.
    if t.category_source == "manual" and t.kind != Kind.INCOME:
        return False
    if s.account and t.account != s.account:
        return False
    text = f"{t.description} {t.memo or ''}".lower()
    if s.match_text and s.match_text.strip().lower() not in text:
        return False
    return abs(t.amount - s.amount) <= max(abs(s.amount) * s.tolerance, 1.0)


def expected_pay(schedules: list[PaySchedule], transactions: list[Transaction],
                 start: date, end: date) -> list[ExpectedPay]:
    """Expected paydays in [start, end], each matched to at most one deposit."""
    used: set[str] = set()
    out: list[ExpectedPay] = []
    for s in schedules:
        cands = [t for t in transactions if _candidate(t, s)]
        for p in paydays(s, start, end):
            exp = ExpectedPay(schedule_id=s.id, name=s.name, date=p, amount=s.amount)
            near = [t for t in cands if t.id not in used and abs((t.date - p).days) <= MATCH_WINDOW_DAYS]
            if near:
                best = min(near, key=lambda t: (abs((t.date - p).days), abs(t.amount - s.amount)))
                used.add(best.id)
                exp.transaction_id, exp.actual_amount, exp.actual_date = best.id, best.amount, best.date
            out.append(exp)
    out.sort(key=lambda e: (e.date, e.name))
    return out


def expected_by_month(schedules: list[PaySchedule], start: date, end: date) -> dict[str, float]:
    totals: dict[str, float] = {}
    for s in schedules:
        for p in paydays(s, start, end):
            key = p.strftime("%Y-%m")
            totals[key] = totals.get(key, 0.0) + s.amount
    return totals
