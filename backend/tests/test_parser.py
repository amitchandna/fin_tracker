from datetime import date

import pytest

from app.models import AccountType
from app.parser import account_name_from_file, parse_amount, parse_csv_text, parse_date


@pytest.mark.parametrize("raw,expected", [
    ("12.34", 12.34), ("-12.34", -12.34), ("$1,234.56", 1234.56), ("(45.00)", -45.0), ("12.34-", -12.34),
    ("12.34 CR", 12.34), ("12.34 DR", -12.34), ("-$5.00", -5.0), ("1.234,56", 1234.56), ("", None), ("abc", None),
])
def test_parse_amount(raw, expected):
    assert parse_amount(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("2026-03-04", date(2026, 3, 4)), ("03/04/2026", date(2026, 3, 4)), ("3/4/26", date(2026, 3, 4)),
    ("Mar 4, 2026", date(2026, 3, 4)), ("04 Mar 2026", date(2026, 3, 4)), ("2026-03-04T10:00:00", date(2026, 3, 4)),
    ("not a date", None),
])
def test_parse_date(raw, expected):
    assert parse_date(raw) == expected


def test_account_name_strips_dates():
    assert account_name_from_file("chase_credit_2026-01.csv") == "Chase Credit"
    assert account_name_from_file("Chase_Credit 2026-02-28.csv") == "Chase Credit"


def test_signed_amount_bank_file():
    text = "Date,Description,Amount\n2026-01-02,STARBUCKS,-5.25\n2026-01-03,ACME PAYROLL,2000.00\n"
    pf = parse_csv_text(text, "checking.csv")
    assert pf.error is None
    assert pf.account_type == AccountType.CHECKING
    assert [r.amount for r in pf.rows] == [-5.25, 2000.0]
    assert not pf.inverted


def test_positive_charge_card_is_inverted():
    text = ("Date,Description,Amount\n01/02/2026,NETFLIX.COM,15.49\n01/05/2026,TARGET,40.00\n"
            "01/20/2026,AUTOPAY PAYMENT - THANK YOU,-55.49\n")
    pf = parse_csv_text(text, "amex.csv")
    assert pf.account_type == AccountType.CREDIT_CARD
    assert pf.inverted
    assert [r.amount for r in pf.rows] == [-15.49, -40.0, 55.49]


def test_negative_charge_card_not_inverted():
    text = ("Transaction Date,Post Date,Description,Category,Type,Amount\n"
            "01/02/2026,01/03/2026,STARBUCKS,Food & Drink,Sale,-5.00\n"
            "01/25/2026,01/25/2026,Payment Thank You-Mobile,,Payment,300.00\n")
    pf = parse_csv_text(text, "chase_card.csv")
    assert not pf.inverted
    assert pf.rows[0].amount == -5.0
    assert pf.rows[0].source_category == "Food & Drink"


def test_debit_credit_columns_and_preamble():
    text = ("Account Name: Checking\nAccount Number: XXXX1\n\n"
            "Date,Description,Debit,Credit,Balance\n"
            "2026-01-01,RENT PAYMENT,1500.00,,500.00\n2026-01-15,PAYROLL,,2500.00,3000.00\n")
    pf = parse_csv_text(text, "bank.csv")
    assert pf.error is None
    assert [r.amount for r in pf.rows] == [-1500.0, 2500.0]
    assert pf.account_type == AccountType.CHECKING


def test_type_column_with_unsigned_amounts():
    text = "Date,Description,Amount,Transaction Type\n2026-01-01,COFFEE,4.50,DEBIT\n2026-01-02,REFUND,4.50,CREDIT\n"
    pf = parse_csv_text(text, "acct.csv")
    assert [r.amount for r in pf.rows] == [-4.5, 4.5]


def test_day_first_dates_detected():
    text = "Date,Description,Amount\n20/04/2026,Interest Paid,10.00\n05/04/2026,Something,-1.00\n"
    pf = parse_csv_text(text, "savings.csv")
    assert [r.date for r in pf.rows] == [date(2026, 4, 20), date(2026, 4, 5)]


def test_headerless_file_inferred():
    text = '"01/02/2026","-12.50","*","","STARBUCKS STORE"\n"01/03/2026","-40.00","*","","SHELL OIL"\n'
    pf = parse_csv_text(text, "wf.csv")
    assert pf.error is None
    assert pf.rows[0].description == "STARBUCKS STORE"
    assert pf.rows[0].amount == -12.5


def test_semicolon_delimiter():
    text = "Date;Description;Amount\n2026-01-02;BAKERY;-3,50\n"
    pf = parse_csv_text(text, "eu.csv")
    assert pf.rows[0].amount == -3.5


def test_invalid_rows_skipped_with_warning():
    text = "Date,Description,Amount\n2026-01-02,OK,-1.00\nTotal,,-1.00\n"
    pf = parse_csv_text(text, "x.csv")
    assert len(pf.rows) == 1
    assert any("Skipped 1" in w for w in pf.warnings)


def test_unparseable_file_reports_error():
    pf = parse_csv_text("hello,world\nfoo,bar\n", "junk.csv")
    assert pf.error


def test_overrides_force_type_and_sign():
    text = "Date,Description,Amount\n2026-01-02,SHOP,10.00\n"
    pf = parse_csv_text(text, "x.csv", {"account_type": "credit_card", "invert_amounts": True, "name": "My Card"})
    assert pf.account == "My Card"
    assert pf.account_type == AccountType.CREDIT_CARD
    assert pf.rows[0].amount == -10.0
