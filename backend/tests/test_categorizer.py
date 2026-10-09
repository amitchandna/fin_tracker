import pytest

from app.categorizer import UserRule, classify, detect_payment_method, normalize_merchant
from app.models import AccountType, Kind, PaymentMethod

CC, CHK = AccountType.CREDIT_CARD, AccountType.CHECKING


@pytest.mark.parametrize("desc,amount,acct,category,kind", [
    ("NETFLIX.COM 866-579-7172 CA", -15.49, CC, "Subscriptions", Kind.EXPENSE),
    ("WHOLEFDS NOH 10245", -80, CC, "Groceries", Kind.EXPENSE),
    ("STARBUCKS STORE 123", -5, CC, "Dining", Kind.EXPENSE),
    ("Payment Thank You-Mobile", 500, CC, "Credit Card Payment", Kind.TRANSFER),
    ("CHASE CREDIT CRD AUTOPAY", -500, CHK, "Credit Card Payment", Kind.TRANSFER),
    ("ONLINE TRANSFER TO SAV ...1234", -200, CHK, "Transfers", Kind.TRANSFER),
    ("ACME CORP PAYROLL PPD", 3000, CHK, "Income", Kind.INCOME),
    ("AMAZON MKTPL*RT88Q1", 20, CC, "Shopping", Kind.REFUND),
    ("ZELLE PAYMENT TO JORDAN", -40, CHK, "Peer-to-Peer", Kind.EXPENSE),
    ("VERIZON WIRELESS PAYMENTS", -65, CHK, "Utilities", Kind.EXPENSE),
    ("ENTERPRISE RENT-A-CAR", -120, CC, "Travel", Kind.EXPENSE),
    ("MYSTERY MERCHANT", -10, CC, "Uncategorized", Kind.EXPENSE),
    ("MYSTERY DEPOSIT", 10, CHK, "Income", Kind.INCOME),
])
def test_builtin_classification(desc, amount, acct, category, kind):
    c = classify(desc, amount, acct, None, [])
    assert (c.category, c.kind) == (category, kind)


def test_source_category_used_as_fallback():
    c = classify("LOCAL PLACE 42", -30, CC, "Food & Drink", [])
    assert c.category == "Dining"
    assert c.category_source == "source"


def test_user_rule_wins():
    rules = [UserRule(id="1", pattern="starbucks", category="Coffee")]
    c = classify("STARBUCKS STORE 1", -5, CC, None, rules)
    assert c.category == "Coffee" and c.category_source == "rule"


def test_user_rule_kind_override():
    rules = [UserRule(id="1", pattern="VENMO FROM ROOMMATE", category="Housing", kind="refund")]
    c = classify("VENMO FROM ROOMMATE", 600, CHK, None, rules)
    assert c.kind == Kind.REFUND


def test_bad_regex_rule_ignored():
    rules = [UserRule(id="1", pattern="([", category="X", match="regex")]
    assert classify("NETFLIX", -10, CC, None, rules).category == "Subscriptions"


@pytest.mark.parametrize("desc,expected", [
    ("NETFLIX.COM 866-579-7172 CA", "Netflix"),
    ("SQ *BLUE BOTTLE COFFEE #12", "Blue Bottle Coffee"),
    ("DEBIT CARD PURCHASE SAFEWAY #1234", "Safeway"),
    ("APPLE.COM/BILL 866-712-7753 CA", "Apple Bill"),
])
def test_normalize_merchant(desc, expected):
    assert normalize_merchant(desc) == expected


@pytest.mark.parametrize("desc,acct,expected", [
    ("ANYTHING", CC, PaymentMethod.CREDIT),
    ("DEBIT CARD PURCHASE SAFEWAY", CHK, PaymentMethod.DEBIT),
    ("ATM WITHDRAWAL 5TH AVE", CHK, PaymentMethod.CASH),
    ("CHECK 1043", CHK, PaymentMethod.CHECK),
    ("ZELLE PAYMENT TO X", CHK, PaymentMethod.TRANSFER),
    ("VERIZON WIRELESS", CHK, PaymentMethod.DEBIT),
])
def test_payment_method(desc, acct, expected):
    assert detect_payment_method(desc, acct) == expected
