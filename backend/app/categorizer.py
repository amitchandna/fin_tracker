"""Turn descriptions into merchants, categories, payment methods and kinds.

Precedence for a category: manual override > user rule > built-in rule >
the bank's own category column > ``Uncategorized``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .models import AccountType, Kind, PaymentMethod

UNCATEGORIZED = "Uncategorized"
CARD_PAYMENT = "Credit Card Payment"
TRANSFERS = "Transfers"
INCOME = "Income"

CATEGORIES = [
    "Housing", "Utilities", "Groceries", "Dining", "Transportation", "Auto & Gas", "Shopping",
    "Subscriptions", "Entertainment", "Travel", "Health & Fitness", "Insurance", "Education",
    "Personal Care", "Home", "Kids & Pets", "Gifts & Donations", "Services", "Fees & Interest",
    "Taxes", "Cash & ATM", "Peer-to-Peer", INCOME, CARD_PAYMENT, TRANSFERS, UNCATEGORIZED,
]

# Categories that never count as spending.
NON_SPENDING = {INCOME, CARD_PAYMENT, TRANSFERS}


@dataclass(frozen=True)
class Rule:
    category: str
    pattern: re.Pattern
    direction: str = "any"  # any | in | out
    kind: Kind | None = None


def _kw(*words: str) -> re.Pattern:
    # Keywords match at word starts so "BP" doesn't match "BPA", but "NETFLIX" matches "NETFLIX.COM".
    return re.compile(r"(?<![A-Z0-9])(?:" + "|".join(re.escape(w).replace(r"\ ", r"\s*") for w in words) + r")", re.I)


BUILTIN_RULES: list[Rule] = [
    # Money moving between your own accounts. Checked first so they never count as spending.
    Rule(CARD_PAYMENT, _kw("PAYMENT THANK YOU", "PAYMENT - THANK YOU", "AUTOPAY PAYMENT", "AUTOMATIC PAYMENT - THANK",
                           "ONLINE PAYMENT THANK", "MOBILE PAYMENT", "PAYMENT RECEIVED", "INTERNET PAYMENT",
                           "ELECTRONIC PAYMENT", "DIRECTPAY FULL BALANCE"), "in", Kind.TRANSFER),
    Rule(CARD_PAYMENT, _kw("CREDIT CRD", "CRD AUTOPAY", "CARD PAYMENT", "CREDIT CARD PAYMENT", "AMEX EPAYMENT",
                           "AMERICAN EXPRESS ACH PMT", "CAPITAL ONE MOBILE PMT", "CAPITAL ONE ONLINE PMT",
                           "CITI AUTOPAY", "DISCOVER E-PAYMENT", "CHASE CARD", "APPLECARD GSBANK", "PAYMENT TO CHASE CARD",
                           "BARCLAYCARD", "SYNCHRONY", "CARDMEMBER SERV"), "out", Kind.TRANSFER),
    Rule("Peer-to-Peer", _kw("VENMO", "ZELLE", "CASH APP", "SQUARE CASH", "PAYPAL TRANSFER", "APPLE CASH")),
    Rule(TRANSFERS, _kw("ONLINE TRANSFER", "TRANSFER TO", "TRANSFER FROM", "INTERNAL TRANSFER", "XFER",
                        "FUNDS TRANSFER", "SAVINGS TRANSFER", "ONLINE BANKING TRANSFER", "TRANSFER TO SAV",
                        "TRANSFER TO CHK", "BROKERAGE", "VANGUARD", "FIDELITY", "SCHWAB", "ROBINHOOD"),
         "any", Kind.TRANSFER),
    # Income
    Rule(INCOME, _kw("PAYROLL", "DIRECT DEP", "DIR DEP", "SALARY", "ADP", "GUSTO", "PAYCHEX", "INTEREST PAID",
                     "INTEREST PAYMENT", "DIVIDEND", "IRS TREAS", "TAX REF", "BONUS", "REIMBURSEMENT"),
         "in", Kind.INCOME),
    # Spending
    Rule("Fees & Interest", _kw("INTEREST CHARGE", "LATE FEE", "ANNUAL FEE", "OVERDRAFT", "NSF FEE",
                                "SERVICE FEE", "FOREIGN TRANSACTION FEE", "MONTHLY MAINTENANCE", "ATM FEE",
                                "FINANCE CHARGE", "WIRE FEE", "PURCHASE INTEREST")),
    Rule("Cash & ATM", _kw("ATM WITHDRAWAL", "ATM WD", "CASH WITHDRAWAL", "ATM CASH", "NON-CHASE ATM")),
    Rule("Subscriptions", _kw("NETFLIX", "SPOTIFY", "HULU", "DISNEY PLUS", "DISNEYPLUS", "DISNEY+", "HBO", "MAX.COM",
                              "PARAMOUNT", "PEACOCK", "YOUTUBE PREMIUM", "YOUTUBEPREMIUM", "GOOGLE *YOUTUBE",
                              "APPLE.COM/BILL", "APPLE.COM BILL", "ITUNES", "ICLOUD", "AUDIBLE", "KINDLE UNLTD",
                              "AMAZON PRIME", "PRIME VIDEO", "AMZN PRIME", "ADOBE", "DROPBOX", "MICROSOFT 365",
                              "MSFT *", "GOOGLE STORAGE", "GOOGLE ONE", "OPENAI", "CHATGPT", "ANTHROPIC",
                              "CLAUDE.AI", "GITHUB", "NOTION", "PATREON", "SUBSTACK", "NYTIMES", "NY TIMES", "WSJ",
                              "SIRIUSXM", "PELOTON", "DUOLINGO", "LINKEDIN PREM", "1PASSWORD", "LASTPASS",
                              "NORDVPN", "EXPRESSVPN", "SLING", "FUBO", "CRUNCHYROLL", "TWITCH")),
    Rule("Housing", _kw("RENT PAYMENT", "RENT PMT", "MONTHLY RENT", "RENTCAFE", "MORTGAGE", "HOA DUES", "HOA FEE", "PROPERTY MGMT", "PROPERTY MANAGEMENT", "APARTMENTS",
                        "LANDLORD", "ZILLOW RENT", "AVAIL RENT", "BILT")),
    Rule("Utilities", _kw("PG&E", "PGE", "CON ED", "CONED", "DUKE ENERGY", "ELECTRIC", "WATER", "GAS CO",
                          "SOCALGAS", "NATIONAL GRID", "XCEL", "EVERSOURCE", "DOMINION", "COMCAST", "XFINITY",
                          "SPECTRUM", "VERIZON", "AT&T", "ATT*", "T-MOBILE", "TMOBILE", "SPRINT", "COX COMM",
                          "OPTIMUM", "FRONTIER", "GOOGLE FI", "MINT MOBILE", "SEWER", "WASTE MGMT",
                          "WASTE MANAGEMENT", "REPUBLIC SERVICES", "UTILITY", "UTILITIES", "INTERNET")),
    Rule("Insurance", _kw("GEICO", "STATE FARM", "PROGRESSIVE", "ALLSTATE", "LIBERTY MUTUAL", "USAA INS",
                          "FARMERS INS", "NATIONWIDE", "LEMONADE", "INSURANCE", "METLIFE", "AFLAC")),
    Rule("Groceries", _kw("WHOLE FOODS", "WHOLEFDS", "TRADER JOE", "SAFEWAY", "KROGER", "PUBLIX", "ALDI",
                          "COSTCO", "SPROUTS", "WEGMANS", "HEB", "H-E-B", "FOOD LION", "GIANT EAGLE", "STOP & SHOP",
                          "STOP AND SHOP", "ALBERTSONS", "RALPHS", "VONS", "MEIJER", "HARRIS TEETER", "INSTACART",
                          "GROCERY", "GROCERIES", "SUPERMARKET", "MARKET BASKET", "FOOD 4 LESS", "WINCO",
                          "SHOPRITE", "HANNAFORD", "LIDL", "FRESH MARKET", "99 RANCH", "H MART")),
    Rule("Dining", _kw("RESTAURANT", "STARBUCKS", "DUNKIN", "MCDONALD", "CHIPOTLE", "SUBWAY", "TACO BELL",
                       "WENDY", "BURGER KING", "CHICK-FIL-A", "CHICKFILA", "PANERA", "DOMINO", "PIZZA",
                       "DOORDASH", "UBER EATS", "UBEREATS", "GRUBHUB", "POSTMATES", "SEAMLESS", "CAFE", "COFFEE",
                       "BAKERY", "BAR & GRILL", "GRILL", "DINER", "SUSHI", "TST*", "TOAST", "SWEETGREEN",
                       "SHAKE SHACK", "IN-N-OUT", "FIVE GUYS", "BLUE BOTTLE", "PEET", "TIM HORTONS",
                       "KITCHEN", "TAQUERIA", "BREWING", "BREWERY", "PUB", "BISTRO", "EATERY", "STEAKHOUSE",
                       "RAMEN", "THAI", "BBQ")),
    Rule("Auto & Gas", _kw("SHELL", "CHEVRON", "EXXON", "MOBIL", "BP#", "BP ", "ARCO", "SUNOCO", "CITGO",
                           "VALERO", "MARATHON", "SPEEDWAY", "WAWA", "QUIKTRIP", "CIRCLE K", "7-ELEVEN",
                           "GAS STATION", "FUEL", "JIFFY LUBE", "AUTOZONE", "O'REILLY", "PEP BOYS", "CAR WASH",
                           "DMV", "TESLA SUPERCHARGER", "CHARGEPOINT", "EVGO", "FIRESTONE", "DISCOUNT TIRE")),
    Rule("Transportation", _kw("UBER", "LYFT", "METRO", "MTA", "BART", "CALTRAIN", "AMTRAK", "TRANSIT",
                               "PARKING", "PARKMOBILE", "SPOTHERO", "TOLL", "E-ZPASS", "EZPASS", "FASTRAK",
                               "SUNPASS", "CLIPPER", "VENTRA", "LIME*", "LIME RIDE", "BIRD APP", "CITI BIKE", "TAXI")),
    Rule("Travel", _kw("AIRLINE", "AIRLINES", "DELTA AIR", "UNITED AIR", "AMERICAN AIR", "SOUTHWEST", "JETBLUE",
                       "ALASKA AIR", "SPIRIT AIR", "FRONTIER AIR", "AIR CANADA", "MARRIOTT", "HILTON", "HYATT",
                       "IHG", "HOLIDAY INN", "BEST WESTERN", "AIRBNB", "VRBO", "EXPEDIA", "BOOKING.COM",
                       "HOTELS.COM", "KAYAK", "PRICELINE", "HERTZ", "AVIS", "ENTERPRISE RENT", "BUDGET RENT",
                       "NATIONAL CAR", "HOTEL", "RESORT", "TSA PRECHECK", "CLEAR ME")),
    Rule("Health & Fitness", _kw("CVS", "WALGREENS", "RITE AID", "PHARMACY", "DENTAL", "DENTIST", "MEDICAL",
                                 "HOSPITAL", "CLINIC", "DOCTOR", "OPTOMETR", "VISION", "LABCORP", "QUEST DIAG",
                                 "KAISER", "GYM", "FITNESS", "PLANET FITNESS", "EQUINOX", "ORANGETHEORY", "YMCA",
                                 "CLASSPASS", "SOULCYCLE", "24 HOUR FIT", "LA FITNESS", "CRUNCH", "THERAPY",
                                 "HEALTH")),
    Rule("Entertainment", _kw("AMC", "REGAL", "CINEMA", "CINEMARK", "THEATER", "THEATRE", "TICKETMASTER",
                              "STUBHUB", "SEATGEEK", "EVENTBRITE", "LIVE NATION", "STEAM", "PLAYSTATION", "XBOX",
                              "NINTENDO", "BOWLING", "MUSEUM", "CONCERT", "GOLF", "ZOO")),
    Rule("Shopping", _kw("AMAZON", "AMZN", "TARGET", "WALMART", "WAL-MART", "BEST BUY", "BESTBUY", "EBAY",
                         "ETSY", "APPLE STORE", "MACY", "NORDSTROM", "KOHL", "TJ MAXX", "TJMAXX", "MARSHALLS",
                         "ROSS STORES", "OLD NAVY", "GAP", "H&M", "ZARA", "UNIQLO", "NIKE", "ADIDAS", "SEPHORA",
                         "ULTA", "IKEA", "WAYFAIR", "HOME DEPOT", "LOWE", "BED BATH", "DOLLAR TREE", "DOLLAR GENERAL",
                         "SHEIN", "TEMU", "SHOPIFY", "PAYPAL *", "SQ *")),
    Rule("Personal Care", _kw("SALON", "BARBER", "HAIR", "SPA", "NAIL", "MASSAGE", "GREAT CLIPS", "SUPERCUTS",
                              "DRY CLEAN", "LAUNDRY")),
    Rule("Education", _kw("TUITION", "UNIVERSITY", "COLLEGE", "SCHOOL", "COURSERA", "UDEMY", "SKILLSHARE",
                          "MASTERCLASS", "STUDENT LOAN", "NAVIENT", "NELNET", "BOOKSTORE")),
    Rule("Kids & Pets", _kw("PETCO", "PETSMART", "CHEWY", "VETERINARY", "VET ", "DAYCARE", "CHILDCARE",
                            "BABYSIT", "TOYS")),
    Rule("Gifts & Donations", _kw("DONATION", "CHARITY", "GOFUNDME", "RED CROSS", "UNICEF", "CHURCH",
                                  "FOUNDATION", "GIFT")),
    Rule("Taxes", _kw("IRS", "TAX PAYMENT", "FRANCHISE TAX", "DEPT OF REVENUE", "STATE TAX", "PROPERTY TAX")),
    Rule("Services", _kw("TASKRABBIT", "THUMBTACK", "ANGI", "HANDY", "CLEANING", "PLUMB", "ELECTRICIAN",
                         "LAWN", "LANDSCAP", "PEST", "STORAGE", "UPS STORE", "USPS", "FEDEX", "POSTAGE", "LEGAL",
                         "ATTORNEY", "ACCOUNTING")),
]

# Mapping of the bank's own category text (lower-cased substring) to ours.
SOURCE_CATEGORY_MAP: list[tuple[str, str]] = [
    ("grocer", "Groceries"), ("supermarket", "Groceries"),
    ("restaurant", "Dining"), ("food & drink", "Dining"), ("dining", "Dining"), ("fast food", "Dining"),
    ("coffee", "Dining"), ("bar", "Dining"),
    ("gas", "Auto & Gas"), ("fuel", "Auto & Gas"), ("automotive", "Auto & Gas"), ("auto", "Auto & Gas"),
    ("travel", "Travel"), ("airline", "Travel"), ("lodging", "Travel"), ("hotel", "Travel"),
    ("transport", "Transportation"), ("parking", "Transportation"), ("taxi", "Transportation"),
    ("utilit", "Utilities"), ("bills", "Utilities"), ("phone", "Utilities"), ("internet", "Utilities"),
    ("cable", "Utilities"),
    ("health", "Health & Fitness"), ("medical", "Health & Fitness"), ("pharmac", "Health & Fitness"),
    ("fitness", "Health & Fitness"),
    ("entertain", "Entertainment"), ("recreation", "Entertainment"),
    ("insurance", "Insurance"), ("education", "Education"),
    ("personal", "Personal Care"), ("home", "Home"), ("pet", "Kids & Pets"), ("child", "Kids & Pets"),
    ("gift", "Gifts & Donations"), ("donation", "Gifts & Donations"), ("charit", "Gifts & Donations"),
    ("fee", "Fees & Interest"), ("interest", "Fees & Interest"), ("professional", "Services"),
    ("service", "Services"), ("tax", "Taxes"), ("rent", "Housing"), ("mortgage", "Housing"),
    ("subscription", "Subscriptions"), ("streaming", "Subscriptions"),
    ("merchandise", "Shopping"), ("shopping", "Shopping"), ("retail", "Shopping"), ("clothing", "Shopping"),
    ("electronics", "Shopping"),
    ("payment", CARD_PAYMENT), ("transfer", TRANSFERS), ("income", INCOME), ("paycheck", INCOME),
]

_NOISE_PREFIXES = re.compile(
    r"^(POS\s+(PURCHASE|DEBIT)?|DEBIT\s+CARD\s+PURCHASE|DEBIT\s+PURCHASE|PURCHASE\s+AUTHORIZED\s+ON\s+\S+|"
    r"PURCHASE|CHECKCARD\s+\d*|CHECK\s+CARD|RECURRING\s+(PAYMENT|DEBIT)?|ACH\s+(DEBIT|WITHDRAWAL|PMT)?|"
    r"PREAUTHORIZED\s+DEBIT|ELECTRONIC\s+WITHDRAWAL|SQ\s*\*|TST\s*\*|SP\s*\*|PAYPAL\s*\*|PP\s*\*|"
    r"DD\s*\*|GOOGLE\s*\*|AMZN\s+MKTP\s+US\s*\*?|WWW\.)\s*",
    re.I,
)
_US_STATES = (
    "AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND "
    "OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC"
).split()


def normalize_merchant(description: str) -> str:
    """Strip noise (card prefixes, store numbers, dates, phone numbers, locations)
    so repeated charges from the same merchant group together."""
    d = description.upper().strip()
    # Peer-to-peer: who the money went to / came from is what matters.
    p2p = re.match(r"^(ZELLE|VENMO|CASH APP|PAYPAL)\b.*?\b(FROM|TO)\s+([A-Z][A-Z'.-]*(?:\s+[A-Z][A-Z'.-]*)?)", d)
    if p2p:
        return f"{p2p.group(1)} {p2p.group(2)} {p2p.group(3)}".title()
    for _ in range(3):
        new = _NOISE_PREFIXES.sub("", d)
        if new == d:
            break
        d = new
    d = re.sub(r"\b(PPD|CCD|WEB|TEL)\s+ID\b.*$|\b(PPD|CCD|DES|INDN|CO ID|ID)\s*:.*$", " ", d)  # ACH trailers
    d = re.sub(r"\b\d{1,2}/\d{1,2}(/\d{2,4})?\b", " ", d)  # dates
    d = re.sub(r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b", " ", d)  # phone numbers
    d = re.sub(r"\.(COM|NET|ORG|CO)\b", " ", d)
    d = re.sub(r"[#*]\s*\S*\d\S*", " ", d)  # "#1234", "*AB12CD"
    d = re.sub(r"\b[A-Z]*\d[A-Z0-9]*\b", " ", d)  # tokens containing digits (ref numbers)
    d = re.sub(r"[^A-Z&' ]+", " ", d)
    tokens = d.split()
    while len(tokens) > 1 and tokens[-1] in _US_STATES:
        tokens.pop()
    tokens = [t for t in tokens if t not in {"INC", "LLC", "CO", "CORP", "LTD", "THE", "US", "USA", "ONLINE"}] or tokens
    merchant = " ".join(tokens[:3]).strip()
    return merchant.title() if merchant else description.strip()[:40]


def detect_payment_method(description: str, account_type: AccountType) -> PaymentMethod:
    if account_type == AccountType.CREDIT_CARD:
        return PaymentMethod.CREDIT
    d = description.upper()
    if re.search(r"\bATM\b|CASH WITHDRAWAL", d):
        return PaymentMethod.CASH
    if re.search(r"^CHECK\b|^CHK\b|\bCHECK\s*#|\bCHECK\s+\d+|^DEPOSITED CHECK", d):
        return PaymentMethod.CHECK
    if re.search(r"\bACH\b|ZELLE|VENMO|PAYPAL|\bWIRE\b|TRANSFER|XFER|ONLINE PMT|BILL\s*PAY|EPAY|DIRECT DEP|"
                 r"PAYROLL|AUTOPAY|WEB PMT|PPD|CCD", d):
        return PaymentMethod.TRANSFER
    return PaymentMethod.DEBIT


@dataclass
class UserRule:
    id: str
    pattern: str
    category: str
    match: str = "contains"  # contains | regex | merchant (exact merchant name, as shown in the app)
    kind: str | None = None  # optionally force a kind (expense / income / transfer / refund)
    exclude: bool = False  # drop matching transactions from budget totals
    direction: str = "any"  # any | in (money in only) | out (money out only)

    def matches(self, description: str) -> bool:
        if self.match == "merchant":
            return normalize_merchant(description).lower() == self.pattern.strip().lower()
        pat = self.compiled()
        return bool(pat and pat.search(description))

    def compiled(self) -> re.Pattern | None:
        try:
            if self.match == "regex":
                return re.compile(self.pattern, re.I)
            return re.compile(re.escape(self.pattern.strip()), re.I)
        except re.error:
            return None

    def to_dict(self) -> dict:
        return {"id": self.id, "pattern": self.pattern, "category": self.category,
                "match": self.match, "kind": self.kind, "exclude": self.exclude, "direction": self.direction}


@dataclass
class Classification:
    category: str
    kind: Kind
    category_source: str
    excluded: bool = False


def _map_source_category(source_category: str | None) -> str | None:
    if not source_category:
        return None
    sc = source_category.lower()
    for key, cat in SOURCE_CATEGORY_MAP:
        if key in sc:
            return cat
    return None


def _default_kind(amount: float, account_type: AccountType, description: str) -> Kind:
    if amount < 0:
        return Kind.EXPENSE
    # Money in.
    if re.search(r"REFUND|RETURN|REVERSAL|CREDIT ADJ|CASHBACK|CASH BACK|REBATE|STATEMENT CREDIT", description, re.I):
        return Kind.REFUND
    if account_type == AccountType.CREDIT_CARD:
        return Kind.REFUND
    return Kind.INCOME


def classify(description: str, amount: float, account_type: AccountType, source_category: str | None,
             user_rules: list[UserRule]) -> Classification:
    direction = "in" if amount > 0 else "out"

    for rule in user_rules:
        if rule.direction != "any" and rule.direction != direction:
            continue
        if rule.matches(description):
            kind = Kind(rule.kind) if rule.kind in Kind._value2member_map_ else None
            if kind is None:
                if rule.category in (CARD_PAYMENT, TRANSFERS):
                    kind = Kind.TRANSFER
                elif rule.category == INCOME and amount > 0:
                    kind = Kind.INCOME
                elif amount > 0:
                    # Money in filed under a spending category is someone paying you back.
                    kind = Kind.REFUND
                else:
                    kind = Kind.EXPENSE
            return Classification(rule.category, kind, "rule", excluded=rule.exclude)

    for rule in BUILTIN_RULES:
        if rule.direction != "any" and rule.direction != direction:
            continue
        if rule.pattern.search(description):
            kind = rule.kind or _default_kind(amount, account_type, description)
            return Classification(rule.category, kind, "auto")

    mapped = _map_source_category(source_category)
    if mapped:
        if mapped in (CARD_PAYMENT, TRANSFERS):
            return Classification(mapped, Kind.TRANSFER, "source")
        if mapped == INCOME:
            return Classification(mapped, Kind.INCOME if amount > 0 else Kind.EXPENSE, "source")
        return Classification(mapped, _default_kind(amount, account_type, description), "source")

    kind = _default_kind(amount, account_type, description)
    if kind == Kind.INCOME:
        return Classification(INCOME, kind, "auto")
    return Classification(UNCATEGORIZED, kind, "auto")
