#!/usr/bin/env python3
"""Generate realistic sample bank/card exports in ./sample_data.

Each file mimics a different real-world format so the parser's format handling
is exercised: signed amounts, positive-means-charge cards, split debit/credit
columns, a preamble before the header, and day-first dates.
Deterministic (fixed seed) so the output is stable across runs.
"""

from __future__ import annotations

import csv
import random
from datetime import date, timedelta
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "sample_data"
rng = random.Random(42)
START = date(2026, 4, 1)
END = date(2026, 9, 30)


def days():
    d = START
    while d <= END:
        yield d
        d += timedelta(days=1)


def month_starts():
    d = START
    while d <= END:
        yield d
        d = (d.replace(day=28) + timedelta(days=4)).replace(day=1)


def money(lo, hi):
    return round(rng.uniform(lo, hi), 2)


def chase_credit():
    """Chase-style: negative = charge, has Category and Type columns."""
    rows = []
    for d in days():
        if rng.random() < 0.35:
            name, cat = rng.choice([("STARBUCKS STORE 08712", "Food & Drink"), ("CHIPOTLE 1123", "Food & Drink"),
                                    ("SWEETGREEN NOHO", "Food & Drink"), ("TST* BLUE RIBBON SUSHI", "Food & Drink")])
            rows.append((d, name, cat, "Sale", -money(5, 48)))
        if d.weekday() == 5:
            rows.append((d, "WHOLEFDS NOH 10245", "Groceries", "Sale", -money(60, 180)))
        if rng.random() < 0.12:
            rows.append((d, "AMAZON MKTPL*2K4LP9QX1", "Shopping", "Sale", -money(12, 140)))
        if rng.random() < 0.06:
            rows.append((d, "UBER *TRIP HELP.UBER.COM", "Travel", "Sale", -money(11, 42)))
        if rng.random() < 0.04:
            rows.append((d, "SHELL OIL 57444", "Gas", "Sale", -money(38, 70)))
    for m in month_starts():
        rows.append((m.replace(day=3), "NETFLIX.COM", "Bills & Utilities", "Sale", -22.99))
        rows.append((m.replace(day=11), "SPOTIFY USA", "Bills & Utilities", "Sale", -11.99))
        rows.append((m.replace(day=19), "PLANET FITNESS CLUB FEE", "Health & Wellness", "Sale", -24.99))
        rows.append((m.replace(day=26), "Payment Thank You-Mobile", "", "Payment", money(900, 1600)))
    rows.append((date(2026, 6, 14), "AMAZON MKTPL*RT88Q1", "Shopping", "Return", 46.20))
    rows.append((date(2026, 7, 2), "DELTA AIR LINES ATLANTA", "Travel", "Sale", -412.40))
    rows.append((date(2026, 7, 18), "MARRIOTT HOTELS SEATTLE", "Travel", "Sale", -689.13))
    rows.sort(key=lambda r: r[0], reverse=True)
    with open(OUT / "chase_sapphire_credit.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Transaction Date", "Post Date", "Description", "Category", "Type", "Amount", "Memo"])
        for d, desc, cat, typ, amt in rows:
            post = d + timedelta(days=1)
            w.writerow([d.strftime("%m/%d/%Y"), post.strftime("%m/%d/%Y"), desc, cat, typ, f"{amt:.2f}", ""])


def amex():
    """Amex-style: positive = charge, negative = payment/credit, no category."""
    rows = []
    for d in days():
        if rng.random() < 0.08:
            rows.append((d, rng.choice(["TRADER JOE'S #123 LOS ANGELES CA", "COSTCO WHSE #0479"]), money(30, 160)))
        if rng.random() < 0.05:
            rows.append((d, "DOORDASH*THAI TOWN", money(25, 65)))
        if rng.random() < 0.03:
            rows.append((d, "TARGET 00012345", money(15, 120)))
    for m in month_starts():
        rows.append((m.replace(day=7), "APPLE.COM/BILL 866-712-7753 CA", 2.99))
        rows.append((m.replace(day=7), "ADOBE *CREATIVE CLOUD", 59.99))
        rows.append((m.replace(day=15), "GEICO *AUTO", 132.50))
        rows.append((m.replace(day=22), "AUTOPAY PAYMENT - THANK YOU", -money(350, 700)))
    rows.append((date(2026, 5, 9), "TICKETMASTER", 186.00))
    rows.append((date(2026, 8, 20), "TARGET 00012345 RETURN", -34.99))
    rows.sort(key=lambda r: r[0])
    with open(OUT / "amex_gold_card.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Date", "Description", "Card Member", "Account #", "Amount"])
        for d, desc, amt in rows:
            w.writerow([d.strftime("%m/%d/%Y"), desc, "ALEX DOE", "-41007", f"{amt:.2f}"])


def checking():
    """Bank checking with a preamble, separate Debit/Credit columns and a balance."""
    rows = []
    for m in month_starts():
        rows.append((m.replace(day=1), "RENTCAFE ONLINE PMT RENT PAYMENT", 2450.00, 0))
        rows.append((m.replace(day=15), "ACME CORP PAYROLL PPD ID: 99123", 0, 3850.00))
        last = (m.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        rows.append((last, "ACME CORP PAYROLL PPD ID: 99123", 0, 3850.00))
        rows.append((m.replace(day=5), "PGANDE WEB ONLINE PG&E ELECTRIC", money(70, 140), 0))
        rows.append((m.replace(day=9), "COMCAST XFINITY INTERNET", 79.99, 0))
        rows.append((m.replace(day=12), "VERIZON WIRELESS PAYMENTS", 65.00, 0))
        rows.append((m.replace(day=27), "CHASE CREDIT CRD AUTOPAY", money(900, 1600), 0))
        rows.append((m.replace(day=23), "AMEX EPAYMENT ACH PMT", money(350, 700), 0))
        rows.append((m.replace(day=20), "ONLINE TRANSFER TO SAV ...4421", 500.00, 0))
        rows.append((m.replace(day=10), "NAVIENT STUDENT LOAN", 312.00, 0))
    for d in days():
        if rng.random() < 0.05:
            rows.append((d, "DEBIT CARD PURCHASE SAFEWAY #1234", money(20, 90), 0))
        if rng.random() < 0.03:
            rows.append((d, "ZELLE PAYMENT TO JORDAN SMITH", money(20, 120), 0))
        if rng.random() < 0.02:
            rows.append((d, "ATM WITHDRAWAL 000123 5TH AVE", 60.00, 0))
        if rng.random() < 0.02:
            rows.append((d, "DEBIT CARD PURCHASE CVS/PHARMACY #0921", money(8, 45), 0))
    rows.append((date(2026, 6, 3), "CHECK 1043", 180.00, 0))
    rows.append((date(2026, 8, 12), "IRS TREAS 310 TAX REF", 0, 742.00))
    rows.sort(key=lambda r: r[0])
    balance = 8200.00
    with open(OUT / "wells_checking.csv", "w", newline="") as f:
        f.write("Account Name: Everyday Checking\nAccount Number: XXXXXX9921\n\n")
        w = csv.writer(f)
        w.writerow(["Date", "Description", "Debit", "Credit", "Balance"])
        for d, desc, debit, credit in rows:
            balance += credit - debit
            w.writerow([d.isoformat(), desc, f"{debit:.2f}" if debit else "", f"{credit:.2f}" if credit else "",
                        f"{balance:.2f}"])


def savings():
    """Savings account, day-first dates, signed amounts."""
    with open(OUT / "ally_savings.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Date", "Description", "Amount"])
        for m in month_starts():
            w.writerow([m.replace(day=20).strftime("%d/%m/%Y"), "Online Transfer from CHK ...9921", "500.00"])
            w.writerow([m.replace(day=28).strftime("%d/%m/%Y"), "Interest Paid", f"{money(9, 14):.2f}"])


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    chase_credit()
    amex()
    checking()
    savings()
    print(f"Wrote sample data to {OUT}")
