from datetime import date

import pytest

from app.models import AccountType, Kind, PaymentMethod, Transaction
from app.paychecks import PaySchedule, expected_by_month, expected_pay, paydays


def sched(**kw):
    base = dict(id="s1", name="Acme", amount=3850.0, frequency="semimonthly", days=[15, 31])
    base.update(kw)
    return PaySchedule(**base)


def deposit(i, d, amount, desc="ACME PAYROLL", account="Checking", kind=Kind.INCOME, source="auto"):
    return Transaction(id=f"t{i}", date=d, description=desc, amount=amount, source_file="f.csv", account=account,
                       account_type=AccountType.CHECKING, payment_method=PaymentMethod.TRANSFER, kind=kind,
                       category="Income", merchant=desc.title(), category_source=source)


def test_semimonthly_last_day_and_weekend_shift():
    # Aug 15 2026 is a Saturday -> Friday 14th; Aug 31 is a Monday.
    assert paydays(sched(), date(2026, 8, 1), date(2026, 8, 31)) == [date(2026, 8, 14), date(2026, 8, 31)]
    # Feb: "31" means the last day (28th, a Saturday -> Friday 27th).
    assert paydays(sched(), date(2026, 2, 1), date(2026, 2, 28))[-1] == date(2026, 2, 27)


def test_weekend_after_and_none():
    assert paydays(sched(weekend="after"), date(2026, 8, 1), date(2026, 8, 31))[0] == date(2026, 8, 17)
    assert paydays(sched(weekend="none"), date(2026, 8, 1), date(2026, 8, 31))[0] == date(2026, 8, 15)


def test_biweekly_from_anchor_in_either_direction():
    s = sched(frequency="biweekly", days=[], anchor_date="2026-06-05")  # a Friday
    days = paydays(s, date(2026, 5, 1), date(2026, 7, 1))
    assert days == [date(2026, 5, 8), date(2026, 5, 22), date(2026, 6, 5), date(2026, 6, 19)]
    assert expected_by_month([s], date(2026, 7, 1), date(2026, 7, 31)) == {"2026-07": 3850 * 3}  # Jul 3, 17, 31


def test_monthly_respects_start_and_end():
    s = sched(frequency="monthly", days=[1], start_date="2026-03-01", end_date="2026-05-31", weekend="none")
    assert paydays(s, date(2026, 1, 1), date(2026, 12, 31)) == [date(2026, 3, 1), date(2026, 4, 1), date(2026, 5, 1)]


def test_matching_by_date_amount_account_and_text():
    s = sched(account="Checking", match_text="payroll")
    txns = [
        deposit(1, date(2026, 8, 14), 3850.00),
        deposit(2, date(2026, 9, 1), 3901.10),  # a day late, slightly more: still a match
        deposit(3, date(2026, 8, 14), 3850.00, account="Savings"),  # wrong account
        deposit(4, date(2026, 8, 31), 3850.00, desc="ZELLE FROM MOM"),  # wrong text
    ]
    got = {e.date: e.transaction_id for e in expected_pay([s], txns, date(2026, 8, 1), date(2026, 8, 31))}
    assert got == {date(2026, 8, 14): "t1", date(2026, 8, 31): "t2"}


def test_amount_far_off_or_labelled_payback_not_matched():
    s = sched()
    txns = [deposit(1, date(2026, 8, 14), 1200.00),
            deposit(2, date(2026, 8, 31), 3850.00, kind=Kind.REFUND, source="manual")]
    assert all(e.transaction_id is None for e in expected_pay([s], txns, date(2026, 8, 1), date(2026, 8, 31)))


def test_each_deposit_matches_one_payday():
    s = sched(frequency="weekly", days=[], anchor_date="2026-08-07")
    txns = [deposit(1, date(2026, 8, 10), 3850.0)]  # between two weekly paydays
    matched = [e for e in expected_pay([s], txns, date(2026, 8, 1), date(2026, 8, 20)) if e.transaction_id]
    assert len(matched) == 1


@pytest.mark.parametrize("today,status", [
    (date(2026, 8, 10), "upcoming"), (date(2026, 8, 16), "due"), (date(2026, 8, 25), "missed"),
])
def test_status(today, status):
    (e,) = expected_pay([sched(days=[14, 31])], [], date(2026, 8, 1), date(2026, 8, 20))
    assert e.status(today) == status


def test_monthly_amount():
    assert sched().monthly_amount == 7700
    assert sched(frequency="biweekly", anchor_date="2026-01-02").monthly_amount == pytest.approx(3850 * 26 / 12)
