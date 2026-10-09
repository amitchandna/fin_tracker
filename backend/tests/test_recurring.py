from datetime import date, timedelta

from app.models import AccountType, Kind, PaymentMethod, Transaction
from app.recurring import detect_recurring


def txn(i, d, desc, amount, category="Subscriptions", merchant=None):
    return Transaction(id=f"t{i}", date=d, description=desc, amount=amount, source_file="f.csv", account="Card",
                       account_type=AccountType.CREDIT_CARD, payment_method=PaymentMethod.CREDIT,
                       kind=Kind.EXPENSE if amount < 0 else Kind.REFUND, category=category,
                       merchant=merchant or desc.title())


def monthly(desc, amount, n=4, start=date(2026, 1, 5), category="Subscriptions"):
    return [txn(f"{desc}{i}", start + timedelta(days=30 * i), desc, amount, category) for i in range(n)]


def test_monthly_subscription_detected():
    series = detect_recurring(monthly("NETFLIX", -15.49))
    assert len(series) == 1
    s = series[0]
    assert s.frequency == "monthly"
    assert s.average_amount == 15.49
    assert s.monthly_cost == 15.49
    assert s.active and s.fixed_amount


def test_variable_utility_bill_detected():
    txns = [txn(i, date(2026, 1, 10) + timedelta(days=30 * i), "PG&E", -a, "Utilities")
            for i, a in enumerate([90, 105, 98, 110])]
    s = detect_recurring(txns)[0]
    assert s.frequency == "monthly" and not s.fixed_amount


def test_irregular_purchases_not_recurring():
    dates = [date(2026, 1, 1), date(2026, 1, 3), date(2026, 2, 20), date(2026, 2, 21), date(2026, 4, 1)]
    txns = [txn(i, d, "AMAZON", -20 - i, "Shopping") for i, d in enumerate(dates)]
    assert detect_recurring(txns) == []


def test_weekly_groceries_with_varying_amounts_not_recurring():
    txns = [txn(i, date(2026, 1, 3) + timedelta(days=7 * i), "WHOLE FOODS", -(60 + 13 * i), "Groceries")
            for i in range(8)]
    assert detect_recurring(txns) == []


def test_weekly_fixed_amount_bill_detected():
    txns = [txn(i, date(2026, 1, 3) + timedelta(days=7 * i), "DOG WALKER", -25, "Services") for i in range(6)]
    s = detect_recurring(txns)[0]
    assert s.frequency == "weekly"
    assert round(s.monthly_cost, 2) == round(25 * 52 / 12, 2)


def test_two_occurrences_need_explicit_hint():
    assert detect_recurring(monthly("GYM", -30, n=2)) == []
    assert len(detect_recurring(monthly("GYM RECURRING", -30, n=2))) == 1


def test_lapsed_subscription_inactive():
    txns = monthly("HULU", -8, n=3, start=date(2026, 1, 1))
    txns.append(txn("other", date(2026, 9, 1), "OTHER", -5, "Shopping"))
    s = next(s for s in detect_recurring(txns) if s.merchant == "Hulu")
    assert not s.active
