from datetime import date, timedelta

import pytest

from app.budgets import progress, suggest
from app.models import AccountType, Kind, PaymentMethod, Transaction


def txn(i, d, amount, category, kind=None, excluded=False):
    kind = kind or (Kind.EXPENSE if amount < 0 else Kind.REFUND)
    return Transaction(id=f"t{i}", date=d, description=category, amount=amount, source_file="f.csv",
                       account="Card", account_type=AccountType.CREDIT_CARD, payment_method=PaymentMethod.CREDIT,
                       kind=kind, category=category, merchant=category, excluded=excluded)


def test_finished_month_statuses():
    txns = [txn(1, date(2026, 8, 3), -300, "Groceries"), txn(2, date(2026, 8, 20), -250, "Groceries"),
            txn(3, date(2026, 8, 31), -100, "Dining")]
    p = progress(txns, {"Groceries": 500, "Dining": 100}, "2026-08")
    rows = {r["category"]: r for r in p["categories"]}
    assert not p["in_progress"] and p["elapsed"] == 1
    assert (rows["Groceries"]["status"], rows["Groceries"]["remaining"]) == ("over", -50)
    assert rows["Dining"]["status"] == "on_track"  # exactly on budget in a finished month is fine
    assert p["totals"] == {"budget": 600, "spent": 650, "remaining": -50, "projected": 650, "unbudgeted": 0,
                           "over": 1, "at_risk": 0, "status": "over"}


def test_month_in_progress_without_history_projects_in_a_straight_line():
    # Data runs to Sep 10 of a 30-day month: a third of the way through.
    txns = [txn(1, date(2026, 9, 2), -100, "Dining"), txn(2, date(2026, 9, 10), -50, "Groceries")]
    p = progress(txns, {"Dining": 200, "Groceries": 600}, "2026-09")
    rows = {r["category"]: r for r in p["categories"]}
    assert p["in_progress"] and p["elapsed"] == pytest.approx(1 / 3, abs=1e-3)
    assert rows["Dining"]["pace"] == pytest.approx(66.67, abs=0.01)
    assert rows["Dining"]["projected"] == pytest.approx(300)
    assert rows["Dining"]["status"] == "at_risk"     # under budget, but on course to overshoot
    assert rows["Groceries"]["status"] == "on_track"


def test_refunds_excluded_and_unbudgeted():
    txns = [txn(1, date(2026, 8, 1), -200, "Shopping"), txn(2, date(2026, 8, 5), 50, "Shopping"),
            txn(3, date(2026, 8, 6), -999, "Shopping", excluded=True),
            txn(4, date(2026, 8, 7), -500, "Credit Card Payment", kind=Kind.TRANSFER),
            txn(5, date(2026, 8, 31), -80, "Travel")]
    p = progress(txns, {"Shopping": 300}, "2026-08")
    assert p["categories"][0]["spent"] == 150  # refund offsets, excluded and transfers ignored
    assert p["unbudgeted"] == [{"category": "Travel", "spent": 80}]


def test_suggest_uses_recent_complete_months_rounded_up():
    start = date(2026, 4, 15)
    txns = [txn(i, start + timedelta(days=30 * i), -(301 + i), "Groceries") for i in range(5)]
    txns.append(txn(99, date(2026, 9, 5), -2000, "Groceries"))  # Sep has only 5 days of data
    s = suggest(txns, months=3)
    # Uses Jun, Jul, Aug (Sep is still in progress): (303 + 304 + 305) / 3 = 304 -> 310
    assert s["Groceries"] == {"average": 304.0, "suggested": 310.0, "months": 3}


def test_projection_uses_what_you_usually_spend_in_the_rest_of_the_month():
    txns = []
    for i, m in enumerate((6, 7, 8)):
        txns += [txn(f"r{i}", date(2026, m, 1), -2000, "Housing"),           # rent on the 1st
                 txn(f"g{i}a", date(2026, m, 5), -100, "Groceries"),
                 txn(f"g{i}b", date(2026, m, 20), -150, "Groceries"),        # after day 10
                 txn(f"s{i}", date(2026, m, 25), -30, "Shopping")]
    # September so far (data to the 10th): rent paid, one grocery shop, one early Amazon order.
    txns += [txn("r9", date(2026, 9, 1), -2000, "Housing"), txn("g9", date(2026, 9, 6), -120, "Groceries"),
             txn("s9", date(2026, 9, 10), -64, "Shopping")]
    p = progress(txns, {"Housing": 2000, "Groceries": 300, "Shopping": 100}, "2026-09")
    rows = {r["category"]: r for r in p["categories"]}
    assert rows["Housing"]["projected"] == 2000          # not 3x the rent
    assert rows["Housing"]["status"] == "on_track"        # rent paid, exactly on budget
    assert rows["Groceries"]["projected"] == 270          # 120 so far + usual 150 later
    assert rows["Groceries"]["status"] == "on_track"
    assert rows["Shopping"]["projected"] == 94            # 64 + usual 30, not 64 * 3
    assert rows["Shopping"]["status"] == "on_track"


def test_net_negative_unbudgeted_category_keeps_totals_consistent():
    # A friend pays back tickets bought last month: Entertainment is net -18.50 this month.
    txns = [txn(1, date(2026, 9, 3), -100, "Dining"), txn(2, date(2026, 9, 14), 18.5, "Entertainment"),
            txn(3, date(2026, 9, 30), -40, "Shopping")]
    p = progress(txns, {"Dining": 200}, "2026-09")
    assert p["unbudgeted"] == [{"category": "Shopping", "spent": 40}, {"category": "Entertainment", "spent": -18.5}]
    assert p["totals"]["spent"] + p["totals"]["unbudgeted"] == pytest.approx(100 + 40 - 18.5)
