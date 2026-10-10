"""Memo columns: what a transaction was for, when the description doesn't say."""

import pytest

from app.categorizer import (
    CATEGORIES, UserRule, classify, is_generic, merchant_for,
)
from app.models import AccountType, Kind
from app.parser import parse_csv_text

CC, CHK = AccountType.CREDIT_CARD, AccountType.CHECKING


def cat(desc, amount=-20.0, memo=None, acct=CHK, rules=()):
    c = classify(desc, amount, acct, None, list(rules), memo=memo, merchant=merchant_for(desc, memo))
    return c.category, c.kind, c.category_source


# ---- parsing --------------------------------------------------------------------------------

USER_EXAMPLE = ("Date,Description,Amount,Memo\n"
                "2026-09-14,ZELLE PAYMENT FROM ALEX KIM,18.50,movie tickets - my share\n"
                "2026-09-15,ONLINE PAYMENT 88213,-1200.00,Rent September Apt 4B\n"
                "2026-09-16,POS PURCHASE 4471,-63.20,TRADER JOE S #552 SEATTLE WA\n"
                "2026-09-17,ACH DEBIT,-45.00,\n")


def test_memo_column_is_read_alongside_description():
    pf = parse_csv_text(USER_EXAMPLE, "checking.csv")
    assert pf.columns["description"] == "description" and pf.columns["memo"] == "memo"
    assert [r.memo for r in pf.rows] == ["movie tickets - my share", "Rent September Apt 4B",
                                          "TRADER JOE S #552 SEATTLE WA", None]


def test_checking_bill_payment_does_not_flip_every_sign():
    # Regression: "ONLINE PAYMENT" in a checking account is a bill you paid, not a card payment received.
    pf = parse_csv_text(USER_EXAMPLE, "checking.csv")
    assert not pf.inverted
    assert [r.amount for r in pf.rows] == [18.5, -1200.0, -63.2, -45.0]


def test_card_with_positive_charges_still_flips():
    text = "Date,Description,Amount\n2026-01-02,SHOP,40.00\n2026-01-20,ONLINE PAYMENT THANK YOU,-40.00\n"
    assert parse_csv_text(text, "amex.csv").inverted


def test_several_memo_columns_are_combined_and_dupes_dropped():
    text = ("Date,Description,Amount,Memo,Notes,Extended Details\n"
            "2026-01-02,ACH DEBIT,-10,PUGET SOUND ENERGY,acct 123,ACH DEBIT\n")
    (row,) = parse_csv_text(text, "chk.csv").rows
    assert row.memo == "PUGET SOUND ENERGY · acct 123"


def test_memo_only_file_uses_memo_as_description():
    (row,) = parse_csv_text("Date,Memo,Amount\n2026-01-02,SAFEWAY #1,-10\n", "chk.csv").rows
    assert row.description == "SAFEWAY #1" and row.memo is None


# ---- the user's examples -------------------------------------------------------------------

def test_user_example_end_to_end():
    pf = parse_csv_text(USER_EXAMPLE, "checking.csv")
    got = [cat(r.description, r.amount, r.memo) for r in pf.rows]
    assert got == [
        ("Entertainment", Kind.REFUND, "memo"),   # a friend paying back their movie ticket
        ("Housing", Kind.EXPENSE, "memo"),
        ("Groceries", Kind.EXPENSE, "memo"),
        ("Uncategorized", Kind.EXPENSE, "auto"),  # nothing to go on: left for the user
    ]
    assert merchant_for("POS PURCHASE 4471", "TRADER JOE S #552 SEATTLE WA") == "Trader Joe's"


@pytest.mark.parametrize("desc,memo", [
    ("ACH DEBIT", None), ("ACH DEBIT", ""), ("POS PURCHASE 4471", "REF 88213"), ("ONLINE PAYMENT 88213", None),
    ("DEBIT CARD PURCHASE", "ID: 99812 WEB"), ("CHECK 1043", None), ("ELECTRONIC WITHDRAWAL", "PPD"),
])
def test_vague_transactions_are_left_for_the_user(desc, memo):
    assert cat(desc, -50.0, memo)[0] == "Uncategorized"
    assert is_generic(desc)


def test_description_wins_over_memo():
    assert cat("NETFLIX.COM", -15.49, "groceries")[:2] == ("Subscriptions", Kind.EXPENSE)


def test_user_rule_can_match_memo():
    rule = UserRule(id="1", pattern="apt 4b", category="Housing")
    assert cat("ACH DEBIT", -1200, "Rent for APT 4B", rules=[rule])[0] == "Housing"


def test_p2p_memo_says_what_for_both_directions():
    assert cat("ZELLE PAYMENT TO JORDAN SMITH", -42, "dinner at Ivar's")[:2] == ("Dining", Kind.EXPENSE)
    assert cat("VENMO FROM SAM LEE", 30, "concert tickets")[:2] == ("Entertainment", Kind.REFUND)
    assert cat("ZELLE PAYMENT TO JORDAN SMITH", -42, None)[0] == "Peer-to-Peer"


def test_memo_transfer_is_still_a_transfer():
    assert cat("ACH DEBIT", -500, "ONLINE TRANSFER TO SAV ...4421")[:2] == ("Transfers", Kind.TRANSFER)


# ---- Washington grocery chains ---------------------------------------------------------------

@pytest.mark.parametrize("name", [
    "QFC #5839 SEATTLE WA", "FRED-MEYER #0123 REDMOND WA", "FRED MEYER 00654", "HAGGEN FOOD & PHARMACY 3410",
    "PCC COMMUNITY MARKETS", "METROPOLITAN MARKET #4", "TOWN & COUNTRY MARKET BAINBRIDGE",
    "UWAJIMAYA SEATTLE", "YOKES FRESH MARKET SPOKANE", "ROSAUERS #12", "GROCERY OUTLET 288", "SAFEWAY #1544",
    "WINCO FOODS #92", "TRADER JOE S #130", "WHOLEFDS WLK 10133", "COSTCO WHSE #0001", "CENTRAL MARKET SHORELINE",
    "THRIFTWAY VASHON", "SUPER 1 FOODS", "H MART LYNNWOOD", "ALBERTSONS #580",
])
def test_washington_grocery_chains(name):
    assert cat(name)[0] == "Groceries"          # in the description
    assert cat("POS PURCHASE 1234", -30, name)[0] == "Groceries"  # or only in the memo


def test_store_pharmacy_and_fuel_beat_the_store_name():
    assert cat("COSTCO PHARMACY #1")[0] == "Healthcare"
    assert cat("FRED MEYER FUEL #654")[0] == "Auto & Gas"
    assert cat("COSTCO GAS #0001")[0] == "Auto & Gas"
    assert cat("QFC #5839")[0] == "Groceries"


# ---- Healthcare ----------------------------------------------------------------------------

@pytest.mark.parametrize("name", [
    "CVS/PHARMACY #0921", "WALGREENS #3412", "BARTELL DRUGS #12", "SWEDISH MEDICAL CENTER", "UW MEDICINE BILLING",
    "VIRGINIA MASON", "KAISER PERMANENTE", "ZOOMCARE", "SEATTLE CHILDRENS HOSP", "PACIFIC DENTAL GROUP",
    "LABCORP", "URGENT CARE PLUS", "AMAZON PHARMACY", "GOODRX",
])
def test_healthcare(name):
    assert cat(name)[0] == "Healthcare"


def test_gyms_are_fitness_not_healthcare():
    assert cat("PLANET FITNESS CLUB FEE")[0] == "Fitness"
    assert cat("VITAL CLIMBING GYM")[0] == "Fitness"
    assert "Healthcare" in CATEGORIES and "Fitness" in CATEGORIES and "Health & Fitness" not in CATEGORIES


# ---- every category: recognised in the description, and from the memo alone ---------------

EVERY_CATEGORY = [
    # category, description example, memo-only example (description is "ACH DEBIT" / "POS PURCHASE")
    ("Housing", "RENTCAFE ONLINE PMT", "September rent"),
    ("Utilities", "PUGET SOUND ENERGY", "SEATTLE CITY LIGHT"),
    ("Groceries", "QFC #5839", "TRADER JOE S #552"),
    ("Dining", "DICK'S DRIVE-IN", "MOD PIZZA #12"),
    ("Transportation", "SOUND TRANSIT", "WA STATE FERRIES"),
    ("Auto & Gas", "CHEVRON 0091", "LES SCHWAB TIRE"),
    ("Shopping", "NORDSTROM #12", "REI #11 SEATTLE"),
    ("Subscriptions", "SPOTIFY USA", "NETFLIX.COM"),
    ("Entertainment", "SEATTLE MARINERS", "TICKETMASTER"),
    ("Travel", "ALASKA AIRLINES", "MARRIOTT SEATTLE"),
    ("Healthcare", "SWEDISH MEDICAL", "dentist copay"),
    ("Fitness", "COREPOWER YOGA", "monthly gym"),
    ("Insurance", "PEMCO INSURANCE", "PREMERA BLUE CROSS"),
    ("Education", "UNIVERSITY OF WASHINGTON", "tuition"),
    ("Personal Care", "GREAT CLIPS 1234", "haircut"),
    ("Home", "HOME DEPOT #4702", "MCLENDON HARDWARE"),
    ("Kids & Pets", "MUD BAY #22", "daycare"),
    ("Gifts & Donations", "KEXP DONATION", "birthday gift"),
    ("Services", "PUBLIC STORAGE 2201", "plumber"),
    ("Fees & Interest", "OVERDRAFT FEE", "MONTHLY MAINTENANCE FEE"),
    ("Taxes", "IRS USATAXPYMT", "property tax"),
    ("Cash & ATM", "ATM WITHDRAWAL 0012", "ATM WITHDRAWAL"),
]


def test_every_spending_category_is_covered():
    spending = set(CATEGORIES) - {"Income", "Credit Card Payment", "Transfers", "Uncategorized", "Peer-to-Peer"}
    assert spending == {row[0] for row in EVERY_CATEGORY}


@pytest.mark.parametrize("category,desc,memo", EVERY_CATEGORY)
def test_category_from_description_and_from_memo(category, desc, memo):
    assert cat(desc)[0] == category
    c, kind, source = cat("ACH DEBIT", -25.0, memo)
    assert (c, kind, source) == (category, Kind.EXPENSE, "memo")


@pytest.mark.parametrize("desc,expected", [
    ("PUBLIC STORAGE 2201", "Services"),   # not "PUB" -> Dining
    ("SPANISH TUTOR", "Uncategorized"),    # not "SPA" -> Personal Care
    ("BARTELL DRUGS", "Healthcare"),       # not "BART" -> Transportation
    ("METROPOLITAN MARKET", "Groceries"),  # not "METRO" -> Transportation
    ("SKIN CARE STUDIO", "Personal Care"), # not "SKI" -> Entertainment
])
def test_short_keywords_need_whole_words(desc, expected):
    assert cat(desc)[0] == expected
