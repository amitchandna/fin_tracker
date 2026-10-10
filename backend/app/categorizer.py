"""Turn descriptions into merchants, categories, payment methods and kinds.

Precedence for a category: manual override > user rule > built-in rule >
the bank's own category column > ``Uncategorized``.
"""

from __future__ import annotations

import re
import string
from dataclasses import dataclass

from .models import AccountType, Kind, PaymentMethod

UNCATEGORIZED = "Uncategorized"
CARD_PAYMENT = "Credit Card Payment"
TRANSFERS = "Transfers"
INCOME = "Income"

CATEGORIES = [
    "Housing", "Utilities", "Groceries", "Dining", "Transportation", "Auto & Gas", "Shopping",
    "Subscriptions", "Entertainment", "Travel", "Healthcare", "Fitness", "Insurance", "Education",
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
    """Keywords match at word starts, so "BP" doesn't match "ABP" but "NETFLIX" matches "NETFLIX.COM".
    A keyword ending in a space must also end at a word boundary: "QFC " matches "QFC #5839" but
    not "QFCX"; "PUB " matches "THE PUB" but not "PUBLIC STORAGE"."""
    parts = []
    for w in words:
        core = w.rstrip()
        pat = re.escape(core).replace(r"\ ", r"\s*")
        if core != w:
            pat += r"(?![A-Z0-9])"
        parts.append(pat)
    return re.compile(r"(?<![A-Z0-9])(?:" + "|".join(parts) + r")", re.I)


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
                        "TRANSFER TO CHK", "BROKERAGE", "VANGUARD", "FIDELITY", "CHARLES SCHWAB", "SCHWAB BROK",
                        "SCHWAB MONEYLINK", "ROBINHOOD"),
         "any", Kind.TRANSFER),
    # Income
    Rule(INCOME, _kw("PAYROLL", "DIRECT DEP", "DIR DEP", "SALARY", "ADP", "GUSTO", "PAYCHEX", "INTEREST PAID",
                     "INTEREST PAYMENT", "DIVIDEND", "IRS TREAS", "TAX REF", "BONUS", "REIMBURSEMENT"),
         "in", Kind.INCOME),
    # Spending. Order matters: the first match wins, so specific rules come before broad ones.
    Rule("Fees & Interest", _kw("INTEREST CHARGE", "LATE FEE", "ANNUAL FEE", "OVERDRAFT", "NSF FEE",
                                "SERVICE FEE", "FOREIGN TRANSACTION FEE", "INTL TRANSACTION FEE", "MONTHLY MAINTENANCE",
                                "ATM FEE", "FINANCE CHARGE", "WIRE FEE", "PURCHASE INTEREST", "CASH ADVANCE FEE",
                                "RETURNED ITEM", "STOP PAYMENT FEE", "PAPER STATEMENT FEE", "MINIMUM BALANCE FEE",
                                "INTEREST CHARGED", "MAINTENANCE FEE", "EXCESS WITHDRAWAL")),
    Rule("Cash & ATM", _kw("ATM WITHDRAWAL", "ATM WD", "CASH WITHDRAWAL", "ATM CASH", "NON-CHASE ATM")),
    # Pharmacies and fuel inside grocery / big-box stores, before the store name claims them.
    Rule("Healthcare", _kw("COSTCO PHARMACY", "COSTCO PHARM", "SAFEWAY PHARMACY", "FRED MEYER PHARMACY",
                           "FRED M PHARMACY", "QFC PHARMACY", "ALBERTSONS PHARMACY", "WALMART PHARMACY",
                           "TARGET PHARMACY", "KROGER PHARMACY", "AMAZON PHARMACY", "HAGGEN PHARMACY")),
    Rule("Auto & Gas", _kw("COSTCO GAS", "COSTCO FUEL", "FRED MEYER FUEL", "FRED M FUEL", "FRED-MEYER FUEL",
                           "SAFEWAY FUEL", "QFC FUEL", "ALBERTSONS FUEL", "KROGER FUEL", "WALMART FUEL",
                           "SAMS CLUB FUEL", "HAGGEN FUEL")),
    # Grocery stores whose name includes "pharmacy" (the general pharmacy rule would claim them).
    Rule("Groceries", _kw("HAGGEN FOOD", "FOOD & PHARMACY", "FOOD AND PHARMACY", "FOOD & PHARM", "FOOD & DRUG")),
    Rule("Subscriptions", _kw("NETFLIX", "SPOTIFY", "HULU", "DISNEY PLUS", "DISNEYPLUS", "DISNEY+", "HBO", "MAX.COM",
                              "PARAMOUNT+", "PARAMOUNT PLUS", "PEACOCK", "YOUTUBE PREMIUM", "YOUTUBEPREMIUM",
                              "YOUTUBE TV", "GOOGLE *YOUTUBE", "APPLE.COM/BILL", "APPLE.COM BILL", "APPLE ONE",
                              "APPLE MUSIC", "APPLE TV", "ITUNES", "ICLOUD", "AUDIBLE", "KINDLE UNLTD",
                              "AMAZON PRIME", "PRIME VIDEO", "AMZN PRIME", "ADOBE", "DROPBOX", "MICROSOFT 365",
                              "MSFT *", "GOOGLE STORAGE", "GOOGLE ONE", "OPENAI", "CHATGPT", "ANTHROPIC",
                              "CLAUDE.AI", "GITHUB", "NOTION", "PATREON", "SUBSTACK", "NYTIMES", "NY TIMES", "WSJ",
                              "WASHINGTON POST", "WAPO", "SEATTLE TIMES", "THE ATHLETIC", "ECONOMIST", "NEW YORKER",
                              "SIRIUSXM", "PANDORA", "TIDAL", "ESPN+", "ESPN PLUS", "DAZN", "PHILO", "STARZ",
                              "SHOWTIME", "MUBI", "CRUNCHYROLL", "TWITCH", "SLING", "FUBO", "PELOTON", "DUOLINGO",
                              "LINKEDIN PREM", "1PASSWORD", "LASTPASS", "NORDVPN", "EXPRESSVPN", "CANVA",
                              "GRAMMARLY", "ZOOM.US", "EVERNOTE", "HEADSPACE", "CALM.COM", "NOOM", "XBOX GAME PASS",
                              "PLAYSTATION PLUS", "NINTENDO ONLINE", "MEDIUM.COM", "SUBSCRIPTION")),
    Rule("Housing", _kw("RENT PAYMENT", "RENT PMT", "MONTHLY RENT", "RENTCAFE", "MORTGAGE", "HOA DUES", "HOA FEE",
                        "PROPERTY MGMT", "PROPERTY MGT", "PROPERTY MANAGEMENT", "APARTMENTS", "APARTMENT ",
                        "LEASING OFFICE", "LANDLORD", "ZILLOW RENT", "AVAIL RENT", "BILT", "APPFOLIO", "BUILDIUM",
                        "CLICKPAY", "RENTPAYMENT", "GREYSTAR", "EQUITY RESIDENTIAL", "ESSEX PROPERTY", "AVALONBAY",
                        "ROCKET MORTGAGE", "MR COOPER", "MR. COOPER", "PENNYMAC", "LOANCARE", "HOME MTG",
                        "HOME LOAN", "WELLS FARGO HOME")),
    Rule("Utilities", _kw("PG&E", "PGE", "CON ED", "CONED", "DUKE ENERGY", "ELECTRIC", "WATER", "GAS CO",
                          "SOCALGAS", "NATIONAL GRID", "XCEL", "EVERSOURCE", "DOMINION", "COMCAST", "XFINITY",
                          "SPECTRUM", "VERIZON", "AT&T", "ATT*", "T-MOBILE", "TMOBILE", "SPRINT", "COX COMM",
                          "OPTIMUM", "FRONTIER COMM", "GOOGLE FI", "MINT MOBILE", "VISIBLE ", "CRICKET",
                          "US MOBILE", "BOOST MOBILE", "METRO BY T", "SEWER", "WASTE MGMT", "WASTE MANAGEMENT",
                          "REPUBLIC SERVICES", "RECOLOGY", "WASTE CONNECTIONS", "CENTURYLINK", "LUMEN ",
                          "WAVE BROADBAND", "ASTOUND", "STARLINK", "UTILITY", "UTILITIES", "INTERNET",
                          # Washington / Pacific Northwest
                          "PUGET SOUND EN", "PUGET SOUND ENERGY", "SEATTLE CITY LIGHT", "SEATTLE PUBLIC UTIL",
                          "CITY OF SEATTLE UTIL", "TACOMA PUBLIC UTIL", "TACOMA POWER", "SNOHOMISH COUNTY PUD",
                          "SNOPUD", "CLARK PUBLIC UTIL", "BENTON PUD", "MASON PUD", "AVISTA", "ZIPLY",
                          "CASCADE NATURAL GAS", "NW NATURAL", "PACIFIC POWER", "PACIFICORP", "PSE ")),
    Rule("Insurance", _kw("GEICO", "STATE FARM", "PROGRESSIVE", "ALLSTATE", "LIBERTY MUTUAL", "USAA INS",
                          "FARMERS INS", "NATIONWIDE", "LEMONADE", "INSURANCE", "METLIFE", "AFLAC", "PEMCO",
                          "SAFECO", "AMERICAN FAMILY", "TRAVELERS INS", "ROOT INS", "HIPPO INS", "PREMERA",
                          "REGENCE", "AETNA", "CIGNA", "UNITEDHEALTH", "UNITED HEALTHCARE", "BLUE CROSS",
                          "BLUE SHIELD", "HUMANA", "MOLINA", "DELTA DENTAL", "VSP VISION", "NORTHWESTERN MUTUAL",
                          "NEW YORK LIFE", "PRUDENTIAL", "GUARDIAN LIFE", "LIFE INS")),
    # Doctor's visits, pharmacies, dental, vision, therapy, labs.
    Rule("Healthcare", _kw("CVS ", "CVS/", "WALGREENS", "RITE AID", "BARTELL", "PHARMACY", "PHARM ", "DRUG STORE",
                           "DRUGSTORE", "DENTAL", "DENTIST", "ORTHODONT", "MEDICAL", "MEDICINE", "HOSPITAL",
                           "CLINIC", "DOCTOR", "PHYSICIAN", "PEDIATRIC", "DERMATOLOG", "OPTOMETR", "OPHTHALM",
                           "VISION", "EYE CARE", "EYECARE", "LENSCRAFTERS", "WARBY PARKER", "LABCORP", "QUEST DIAG",
                           "KAISER", "URGENT CARE", "URGENTCARE", "THERAPY", "THERAPIST", "COUNSELING",
                           "PSYCHIATR", "PSYCHOLOG", "CHIROPRACT", "ACUPUNCT", "PHYSICAL THERAPY", "RADIOLOGY",
                           "IMAGING", "ANESTHESI", "SURGERY", "SURGICAL", "OBGYN", "OB/GYN", "MIDWIFE",
                           "HEALTHEQUITY", "HEALTH EQUITY", "HSA BANK", "GOODRX", "CAPSULE RX", "TELADOC",
                           "ONE MEDICAL", "1LIFE", "ZOOMCARE", "MINUTECLINIC", "COPAY", "HEALTHCARE", "HEALTH CARE",
                           # Washington health systems
                           "SWEDISH", "PROVIDENCE", "UW MEDICINE", "UW MEDICAL", "UWMC", "HARBORVIEW",
                           "VIRGINIA MASON", "MULTICARE", "EVERGREENHEALTH", "EVERGREEN HEALTH", "OVERLAKE",
                           "SEATTLE CHILDREN", "POLYCLINIC", "PACMED", "PACIFIC MEDICAL", "VALLEY MEDICAL",
                           "KAISER PERMANENTE", "FRANCISCAN", "PEACEHEALTH", "CONFLUENCE HEALTH", "HEALTH")),
    Rule("Fitness", _kw("GYM", "FITNESS", "PLANET FITNESS", "EQUINOX", "ORANGETHEORY", "ORANGE THEORY", "YMCA",
                        "CLASSPASS", "SOULCYCLE", "24 HOUR FIT", "LA FITNESS", "CRUNCH", "GOLD'S GYM", "GOLDS GYM",
                        "ANYTIME FITNESS", "CROSSFIT", "F45", "YOGA", "PILATES", "BARRE", "COREPOWER",
                        "CORE POWER", "CLIMBING", "BOULDERING", "EDGEWORKS", "VITAL CLIMBING", "STONE GARDENS",
                        "SEATTLE ATHLETIC", "WASHINGTON ATHLETIC", "PRO CLUB", "PRO SPORTS CLUB", "STRAVA",
                        "ZWIFT", "ATHLETIC CLUB", "SWIM ", "AQUATIC", "MARTIAL ARTS", "BOXING")),
    Rule("Groceries", _kw("WHOLE FOODS", "WHOLEFDS", "WHOLE FDS", "TRADER JOE", "SAFEWAY", "KROGER", "PUBLIX",
                          "ALDI ", "COSTCO", "SPROUTS", "WEGMANS", "HEB ", "H-E-B", "FOOD LION", "GIANT EAGLE",
                          "STOP & SHOP", "STOP AND SHOP", "ALBERTSON", "RALPHS", "VONS", "MEIJER", "HARRIS TEETER",
                          "INSTACART", "AMAZON FRESH", "AMZN FRESH", "GROCERY", "GROCERIES", "SUPERMARKET",
                          "MARKET BASKET", "FOOD 4 LESS", "WINCO", "SHOPRITE", "HANNAFORD", "LIDL", "FRESH MARKET",
                          "99 RANCH", "H MART", "HMART", "SMART & FINAL", "SAMS CLUB", "SAM'S CLUB", "BJS WHOLESALE",
                          "HELLOFRESH", "BLUE APRON", "HOME CHEF", "FACTOR75", "THRIVE MARKET", "MISFITS MARKET",
                          "IMPERFECT FOODS", "WEEE", "FOOD CO-OP", "FOOD COOP", "BUTCHER", "BAKERY OUTLET",
                          # Washington state / Pacific Northwest chains
                          "QFC ", "QUALITY FOOD CENTER", "FRED MEYER", "FRED-MEYER", "FREDMEYER", "FRED M ",
                          "HAGGEN", "PCC COMMUNITY", "PCC NATURAL", "PCC MKT", "PCC MARKET", "METROPOLITAN MARKET",
                          "METROPOLITAN MKT", "MET MARKET", "TOWN & COUNTRY MARKET", "TOWN AND COUNTRY MARKET",
                          "TOWN & COUNTRY MKT", "UWAJIMAYA", "YOKES", "YOKE'S", "ROSAUERS", "GROCERY OUTLET",
                          "SUPER 1 FOODS", "SAARS", "THRIFTWAY", "CENTRAL MARKET", "BALLARD MARKET",
                          "RED APPLE MARKET", "NEW SEASONS", "MARKET OF CHOICE", "CASH & CARRY", "CHEF'STORE",
                          "CHEFSTORE", "SMART FOODSERVICE", "FOOD PAVILION", "HARVEST FOODS", "WALMART NEIGHBORHOOD")),
    Rule("Dining", _kw("RESTAURANT", "STARBUCKS", "DUNKIN", "MCDONALD", "CHIPOTLE", "SUBWAY", "TACO BELL",
                       "WENDY", "BURGER KING", "CHICK-FIL-A", "CHICKFILA", "PANERA", "DOMINO", "PIZZA",
                       "DOORDASH", "UBER EATS", "UBEREATS", "GRUBHUB", "POSTMATES", "SEAMLESS", "CAVIAR", "CAFE",
                       "COFFEE", "ESPRESSO", "ROASTER", "BAKERY", "BAR & GRILL", "GRILL", "DINER", "SUSHI", "TST*",
                       "TOAST", "SWEETGREEN", "SHAKE SHACK", "IN-N-OUT", "FIVE GUYS", "BLUE BOTTLE", "PEET",
                       "TIM HORTONS", "KITCHEN", "TAQUERIA", "BREWING", "BREWERY", "TAPROOM", "PUB ", "BISTRO",
                       "EATERY", "STEAKHOUSE", "RAMEN", "THAI ", "BBQ", "PHO ", "TERIYAKI", "DIM SUM", "NOODLE",
                       "DELI ", "TAVERN", "SALOON", "CANTINA", "BURGER", "WINGS", "WINGSTOP", "JACK IN THE BOX",
                       "ARBY", "POPEYES", "KFC ", "SONIC DRIVE", "PANDA EXPRESS", "OLIVE GARDEN", "APPLEBEE",
                       "CHILI'S", "RED ROBIN", "IHOP", "DENNY", "CHEESECAKE FACTORY", "PF CHANG", "P.F. CHANG",
                       "JIMMY JOHN", "JERSEY MIKE", "FIREHOUSE SUBS", "QDOBA", "CAVA ", "NOODLES &",
                       "BUFFALO WILD", "CARIBOU", "SMOOTHIE", "JAMBA", "BOBA", "ICE CREAM", "GELATO", "DONUT",
                       "DOUGHNUT", "BAGEL",
                       # Pacific Northwest
                       "DICKS DRIVE", "DICK'S DRIVE", "IVAR", "TOM DOUGLAS", "MOD PIZZA", "MOD SUPER", "TACO TIME",
                       "BURGERVILLE", "DUTCH BROS", "TULLY", "CAFFE LADRO", "CAFFE VITA", "VICTROLA",
                       "STUMPTOWN", "ZEEKS", "PAGLIACCI", "PIROSHKY", "MOLLY MOON", "SALT & STRAW", "RAINIER BEER",
                       "ELYSIAN", "FREMONT BREW", "UMAMI KUSHI")),
    Rule("Auto & Gas", _kw("SHELL ", "SHELL OIL", "CHEVRON", "EXXON", "MOBIL ", "BP#", "BP ", "ARCO ", "SUNOCO",
                           "CITGO", "VALERO", "MARATHON PETRO", "SPEEDWAY", "WAWA", "QUIKTRIP", "CIRCLE K", "7-ELEVEN",
                           "76 ", "PHILLIPS 66", "CONOCO", "TEXACO", "SINCLAIR", "GAS STATION", "FUEL", "JIFFY LUBE",
                           "VALVOLINE", "MIDAS", "MEINEKE", "LES SCHWAB", "AUTOZONE", "O'REILLY", "NAPA AUTO",
                           "PEP BOYS", "CAR WASH", "BRADLEY CAR", "BRANDS CAR", "DMV", "DEPT OF LICENSING",
                           "DOL ", "EMISSIONS", "TESLA SUPERCHARGER", "TESLA", "CHARGEPOINT", "EVGO",
                           "ELECTRIFY AMERICA", "BLINK CHARGING", "FIRESTONE", "DISCOUNT TIRE", "BIG O TIRES",
                           "TOYOTA MOTOR CREDIT", "TOYOTA FINANCIAL", "HONDA FINANCIAL", "AMERICAN HONDA FIN",
                           "SUBARU MOTORS FIN", "FORD CREDIT", "GM FINANCIAL", "ALLY AUTO", "AUTO LOAN",
                           "CAR PAYMENT", "CARMAX", "CARVANA")),
    Rule("Transportation", _kw("UBER", "LYFT", "METRO TRANSIT", "KING COUNTY METRO", "SOUND TRANSIT", "ORCA ",
                               "WSDOT", "GOOD TO GO", "GOODTOGO", "WA STATE FERR", "WASHINGTON STATE FERR", "WSF ",
                               "COMMUNITY TRANSIT", "PIERCE TRANSIT", "SEATTLE STREETCAR", "TRIMET", "MTA ", "BART ",
                               "CALTRAIN", "AMTRAK", "TRANSIT", "GREYHOUND", "PARKING", "PARKMOBILE", "PAYBYPHONE",
                               "SPOTHERO", "DIAMOND PARK", "IMPARK", "REEF PARKING", "LAZ PARKING", "ABM PARKING",
                               "TOLL", "E-ZPASS", "EZPASS", "FASTRAK", "SUNPASS", "CLIPPER", "VENTRA", "LIME*",
                               "LIME RIDE", "BIRD APP", "CITI BIKE", "REVEL", "WAYMO", "TAXI", "YELLOW CAB")),
    Rule("Travel", _kw("AIRLINE", "AIRLINES", "DELTA AIR", "UNITED AIR", "AMERICAN AIR", "SOUTHWEST", "JETBLUE",
                       "ALASKA AIR", "HORIZON AIR", "SPIRIT AIR", "FRONTIER AIR", "AIR CANADA", "HAWAIIAN AIR",
                       "SUN COUNTRY", "ALLEGIANT", "BRITISH AIRWAYS", "LUFTHANSA", "MARRIOTT", "HILTON", "HYATT",
                       "IHG", "HOLIDAY INN", "HAMPTON INN", "BEST WESTERN", "WESTIN", "SHERATON", "LA QUINTA",
                       "MOTEL", "INN ", "LODGE ", "HOSTEL", "AIRBNB", "VRBO", "EXPEDIA", "BOOKING.COM", "HOTELS.COM",
                       "KAYAK", "PRICELINE", "HOPPER", "TRIP.COM", "HERTZ", "AVIS", "ENTERPRISE RENT", "BUDGET RENT",
                       "NATIONAL CAR", "ALAMO", "SIXT", "THRIFTY", "DOLLAR RENT", "TURO", "HOTEL", "RESORT",
                       "TSA PRECHECK", "CLEAR ME", "GLOBAL ENTRY", "PRIORITY PASS", "PASSPORT", "SEA-TAC", "SEATAC",
                       "PORT OF SEATTLE", "CLIPPER VACATIONS", "CRUISE")),
    Rule("Entertainment", _kw("AMC ", "REGAL", "CINEMA", "CINEMARK", "THEATER", "THEATRE", "TICKETMASTER",
                              "STUBHUB", "SEATGEEK", "EVENTBRITE", "LIVE NATION", "AXS ", "DICE.FM", "TICKETWEB",
                              "STEAM", "PLAYSTATION", "XBOX", "NINTENDO", "BOWLING", "MUSEUM", "CONCERT", "GOLF",
                              "TOPGOLF", "ZOO", "AQUARIUM", "ARCADE", "ROUND ONE", "ROUND1", "DAVE & BUSTER",
                              "ESCAPE ROOM", "SKI ", "SKI RESORT", "LIFT TICKET", "EPIC PASS", "IKON PASS",
                              # Seattle / Washington
                              "MARINERS", "SEAHAWKS", "SOUNDERS", "KRAKEN", "STORM BASKETBALL", "CLIMATE PLEDGE",
                              "LUMEN FIELD", "T-MOBILE PARK", "SIFF ", "SPACE NEEDLE", "CHIHULY", "MOPOP", "PACIFIC SCIENCE",
                              "WOODLAND PARK ZOO", "SEATTLE AQUARIUM", "CRYSTAL MOUNTAIN", "STEVENS PASS",
                              "SNOQUALMIE PASS", "SUMMIT AT SNOQUALMIE", "MT BAKER SKI", "MISSION RIDGE",
                              "5TH AVENUE THEATRE", "BENAROYA", "SEATTLE SYMPHONY", "SEATTLE OPERA", "PARAMOUNT THEAT",
                              "SHOWBOX", "NEPTUNE THEATRE", "CROCODILE", "NEUMOS")),
    # Furniture, hardware, home improvement, garden.
    Rule("Home", _kw("HOME DEPOT", "LOWE'S", "LOWES ", "IKEA", "WAYFAIR", "BED BATH", "HOMEGOODS", "HOME GOODS",
                     "ACE HARDWARE", "TRUE VALUE", "HARDWARE", "SHERWIN", "BENJAMIN MOORE", "CRATE & BARREL",
                     "CRATE AND BARREL", "POTTERY BARN", "WEST ELM", "WILLIAMS SONOMA", "WILLIAMS-SONOMA",
                     "RESTORATION HARDWARE", "RH ", "CONTAINER STORE", "SUR LA TABLE", "MATTRESS", "FURNITURE",
                     "APPLIANCE", "NURSERY", "GARDEN CENTER", "LUMBER", "ROOM & BOARD", "ARTICLE.COM",
                     # Washington
                     "MCLENDON", "DUNN LUMBER", "SWANSONS NURSERY", "SWANSON'S NURSERY", "MOLBAK", "PARKER PAINT",
                     "MILLER PAINT")),
    Rule("Personal Care", _kw("SALON", "BARBER", "HAIR", "SPA ", "DAY SPA", "NAIL", "MASSAGE", "GREAT CLIPS",
                              "SUPERCUTS", "SPORT CLIPS", "FANTASTIC SAMS", "DRYBAR", "EUROPEAN WAX", "WAXING",
                              "ESTHETIC", "SKIN CARE", "SKINCARE", "BEAUTY", "COSMETIC", "SEPHORA", "ULTA",
                              "BATH & BODY", "LUSH ", "DRY CLEAN", "CLEANERS", "LAUNDRY", "LAUNDROMAT", "TAILOR",
                              "ALTERATIONS")),
    Rule("Kids & Pets", _kw("PETCO", "PETSMART", "CHEWY", "MUD BAY", "ALL THE BEST PET", "BANFIELD", "VCA ",
                            "BLUEPEARL", "VETERINARY", "VET ", "ANIMAL HOSP", "ROVER.COM", "WAG ", "BARKBOX",
                            "GROOMING", "DAYCARE", "CHILDCARE", "CHILD CARE", "PRESCHOOL", "KINDERCARE",
                            "BRIGHT HORIZONS", "BABYSIT", "NANNY", "BUY BUY BABY", "CARTER'S", "OSHKOSH", "KUMON",
                            "SUMMER CAMP", "TOYS", "LEGO")),
    Rule("Education", _kw("TUITION", "UNIVERSITY", "COLLEGE", "SCHOOL", "COURSERA", "UDEMY", "SKILLSHARE",
                          "MASTERCLASS", "KHAN ACADEMY", "CHEGG", "PEARSON", "MCGRAW", "KAPLAN", "PRINCETON REVIEW",
                          "STUDENT LOAN", "STUDENT LN", "NAVIENT", "NELNET", "MOHELA", "AIDVANTAGE", "GREAT LAKES ED",
                          "EDFINANCIAL", "SALLIE MAE", "FEDLOAN", "DEPT OF ED", "DEPT EDUCATION", "BOOKSTORE",
                          # Washington
                          "UNIVERSITY OF WASHINGTON", "UW TUITION", "WSU ", "WASHINGTON STATE UNIV",
                          "WESTERN WASHINGTON", "SEATTLE U", "SEATTLE PACIFIC", "BELLEVUE COLLEGE",
                          "UNIVERSITY BOOK STORE")),
    Rule("Shopping", _kw("AMAZON", "AMZN", "TARGET", "WALMART", "WAL-MART", "BEST BUY", "BESTBUY", "EBAY",
                         "ETSY", "APPLE STORE", "MACY", "NORDSTROM", "KOHL", "TJ MAXX", "TJMAXX", "MARSHALLS",
                         "ROSS STORES", "BURLINGTON", "OLD NAVY", "GAP ", "BANANA REPUBLIC", "J.CREW", "J CREW",
                         "H&M", "ZARA", "UNIQLO", "NIKE", "ADIDAS", "LULULEMON", "PATAGONIA", "REI ", "REI.COM",
                         "DICK'S SPORTING", "DICKS SPORTING", "ZAPPOS", "MICRO CENTER", "GAMESTOP", "BARNES & NOBLE",
                         "BARNES&NOBLE", "ELLIOTT BAY BOOK", "POWELL'S", "POWELLS", "MICHAELS", "JO-ANN", "JOANN",
                         "HOBBY LOBBY", "STAPLES", "OFFICE DEPOT", "DOLLAR TREE", "DOLLAR GENERAL", "FIVE BELOW",
                         "SHEIN", "TEMU", "SHOPIFY", "GOODWILL", "VALUE VILLAGE", "SAVERS", "UWAJIMAYA GIFT",
                         "PAYPAL *", "SQ *")),
    Rule("Gifts & Donations", _kw("DONATION", "CHARITY", "GOFUNDME", "RED CROSS", "UNICEF", "CHURCH",
                                  "FOUNDATION", "UNITED WAY", "SALVATION ARMY", "PLANNED PARENTHOOD", "ACLU",
                                  "WIKIMEDIA", "DONORSBOX", "CLASSY.ORG", "TITHE", "NPR ", "KUOW", "KEXP", "KCTS",
                                  "1-800-FLOWERS", "FTD ", "FLORIST", "FLOWERS", "HALLMARK", "GIFT")),
    Rule("Taxes", _kw("IRS ", "IRS USATAXPYMT", "US TREASURY TAX", "EFTPS", "TAX PAYMENT", "TAX PMT",
                      "ESTIMATED TAX", "FRANCHISE TAX", "DEPT OF REVENUE", "DEPT REVENUE", "STATE TAX",
                      "PROPERTY TAX", "COUNTY TREAS", "KING COUNTY TREAS", "TURBOTAX", "H&R BLOCK", "HR BLOCK")),
    Rule("Services", _kw("TASKRABBIT", "THUMBTACK", "ANGI ", "ANGIES LIST", "HANDY", "CLEANING", "MAID",
                         "PLUMB", "ELECTRICIAN", "HVAC", "ROOTER", "LAWN", "LANDSCAP", "PEST", "TERMINIX", "ORKIN",
                         "LOCKSMITH", "MOVING", "MOVERS", "U-HAUL", "UHAUL", "STORAGE", "PUBLIC STORAGE",
                         "EXTRA SPACE", "CUBESMART", "UPS STORE", "USPS", "FEDEX", "POSTAGE", "LEGAL", "ATTORNEY",
                         "LEGALZOOM", "NOTARY", "ACCOUNTING", "CPA ", "GEEK SQUAD", "SHOE REPAIR", "REPAIR")),
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
    ("health", "Healthcare"), ("medical", "Healthcare"), ("pharmac", "Healthcare"), ("doctor", "Healthcare"),
    ("dental", "Healthcare"), ("fitness", "Fitness"), ("gym", "Fitness"), ("sport", "Fitness"),
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


# Words that say *how* money moved but not *what for*. A description made only of these
# (plus numbers, dates and punctuation) is generic: "ACH DEBIT", "POS PURCHASE 4471".
_GENERIC_WORDS = {
    "POS", "PURCHASE", "PURCHASES", "DEBIT", "CREDIT", "CARD", "ACH", "ONLINE", "PAYMENT", "PAYMENTS", "PMT",
    "WITHDRAWAL", "WITHDRWL", "WD", "DEPOSIT", "ELECTRONIC", "RECURRING", "PREAUTHORIZED", "AUTHORIZED", "AUTH",
    "CHECKCARD", "CHECK", "CHK", "TRANSACTION", "TXN", "WEB", "ID", "PPD", "CCD", "BILL", "BILLPAY", "PAY", "ON",
    "MISC", "EXTERNAL", "EXT", "DR", "CR", "TRN", "REF", "NO", "NUMBER", "ORIG", "CO", "NAME", "ENTRY", "DESCR",
    "SEC", "MEMO", "VISA", "MASTERCARD", "MC", "SIGNATURE", "PIN", "ITEM", "OTHER", "DIRECT", "DATE", "AND",
}


def is_generic(description: str | None) -> bool:
    """True when a description says nothing about what the money was for."""
    if not description:
        return True
    words = re.findall(r"[A-Z]+", description.upper())
    return not [w for w in words if len(w) > 1 and w not in _GENERIC_WORDS]


def merchant_for(description: str, memo: str | None) -> str:
    """The merchant name, taken from the memo when the description is generic."""
    if memo and is_generic(description) and not is_generic(memo):
        return normalize_merchant(memo)
    return normalize_merchant(description)


def normalize_merchant(description: str) -> str:
    """Strip noise (card prefixes, store numbers, dates, phone numbers, locations)
    so repeated charges from the same merchant group together."""
    d = description.upper().strip()
    # Peer-to-peer: who the money went to / came from is what matters.
    p2p = re.match(r"^(ZELLE|VENMO|CASH APP|PAYPAL)\b.*?\b(FROM|TO)\s+([A-Z][A-Z'.-]*(?:\s+[A-Z][A-Z'.-]*)?)", d)
    if p2p:
        return string.capwords(f"{p2p.group(1)} {p2p.group(2)} {p2p.group(3)}")
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
    # "TRADER JOE S" -> "TRADER JOE'S"
    merged: list[str] = []
    for t in tokens:
        if t == "S" and merged:
            merged[-1] += "'S"
        else:
            merged.append(t)
    tokens = merged
    had_state = False
    while len(tokens) > 1 and tokens[-1] in _US_STATES:
        tokens.pop()
        had_state = True
    if had_state and len(tokens) >= 3:
        tokens.pop()  # the city before the state: "SEATTLE WA"
    tokens = [t for t in tokens if t not in {"INC", "LLC", "CO", "CORP", "LTD", "THE", "US", "USA", "ONLINE"}] or tokens
    merchant = " ".join(tokens[:3]).strip()
    return string.capwords(merchant) if merchant else description.strip()[:40]


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

    def matches(self, description: str, memo: str | None = None, merchant: str | None = None) -> bool:
        """Contains/regex rules look at the description and the memo; merchant rules at the
        merchant name shown in the app."""
        if self.match == "merchant":
            name = merchant if merchant is not None else merchant_for(description, memo)
            return name.lower() == self.pattern.strip().lower()
        pat = self.compiled()
        return bool(pat and (pat.search(description) or (memo and pat.search(memo))))

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


# Everyday words people type in memos and payment notes ("dinner", "movie tickets").
# Only used on memo text, never on bank descriptions.
MEMO_HINTS: list[tuple[str, re.Pattern]] = [(cat, re.compile(r"\b(?:" + pat + r")\b", re.I)) for cat, pat in [
    ("Housing", r"rent|mortgage|hoa|landlord|lease|security deposit"),
    ("Utilities", r"utilities|utility|electric(?:ity)?|power bill|internet|wifi|water bill|phone bill|gas bill|"
                  r"garbage|trash|sewer|cell phone"),
    ("Groceries", r"groceries|grocery|costco run|food shopping"),
    ("Dining", r"dinner|lunch|brunch|breakfast|drinks|beers?|coffee|food|pizza|sushi|meal|takeout|take out|"
               r"restaurant|tacos?|burgers?|bar tab|happy hour"),
    ("Entertainment", r"movies?|tickets?|concert|show|game|bowling|museum|festival|karaoke|ski pass|lift tickets?"),
    ("Transportation", r"uber|lyft|cab|taxi|parking|gas money|ride|ferry|bus|train|toll"),
    ("Auto & Gas", r"gas|fuel|car wash|oil change|tires?|car repair|car payment|registration|tabs"),
    ("Travel", r"trip|hotel|airbnb|vrbo|flights?|airfare|vacation|lodging|cabin|camping"),
    ("Healthcare", r"doctor|dr visit|dentist|dental|copay|co-pay|prescriptions?|rx|pharmacy|meds|medicine|"
                   r"therapy|therapist|clinic|hospital|urgent care|eye exam|glasses|contacts|vet bill"),
    ("Fitness", r"gym|yoga|pilates|climbing|crossfit|spin class|personal trainer|race entry|marathon"),
    ("Insurance", r"insurance|premium"),
    ("Education", r"tuition|textbooks?|books for class|class fee|course|school|student loan"),
    ("Personal Care", r"haircut|hair|salon|barber|nails|manicure|pedicure|massage|spa|dry cleaning"),
    ("Home", r"furniture|couch|sofa|mattress|hardware|tools|paint|plants|garden|home improvement|appliance"),
    ("Kids & Pets", r"daycare|babysit(?:ting|ter)?|nanny|dog|cat|pet|kids?|diapers|toys|camp"),
    ("Gifts & Donations", r"gift|birthday|wedding|donation|charity|present|flowers"),
    ("Services", r"cleaning|cleaner|plumber|electrician|repair|movers|moving|storage|lawn|handyman"),
    ("Shopping", r"clothes|clothing|shoes|amazon order|electronics"),
    ("Subscriptions", r"subscription|membership|streaming"),
    ("Taxes", r"taxes|tax payment|property tax"),
]]


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


def _builtin(text: str, direction: str) -> Rule | None:
    for rule in BUILTIN_RULES:
        if rule.direction != "any" and rule.direction != direction:
            continue
        if rule.pattern.search(text):
            return rule
    return None


def _from_memo(memo: str, amount: float, direction: str) -> tuple[str, Kind | None] | None:
    """Category (and forced kind, if any) suggested by the memo, or None."""
    rule = _builtin(memo, direction)
    if rule:
        return rule.category, rule.kind
    for category, pattern in MEMO_HINTS:
        if pattern.search(memo):
            return category, None
    return None


def classify(description: str, amount: float, account_type: AccountType, source_category: str | None,
             user_rules: list[UserRule], memo: str | None = None, merchant: str | None = None) -> Classification:
    """Pick a category and kind. Precedence: your rules (description or memo) > built-in keywords on
    the description > the memo > the bank's own category > Uncategorized. A generic description
    ("ACH DEBIT") with nothing useful in the memo is left Uncategorized for you to decide."""
    direction = "in" if amount > 0 else "out"

    def spend_kind(category: str, forced: Kind | None) -> Kind:
        if forced:
            return forced
        if category in (CARD_PAYMENT, TRANSFERS):
            return Kind.TRANSFER
        if category == INCOME:
            return Kind.INCOME if amount > 0 else Kind.EXPENSE
        # A memo naming what the money was for: money in under that category is a pay-back.
        return Kind.REFUND if amount > 0 else Kind.EXPENSE

    for rule in user_rules:
        if rule.direction != "any" and rule.direction != direction:
            continue
        if rule.matches(description, memo, merchant):
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

    rule = _builtin(description, direction)
    if rule:
        # Person-to-person payments say who, not what for; the memo often says what for.
        if rule.category == "Peer-to-Peer" and memo:
            hint = _from_memo(memo, amount, direction)
            if hint and hint[0] not in ("Peer-to-Peer", INCOME):
                return Classification(hint[0], spend_kind(hint[0], hint[1]), "memo")
        kind = rule.kind or _default_kind(amount, account_type, description)
        return Classification(rule.category, kind, "auto")

    if memo:
        hint = _from_memo(memo, amount, direction)
        if hint:
            category, forced = hint
            if forced is None and category not in (CARD_PAYMENT, TRANSFERS, INCOME):
                forced = _default_kind(amount, account_type, memo) if amount > 0 else Kind.EXPENSE
                if amount > 0 and forced == Kind.INCOME:
                    forced = Kind.REFUND  # money in, memo names a spending category -> paid back
            return Classification(category, spend_kind(category, forced), "memo")

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
