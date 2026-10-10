import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

SAMPLE = Path(__file__).resolve().parents[2] / "sample_data"


@pytest.fixture
def data_dir(tmp_path):
    d = tmp_path / "data"
    shutil.copytree(SAMPLE, d)
    return d


@pytest.fixture
def client(data_dir, tmp_path):
    settings = Settings(data_dir=data_dir, state_dir=tmp_path / "state", frontend_dist=tmp_path / "nope")
    return TestClient(create_app(settings))


def test_sources_parsed(client):
    sources = {s["file_name"]: s for s in client.get("/api/sources").json()}
    assert set(sources) == {"chase_sapphire_credit.csv", "amex_gold_card.csv", "wells_checking.csv",
                            "ally_savings.csv"}
    assert all(s["error"] is None for s in sources.values())
    assert sources["amex_gold_card.csv"]["account_type"] == "credit_card"
    assert sources["amex_gold_card.csv"]["inverted"] is True
    assert sources["wells_checking.csv"]["account_type"] == "checking"
    assert sources["ally_savings.csv"]["account_type"] == "savings"


def test_card_payments_not_counted_as_spending(client):
    months = client.get("/api/summary/monthly").json()
    assert len(months) == 6
    for m in months:
        assert "Credit Card Payment" not in m["by_category"]
        assert "Transfers" not in m["by_category"]
        assert m["spending"] == pytest.approx(sum(m["by_category"].values()), abs=0.05)
        assert m["spending"] == pytest.approx(sum(m["by_payment_method"].values()), abs=0.05)
        assert m["spending"] == pytest.approx(m["recurring"] + m["one_time"], abs=0.05)
        assert m["income"] > 7000


def test_filter_by_payment_method(client):
    credit = client.get("/api/summary/monthly", params={"payment_method": "credit"}).json()
    assert all(set(m["by_payment_method"]) <= {"credit"} for m in credit)


def test_recurring_detected(client):
    names = {r["merchant"] for r in client.get("/api/recurring").json()}
    assert {"Netflix", "Spotify", "Geico Auto"} <= names


def test_transactions_filter_and_paging(client):
    r = client.get("/api/transactions", params={"category": "Subscriptions", "limit": 5}).json()
    assert r["total"] >= 24
    assert len(r["items"]) == 5
    assert all(i["category"] == "Subscriptions" for i in r["items"])
    r = client.get("/api/transactions", params={"q": "netflix"}).json()
    assert r["total"] == 6 and all(i["is_recurring"] for i in r["items"])


def test_manual_category_override(client):
    tid = client.get("/api/transactions", params={"q": "CHECK 1043"}).json()["items"][0]["id"]
    r = client.patch(f"/api/transactions/{tid}", json={"category": "Home"})
    assert r.status_code == 200 and r.json()["category"] == "Home" and r.json()["category_source"] == "manual"
    r = client.patch(f"/api/transactions/{tid}", json={"category": "Transfers"})
    assert r.json()["kind"] == "transfer"
    assert client.patch("/api/transactions/nope", json={"category": "Home"}).status_code == 404


def test_rules_crud(client):
    r = client.post("/api/rules", json={"pattern": "starbucks", "category": "Coffee"})
    assert r.status_code == 201 and r.json()["matched"] > 0
    rid = r.json()["id"]
    cats = client.get("/api/summary/categories").json()
    assert any(c["category"] == "Coffee" for c in cats)
    assert client.delete(f"/api/rules/{rid}").status_code == 204
    assert client.delete(f"/api/rules/{rid}").status_code == 404
    assert client.post("/api/rules", json={"pattern": "([", "category": "X", "match": "regex"}).status_code == 422


def test_new_file_picked_up_and_duplicates_skipped(client, data_dir):
    before = client.get("/api/config").json()["transactions"]
    shutil.copy(data_dir / "amex_gold_card.csv", data_dir / "amex_copy.csv")
    sources = {s["file_name"]: s for s in client.get("/api/sources").json()}
    counts = sorted([sources["amex_copy.csv"]["transactions"], sources["amex_gold_card.csv"]["transactions"]])
    assert counts == [0, 50]
    assert client.get("/api/config").json()["transactions"] == before
    (data_dir / "new_card.csv").write_text("Date,Description,Amount\n2026-09-15,NEW SHOP,-12.00\n")
    assert client.get("/api/config").json()["transactions"] == before + 1


def test_source_settings_override(client):
    r = client.put("/api/sources/ally_savings.csv", json={"name": "Rainy Day Fund"})
    assert r.status_code == 200 and r.json()["account"] == "Rainy Day Fund"
    assert client.put("/api/sources/missing.csv", json={}).status_code == 404


def test_overview_and_export(client):
    o = client.get("/api/summary/overview").json()
    assert o["months"] == 6 and o["average_monthly_spending"] > 0 and o["active_recurring"] >= 8
    r = client.get("/api/transactions/export", params={"month": "2026-05"})
    assert r.status_code == 200 and r.text.startswith("date,description")


def test_empty_data_dir(tmp_path):
    settings = Settings(data_dir=tmp_path / "missing", state_dir=tmp_path / "s", frontend_dist=tmp_path / "x")
    c = TestClient(create_app(settings))
    assert c.get("/api/summary/overview").json()["months"] == 0
    assert c.get("/api/sources").json() == []


def test_savings_is_income_minus_spending(client):
    months = client.get("/api/summary/monthly").json()
    running = 0.0
    for m in months:
        assert m["savings"] == pytest.approx(m["income"] - m["spending"], abs=0.01)
        assert m["savings_rate"] == pytest.approx(m["savings"] / m["income"], abs=1e-3)
        running += m["savings"]
        assert m["cumulative_savings"] == pytest.approx(running, abs=0.05)
        assert m["income"] == pytest.approx(sum(m["by_income_source"].values()), abs=0.05)
    o = client.get("/api/summary/overview").json()
    assert o["total_savings"] == pytest.approx(o["total_income"] - o["total_spending"], abs=0.05)
    assert 0 < o["savings_rate"] < 1
    assert o["months_saved"] == 6 and o["months_overspent"] == 0


def test_income_sources(client):
    sources = client.get("/api/summary/income").json()
    by_name = {s["source"]: s for s in sources}
    assert by_name["Acme Payroll"]["transactions"] == 12
    assert by_name["Acme Payroll"]["amount"] == pytest.approx(46200)
    assert sources[0]["source"] == "Acme Payroll"
    assert sum(s["share"] for s in sources) == pytest.approx(1, abs=0.01)
    may = client.get("/api/summary/income", params={"month": "2026-05"}).json()
    # Before review, a friend's Zelle is guessed as income (and flagged for review).
    assert {s["source"] for s in may} == {"Acme Payroll", "Interest Paid", "Zelle From Alex Kim"}


def test_month_without_income_has_no_savings_rate(tmp_path):
    d = tmp_path / "data"
    d.mkdir()
    (d / "card.csv").write_text("Date,Description,Amount\n2026-01-05,TARGET,-50.00\n")
    settings = Settings(data_dir=d, state_dir=tmp_path / "s", frontend_dist=tmp_path / "x")
    m = TestClient(create_app(settings)).get("/api/summary/monthly").json()[0]
    assert m["savings"] == -50 and m["savings_rate"] is None


def test_exclude_transaction_from_budget(client):
    before = {m["month"]: m for m in client.get("/api/summary/monthly").json()}
    t = client.get("/api/transactions", params={"q": "DELTA AIR"}).json()["items"][0]
    r = client.patch(f"/api/transactions/{t['id']}", json={"excluded": True})
    assert r.json()["excluded"] is True and r.json()["excluded_source"] == "manual"
    assert r.json()["category"] == t["category"]  # category untouched

    after = {m["month"]: m for m in client.get("/api/summary/monthly").json()}
    m = t["month"]
    assert after[m]["spending"] == pytest.approx(before[m]["spending"] + t["amount"], abs=0.01)
    assert after[m]["savings"] == pytest.approx(before[m]["savings"] - t["amount"], abs=0.01)
    o = client.get("/api/summary/overview").json()
    assert o["excluded_count"] == 1 and o["excluded_amount"] == pytest.approx(abs(t["amount"]))
    listed = client.get("/api/transactions", params={"excluded": True}).json()
    assert [i["id"] for i in listed["items"]] == [t["id"]] and listed["net_spending"] == 0

    client.patch(f"/api/transactions/{t['id']}", json={"excluded": False})
    restored = {m["month"]: m for m in client.get("/api/summary/monthly").json()}
    assert restored[m]["spending"] == pytest.approx(before[m]["spending"], abs=0.01)


def test_exclude_rule_and_manual_keep(client):
    r = client.post("/api/rules", json={"pattern": "MARRIOTT", "category": "Travel", "exclude": True})
    assert r.json()["exclude"] is True
    t = client.get("/api/transactions", params={"q": "MARRIOTT"}).json()["items"][0]
    assert t["excluded"] and t["excluded_source"] == "rule"
    # A manual "keep" beats the rule; clearing it hands control back to the rule.
    assert client.patch(f"/api/transactions/{t['id']}", json={"excluded": False}).json()["excluded"] is False
    assert client.patch(f"/api/transactions/{t['id']}", json={"excluded": None}).json()["excluded"] is True


def test_excluded_recurring_charges_not_detected(client):
    for t in client.get("/api/transactions", params={"q": "netflix"}).json()["items"]:
        client.patch(f"/api/transactions/{t['id']}", json={"excluded": True})
    assert "Netflix" not in {r["merchant"] for r in client.get("/api/recurring").json()}


PAYCHECK = {"name": "Acme paycheck", "amount": 3850, "frequency": "semimonthly", "days": [15, 31],
            "match_text": "payroll"}


def test_money_in_needs_review_until_labelled(client):
    queue = client.get("/api/transactions", params={"needs_review": True, "limit": 500}).json()["items"]
    names = {i["merchant"] for i in queue}
    assert {"Acme Payroll", "Interest Paid", "Zelle From Alex Kim", "Venmo Cashout"} <= names
    assert all(i["amount"] > 0 for i in queue)
    assert client.get("/api/summary/overview").json()["needs_review"] == len(queue)

    # The friend paid back half a dinner: label it Dining -> it offsets spending, not income.
    before = {m["month"]: m for m in client.get("/api/summary/monthly").json()}
    z = next(i for i in queue if i["merchant"] == "Zelle From Alex Kim" and i["month"] == "2026-05")
    r = client.patch(f"/api/transactions/{z['id']}", json={"category": "Dining"}).json()
    assert r["kind"] == "refund" and r["needs_review"] is False
    assert r["merchant_different_category"] == 1  # the September one, still guessed as income
    assert r["merchant_needs_review"] == 1
    after = {m["month"]: m for m in client.get("/api/summary/monthly").json()}
    assert after["2026-05"]["income"] == pytest.approx(before["2026-05"]["income"] - 93)
    assert after["2026-05"]["spending"] == pytest.approx(before["2026-05"]["spending"] - 93)
    assert after["2026-05"]["savings"] == pytest.approx(before["2026-05"]["savings"])

    # Labelling as income clears it from the queue too.
    i = next(i for i in queue if i["merchant"] == "Venmo Cashout")
    assert client.patch(f"/api/transactions/{i['id']}", json={"category": "Income"}).json()["kind"] == "income"
    # Confirming a correct guess still offers to label the rest of that sender's deposits.
    interest = next(i for i in queue if i["merchant"] == "Interest Paid")
    r = client.patch(f"/api/transactions/{interest['id']}", json={"category": "Income"}).json()
    assert r["merchant_different_category"] == 0 and r["merchant_needs_review"] == 5


def test_payback_merchant_rule_only_affects_money_in(client):
    r = client.post("/api/rules", json={"pattern": "Zelle From Alex Kim", "match": "merchant",
                                        "category": "Entertainment", "direction": "in"}).json()
    assert r["matched"] == 2
    items = client.get("/api/transactions", params={"q": "alex kim"}).json()["items"]
    assert all(i["kind"] == "refund" and not i["needs_review"] for i in items)
    out = client.get("/api/transactions", params={"q": "jordan smith"}).json()["items"]
    assert all(i["category"] == "Peer-to-Peer" for i in out)


def test_pay_schedule_confirms_paychecks(client):
    assert client.post("/api/income/schedules", json={**PAYCHECK, "days": [15]}).status_code == 422
    assert client.post("/api/income/schedules", json={**PAYCHECK, "frequency": "biweekly"}).status_code == 422
    s = client.post("/api/income/schedules", json=PAYCHECK)
    assert s.status_code == 201 and s.json()["monthly_amount"] == 7700

    payroll = client.get("/api/transactions", params={"q": "payroll", "limit": 50}).json()["items"]
    assert len(payroll) == 12
    assert all(p["category_source"] == "paycheck" and not p["needs_review"] for p in payroll)

    expected = client.get("/api/income/expected").json()
    received = [e for e in expected if e["status"] == "received"]
    assert len(received) == 12 and {e["actual_amount"] for e in received} == {3850}
    assert {e["status"] for e in expected if e["month"] == "2026-10"} <= {"upcoming", "due", "missed"}

    months = {m["month"]: m for m in client.get("/api/summary/monthly").json()}
    assert months["2026-06"]["expected_income"] == 7700


def test_manual_label_beats_paycheck_match(client):
    t = client.get("/api/transactions", params={"q": "payroll", "limit": 1}).json()["items"][0]
    client.patch(f"/api/transactions/{t['id']}", json={"category": "Gifts & Donations"})
    client.post("/api/income/schedules", json=PAYCHECK)
    t2 = client.get("/api/transactions", params={"q": "payroll", "month": t["month"], "limit": 5}).json()["items"]
    mine = next(x for x in t2 if x["id"] == t["id"])
    assert mine["category"] == "Gifts & Donations" and mine["kind"] == "refund"
    assert t["id"] not in {e["transaction_id"] for e in client.get("/api/income/expected").json()}


def test_pay_schedule_crud_persists(client, data_dir, tmp_path):
    sid = client.post("/api/income/schedules", json=PAYCHECK).json()["id"]
    upd = client.put(f"/api/income/schedules/{sid}", json={**PAYCHECK, "amount": 4000}).json()
    assert upd["amount"] == 4000
    settings = Settings(data_dir=data_dir, state_dir=tmp_path / "state", frontend_dist=tmp_path / "nope")
    again = TestClient(create_app(settings)).get("/api/income/schedules").json()
    assert [s["amount"] for s in again] == [4000]
    assert client.put("/api/income/schedules/nope", json=PAYCHECK).status_code == 404
    assert client.delete(f"/api/income/schedules/{sid}").status_code == 204
    assert client.get("/api/income/schedules").json() == []


def test_budgets_crud_progress_and_persistence(client, data_dir, tmp_path):
    assert client.get("/api/budgets").json() == {"budgets": [], "total": 0}
    s = client.get("/api/budgets/suggest").json()
    assert s["Housing"]["suggested"] == 2450 and s["Groceries"]["suggested"] >= s["Groceries"]["average"]

    r = client.put("/api/budgets", json={"budgets": [
        {"category": "Groceries", "amount": 700}, {"category": "Dining", "amount": 250},
        {"category": "Travel", "amount": 0}]})
    assert r.json() == {"budgets": [{"category": "Groceries", "amount": 700}, {"category": "Dining", "amount": 250}],
                        "total": 950}
    assert client.put("/api/budgets", json={"budgets": [{"category": "Income", "amount": 9}]}).status_code == 422
    assert client.put("/api/budgets", json={"budgets": [{"category": "Dining", "amount": 1},
                                                        {"category": "Dining", "amount": 2}]}).status_code == 422
    assert client.put("/api/budgets", json={"budgets": [{"category": "Dining", "amount": -5}]}).status_code == 422

    p = client.get("/api/budgets/progress").json()
    assert p["month"] == "2026-09" and not p["in_progress"]
    by = {c["category"]: c for c in p["categories"]}
    month = {m["month"]: m for m in client.get("/api/summary/monthly").json()}["2026-09"]
    assert by["Groceries"]["spent"] == pytest.approx(month["by_category"]["Groceries"])
    assert {u["category"] for u in p["unbudgeted"]} >= {"Housing", "Utilities"}
    assert p["totals"]["unbudgeted"] == pytest.approx(month["spending"] - p["totals"]["spent"], abs=0.05)

    # Excluding a transaction takes it out of budget spending too.
    t = client.get("/api/transactions", params={"month": "2026-09", "category": "Groceries", "limit": 1}).json()["items"][0]
    client.patch(f"/api/transactions/{t['id']}", json={"excluded": True})
    p2 = client.get("/api/budgets/progress", params={"month": "2026-09"}).json()
    assert p2["categories"][0]["spent"] == pytest.approx(by["Groceries"]["spent"] + t["amount"], abs=0.01)

    h = client.get("/api/budgets/history", params={"months": 3}).json()
    assert [m["month"] for m in h] == ["2026-07", "2026-08", "2026-09"] and h[0]["total_budget"] == 950

    settings = Settings(data_dir=data_dir, state_dir=tmp_path / "state", frontend_dist=tmp_path / "nope")
    assert TestClient(create_app(settings)).get("/api/budgets").json()["total"] == 950
    assert client.get("/api/budgets/progress", params={"month": "bad"}).status_code == 422
