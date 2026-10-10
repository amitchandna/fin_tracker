"""CSV ingestion: header detection, column mapping, amount/date parsing and
sign normalisation for the many formats banks and card issuers export.

Every parsed row ends up with a signed amount where **negative means money left
you** (a purchase, a bill, a withdrawal) and positive means money came in
(a paycheck, a refund, a card payment received by the card account).
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
from datetime import date, datetime
from pathlib import Path

from .models import AccountType, ParsedFile, RawRow

# Header aliases, most specific first. Matching is done on normalised header text.
DATE_HEADERS = [
    "transaction date", "trans date", "trans. date", "date", "posted date", "post date",
    "posting date", "booking date", "value date", "date posted", "transaction posted date",
]
DESC_HEADERS = [
    "description", "transaction description", "payee", "merchant", "merchant name", "name",
    "details", "narrative", "original description", "memo", "transaction details", "reference",
]
AMOUNT_HEADERS = ["amount", "transaction amount", "amount (usd)", "amount usd", "value", "net amount"]
DEBIT_HEADERS = [
    "debit", "debits", "withdrawal", "withdrawals", "debit amount", "money out", "paid out",
    "charges", "withdrawal amount", "amount debit",
]
CREDIT_HEADERS = [
    "credit", "credits", "deposit", "deposits", "credit amount", "money in", "paid in",
    "payments", "deposit amount", "amount credit",
]
# Free-text notes that often say what a vague description was for
# ("ACH DEBIT" + memo "PUGET SOUND ENERGY BILLPAY").
MEMO_HEADERS = [
    "memo", "notes", "note", "transaction memo", "extended details", "additional info",
    "additional information", "appears on your statement as", "description 2", "payee notes", "comments",
    "purpose", "remarks",
]
TYPE_HEADERS = ["transaction type", "type", "debit/credit", "dr/cr", "credit/debit", "cr/dr"]
CATEGORY_HEADERS = ["category", "transaction category", "categories"]

CREDIT_FILE_HINTS = (
    "credit", "card", "visa", "mastercard", "amex", "american express", "discover",
    "sapphire", "freedom", "venture", "quicksilver", "platinum", "gold card",
)
BANK_FILE_HINTS = ("checking", "debit", "bank", "current account")
SAVINGS_FILE_HINTS = ("savings", "saving", "money market")

DATE_FORMATS = [
    "%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%d/%m/%Y", "%Y/%m/%d", "%m-%d-%Y", "%d-%m-%Y",
    "%d %b %Y", "%d %B %Y", "%b %d, %Y", "%B %d, %Y", "%b %d %Y", "%Y%m%d", "%d.%m.%Y",
    "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%m/%d/%Y %H:%M:%S", "%m/%d/%Y %I:%M:%S %p",
]

CARD_PAYMENT_IN = re.compile(
    r"PAYMENT\s*(-\s*)?THANK\s*YOU|AUTOPAY|AUTO\s*PAY|ONLINE PAYMENT|PAYMENT RECEIVED|MOBILE PAYMENT|"
    r"ELECTRONIC PAYMENT|PAYMENT - WEB|INTERNET PAYMENT|DIRECTPAY",
    re.I,
)
INCOME_HINT = re.compile(r"PAYROLL|DIRECT DEP|SALARY|DEPOSIT|INTEREST PAID|DIVIDEND", re.I)


def _norm_header(h: str) -> str:
    return re.sub(r"\s+", " ", h.replace("﻿", "").strip().strip('"').lower())


def parse_date(value: str, day_first: bool = False) -> date | None:
    v = value.strip()
    if not v:
        return None
    formats = DATE_FORMATS
    if day_first:
        formats = ["%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y"] + DATE_FORMATS
    for fmt in formats:
        try:
            return datetime.strptime(v, fmt).date()
        except ValueError:
            continue
    # Tolerate trailing garbage like "01/02/2024 *" or a timezone suffix.
    m = re.match(r"(\d{1,4}[/\-.]\d{1,2}[/\-.]\d{1,4})", v)
    if m and m.group(1) != v:
        return parse_date(m.group(1), day_first)
    return None


_AMOUNT_CLEAN = re.compile(r"[^\d.\-]")


def parse_amount(value: str) -> float | None:
    """Parse '$1,234.56', '(12.34)', '-12.34', '12.34 CR', '12.34-', '€ 5,00'."""
    v = value.strip()
    if not v or v in {"-", "--"}:
        return None
    negative = False
    upper = v.upper()
    if upper.endswith("CR"):
        v = v[:-2]
    elif upper.endswith("DR"):
        v = v[:-2]
        negative = True
    if v.startswith("(") and v.endswith(")"):
        negative = True
        v = v[1:-1]
    v = v.strip()
    if v.endswith("-"):
        negative = True
        v = v[:-1]
    # European decimal comma: "1.234,56" or "5,00"
    if re.fullmatch(r"[^\d]*\d{1,3}(\.\d{3})*,\d{2}[^\d]*", v):
        v = v.replace(".", "").replace(",", ".")
    else:
        v = v.replace(",", "")
    cleaned = _AMOUNT_CLEAN.sub("", v)
    if cleaned.count("-") > 0:
        negative = negative ^ cleaned.startswith("-")
        cleaned = cleaned.replace("-", "")
    if not cleaned or cleaned == ".":
        return None
    try:
        num = float(cleaned)
    except ValueError:
        return None
    return -num if negative else num


def _find(headers: list[str], aliases: list[str], exclude: set[int] = frozenset()) -> int | None:
    # Exact alias match first, then "header contains alias".
    for alias in aliases:
        for i, h in enumerate(headers):
            if i not in exclude and h == alias:
                return i
    for alias in aliases:
        for i, h in enumerate(headers):
            if i not in exclude and len(alias) > 3 and alias in h:
                return i
    return None


def _sniff_dialect(text: str) -> type[csv.Dialect] | csv.Dialect:
    sample = text[:8192]
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        return csv.excel


def _looks_like_header(row: list[str]) -> bool:
    headers = [_norm_header(c) for c in row]
    has_date = _find(headers, DATE_HEADERS) is not None
    has_money = any(
        _find(headers, aliases) is not None for aliases in (AMOUNT_HEADERS, DEBIT_HEADERS, CREDIT_HEADERS)
    )
    return has_date and has_money


def _infer_headerless(rows: list[list[str]]) -> dict[str, int | None] | None:
    """For exports without a header row, guess columns from the data itself."""
    sample = [r for r in rows[:50] if any(c.strip() for c in r)]
    if not sample:
        return None
    width = max(len(r) for r in sample)
    date_col = amount_col = desc_col = None
    best_text_len = 0.0
    for col in range(width):
        vals = [r[col] for r in sample if col < len(r) and r[col].strip()]
        if not vals:
            continue
        date_hits = sum(parse_date(v) is not None for v in vals)
        amt_hits = sum(parse_amount(v) is not None and re.search(r"\d", v) is not None for v in vals)
        if date_col is None and date_hits >= 0.8 * len(vals):
            date_col = col
        elif amount_col is None and amt_hits >= 0.8 * len(vals):
            amount_col = col
        else:
            avg_len = sum(len(v) for v in vals) / len(vals)
            if avg_len > best_text_len and amt_hits < 0.5 * len(vals):
                best_text_len = avg_len
                desc_col = col
    if date_col is None or amount_col is None or desc_col is None:
        return None
    return {"date": date_col, "description": desc_col, "amount": amount_col,
            "debit": None, "credit": None, "type": None, "category": None}


def detect_account_type(file_name: str, headers: list[str], descriptions: list[str],
                        signed_amounts: list[float]) -> AccountType:
    name = file_name.lower().replace("_", " ").replace("-", " ")
    if any(h in name for h in SAVINGS_FILE_HINTS):
        return AccountType.SAVINGS
    if any(h in name for h in CREDIT_FILE_HINTS):
        return AccountType.CREDIT_CARD
    if any(h in name for h in BANK_FILE_HINTS):
        return AccountType.CHECKING
    joined = " ".join(headers)
    if "card no" in joined or "card member" in joined or "cardholder" in joined or "card number" in joined:
        return AccountType.CREDIT_CARD
    if "balance" in joined or "check number" in joined or "check or slip" in joined:
        return AccountType.CHECKING
    # Card statements contain "PAYMENT THANK YOU"-style rows.
    if descriptions and sum(bool(CARD_PAYMENT_IN.search(d)) for d in descriptions) >= 1 and not any(
        re.search(r"PAYROLL|DIRECT DEP|ATM", d, re.I) for d in descriptions
    ):
        return AccountType.CREDIT_CARD
    return AccountType.CHECKING


def account_name_from_file(file_name: str) -> str:
    """'chase_credit_2024-01.csv' -> 'Chase Credit'. Dates and statement numbers are
    stripped so successive exports of the same account share a name."""
    stem = Path(file_name).stem
    stem = re.sub(r"\d{4}[-_.]?\d{2}([-_.]?\d{2})?", " ", stem)
    stem = re.sub(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\b", " ", stem, flags=re.I)
    stem = re.sub(r"\d+", " ", stem)
    stem = re.sub(r"[_\-.()\[\]]+", " ", stem)
    stem = re.sub(r"\b(statement|transactions?|export|activity|download|history|to|thru)\b", " ", stem, flags=re.I)
    words = stem.split()
    if not words:
        return Path(file_name).stem
    return " ".join(w if w.isupper() and len(w) <= 4 else w.capitalize() for w in words)


def _should_invert(account_type: AccountType, rows: list[RawRow]) -> bool:
    """Decide whether a single signed-amount column uses 'positive = money out'
    (Amex, Discover, some Capital One exports)."""
    if not rows:
        return False
    # Strongest signal: rows that are clearly money *in* show up as negative. On a card that's
    # "PAYMENT THANK YOU"; in a bank account it's pay. ("ONLINE PAYMENT" in a checking account is
    # a bill you paid, so card-payment wording must not be used there.)
    if account_type == AccountType.CREDIT_CARD:
        in_rows = [r for r in rows if CARD_PAYMENT_IN.search(r.description)]
    else:
        in_rows = [r for r in rows if re.search(r"PAYROLL|DIRECT DEP|DIR DEP|SALARY", r.description, re.I)]
    if in_rows:
        neg = sum(r.amount < 0 for r in in_rows)
        if neg > len(in_rows) / 2:
            return True
        if neg < len(in_rows) / 2:
            return False
    if account_type == AccountType.CREDIT_CARD:
        positives = sum(r.amount > 0 for r in rows)
        return positives > len(rows) * 0.6
    return False


def parse_csv_text(text: str, file_name: str, overrides: dict | None = None) -> ParsedFile:
    overrides = overrides or {}
    content_hash = hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()
    result = ParsedFile(file_name=file_name, account=overrides.get("name") or account_name_from_file(file_name),
                        account_type=AccountType.UNKNOWN, content_hash=content_hash)
    if not text.strip():
        result.error = "File is empty"
        return result

    dialect = _sniff_dialect(text)
    all_rows = list(csv.reader(io.StringIO(text), dialect))

    header_idx = None
    for i, row in enumerate(all_rows[:40]):
        if _looks_like_header(row):
            header_idx = i
            break

    if header_idx is not None:
        headers = [_norm_header(c) for c in all_rows[header_idx]]
        data_rows = all_rows[header_idx + 1:]
        cols: dict[str, int | None] = {}
        cols["date"] = _find(headers, DATE_HEADERS)
        used = {cols["date"]}
        cols["debit"] = _find(headers, DEBIT_HEADERS, used)
        used.add(cols["debit"])
        cols["credit"] = _find(headers, CREDIT_HEADERS, used)
        used.add(cols["credit"])
        cols["amount"] = _find(headers, AMOUNT_HEADERS, used)
        used.add(cols["amount"])
        cols["type"] = _find(headers, TYPE_HEADERS, used)
        used.add(cols["type"])
        cols["category"] = _find(headers, CATEGORY_HEADERS, used)
        used.add(cols["category"])
        cols["description"] = _find(headers, DESC_HEADERS, used)
        used.add(cols["description"])
        memo_cols = [i for i, h in enumerate(headers) if i not in used and h and any(
            h == alias or (len(alias) > 3 and alias in h) for alias in MEMO_HEADERS)]
        if cols["amount"] is not None and (cols["debit"] is not None or cols["credit"] is not None):
            # Prefer the split debit/credit columns only when both exist.
            if cols["debit"] is None or cols["credit"] is None:
                cols["debit"] = cols["credit"] = None
    else:
        headers = []
        inferred = _infer_headerless(all_rows)
        if inferred is None:
            result.error = "Could not find a header row with date and amount columns"
            return result
        cols = inferred
        memo_cols = []
        data_rows = all_rows
        result.warnings.append("No header row found; columns were inferred from the data")

    if cols["date"] is None:
        result.error = "No date column found"
        return result
    if cols["amount"] is None and cols["debit"] is None and cols["credit"] is None:
        result.error = "No amount, debit or credit column found"
        return result
    if cols["description"] is None:
        result.warnings.append("No description column found; using row text")

    result.columns = {k: (headers[v] if headers and v is not None else (str(v) if v is not None else None))
                      for k, v in cols.items()}
    result.columns["memo"] = ", ".join(headers[i] for i in memo_cols) or None

    day_first = bool(overrides.get("day_first", False))
    if not day_first and cols["date"] is not None:
        # If any day value is > 12 in the first position, the file is day-first.
        for r in data_rows[:200]:
            if cols["date"] < len(r):
                m = re.match(r"^\s*(\d{1,2})[/.\-](\d{1,2})[/.\-]\d{2,4}", r[cols["date"]])
                if m and int(m.group(1)) > 12:
                    day_first = True
                    break

    def cell(r: list[str], key: str) -> str:
        idx = cols.get(key)
        return r[idx].strip() if idx is not None and idx < len(r) else ""

    single_signed = cols["amount"] is not None and cols["debit"] is None
    rows: list[RawRow] = []
    for r in data_rows:
        if not any(c.strip() for c in r):
            continue
        d = parse_date(cell(r, "date"), day_first)
        if d is None:
            result.skipped_rows += 1
            continue
        if cols["debit"] is not None or cols["credit"] is not None:
            debit = parse_amount(cell(r, "debit")) or 0.0
            credit = parse_amount(cell(r, "credit")) or 0.0
            if debit == 0 and credit == 0 and cols["amount"] is not None:
                amount = parse_amount(cell(r, "amount"))
            else:
                amount = abs(credit) - abs(debit)
        else:
            amount = parse_amount(cell(r, "amount"))
            ttype = cell(r, "type").lower()
            if amount is not None and ttype:
                if ttype in {"debit", "dr", "d", "withdrawal", "purchase", "sale", "payment out"} or ttype.startswith("debit"):
                    amount = -abs(amount)
                    single_signed = False
                elif ttype in {"credit", "cr", "c", "deposit"} or ttype.startswith("credit"):
                    amount = abs(amount)
                    single_signed = False
        if amount is None:
            result.skipped_rows += 1
            continue
        desc = cell(r, "description") or " ".join(c.strip() for c in r if c.strip() and not parse_amount(c))
        desc = re.sub(r"\s+", " ", desc).strip() or "(no description)"
        notes = []
        for i in memo_cols:
            note = re.sub(r"\s+", " ", r[i]).strip() if i < len(r) else ""
            if note and note.lower() != desc.lower() and note not in notes:
                notes.append(note)
        rows.append(RawRow(date=d, description=desc, amount=amount,
                           source_category=cell(r, "category") or None, memo=" · ".join(notes) or None))

    if not rows:
        result.error = "No valid transactions found"
        return result

    if overrides.get("account_type"):
        try:
            result.account_type = AccountType(overrides["account_type"])
        except ValueError:
            result.warnings.append(f"Unknown account_type override {overrides['account_type']!r}")
    if result.account_type == AccountType.UNKNOWN:
        result.account_type = detect_account_type(
            file_name, headers, [r.description for r in rows], [r.amount for r in rows])

    if "invert_amounts" in overrides and overrides["invert_amounts"] is not None:
        invert = bool(overrides["invert_amounts"])
    else:
        invert = single_signed and _should_invert(result.account_type, rows)
    if invert:
        for r in rows:
            r.amount = -r.amount
        result.inverted = True
        result.warnings.append("Amounts were sign-flipped (this export lists charges as positive)")

    if result.skipped_rows:
        result.warnings.append(f"Skipped {result.skipped_rows} row(s) without a valid date or amount")
    result.rows = rows
    return result


def read_text(path: Path) -> str:
    raw = path.read_bytes()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16")
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1")


def parse_csv_file(path: Path, overrides: dict | None = None, display_name: str | None = None) -> ParsedFile:
    try:
        text = read_text(path)
    except OSError as exc:
        return ParsedFile(file_name=display_name or path.name, account=path.stem,
                          account_type=AccountType.UNKNOWN, error=f"Could not read file: {exc}")
    return parse_csv_text(text, display_name or path.name, overrides)
