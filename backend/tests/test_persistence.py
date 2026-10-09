"""Choices a user makes (categories, exclusions, rules) must survive restarts,
file renames, account renames and fresh re-exports."""

import json
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


def launch(data_dir: Path) -> TestClient:
    """A fresh app process: nothing carried over except what's on disk."""
    settings = Settings(data_dir=data_dir, state_dir=data_dir / ".fintracker", frontend_dist=data_dir / "nope")
    return TestClient(create_app(settings))


def find(client, q):
    return client.get("/api/transactions", params={"q": q}).json()["items"][0]


def test_category_survives_restart(data_dir):
    c = launch(data_dir)
    t = find(c, "CHECK 1043")
    c.patch(f"/api/transactions/{t['id']}", json={"category": "Home"})
    t2 = find(launch(data_dir), "CHECK 1043")
    assert (t2["category"], t2["category_source"]) == ("Home", "manual")


def test_exclusion_survives_restart(data_dir):
    c = launch(data_dir)
    t = find(c, "DELTA AIR")
    c.patch(f"/api/transactions/{t['id']}", json={"excluded": True})
    assert find(launch(data_dir), "DELTA AIR")["excluded"] is True


def test_rules_survive_restart(data_dir):
    launch(data_dir).post("/api/rules", json={"pattern": "STARBUCKS", "category": "Coffee"})
    assert find(launch(data_dir), "STARBUCKS")["category"] == "Coffee"


def test_choices_survive_account_rename(data_dir):
    c = launch(data_dir)
    t = find(c, "CHECK 1043")
    c.patch(f"/api/transactions/{t['id']}", json={"category": "Home"})
    c.put("/api/sources/wells_checking.csv", json={"name": "Joint Checking"})
    t2 = find(launch(data_dir), "CHECK 1043")
    assert t2["account"] == "Joint Checking" and t2["category"] == "Home"


def test_choices_survive_file_rename_and_reexport(data_dir):
    c = launch(data_dir)
    c.patch(f"/api/transactions/{find(c, 'CHECK 1043')['id']}", json={"category": "Home"})
    c.patch(f"/api/transactions/{find(c, 'DELTA AIR')['id']}", json={"excluded": True})
    # A new download of the same accounts saved under different names.
    (data_dir / "wells_checking.csv").rename(data_dir / "bank_export_october.csv")
    (data_dir / "chase_sapphire_credit.csv").rename(data_dir / "Chase7788_Activity.csv")
    c2 = launch(data_dir)
    assert find(c2, "CHECK 1043")["category"] == "Home"
    assert find(c2, "DELTA AIR")["excluded"] is True


def test_reset_clears_mark_matched_by_fingerprint(data_dir):
    c = launch(data_dir)
    c.patch(f"/api/transactions/{find(c, 'CHECK 1043')['id']}", json={"category": "Home"})
    (data_dir / "wells_checking.csv").rename(data_dir / "renamed.csv")
    c2 = launch(data_dir)
    t = find(c2, "CHECK 1043")
    assert t["category"] == "Home"
    assert c2.patch(f"/api/transactions/{t['id']}", json={"category": None}).json()["category"] == "Uncategorized"
    assert find(launch(data_dir), "CHECK 1043")["category"] == "Uncategorized"


def test_state_file_is_readable(data_dir):
    c = launch(data_dir)
    c.patch(f"/api/transactions/{find(c, 'CHECK 1043')['id']}", json={"category": "Home"})
    state = json.loads((data_dir / ".fintracker" / "state.json").read_text())
    (rec,) = state["overrides"].values()
    assert rec["category"] == "Home" and rec["description"] == "CHECK 1043" and rec["date"] == "2026-06-03"
    assert c.get("/api/config").json()["state_file"].endswith("state.json")


def test_legacy_state_format_still_loads(data_dir):
    c = launch(data_dir)
    tid = find(c, "CHECK 1043")["id"]
    path = data_dir / ".fintracker" / "state.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"overrides": {tid: "Home"}, "excluded": {tid: True}}))
    t = find(launch(data_dir), "CHECK 1043")
    assert t["category"] == "Home" and t["excluded"] is True


def test_merchant_rule_applies_to_past_and_future(data_dir):
    c = launch(data_dir)
    t = find(c, "STARBUCKS")
    r = c.patch(f"/api/transactions/{t['id']}", json={"category": "Coffee"}).json()
    assert r["merchant_different_category"] == r["merchant_total"] > 0
    rule = c.post("/api/rules", json={"pattern": r["merchant"], "match": "merchant", "category": "Coffee"}).json()
    assert rule["matched"] == r["merchant_total"] + 1
    # A charge arriving in next month's export is categorized without asking again.
    (data_dir / "new_card.csv").write_text("Date,Description,Amount\n2026-10-02,STARBUCKS STORE 99999,-6.10\n")
    items = launch(data_dir).get("/api/transactions", params={"q": "starbucks", "limit": 500}).json()["items"]
    assert {i["category"] for i in items} == {"Coffee"}
    assert any(i["date"] == "2026-10-02" for i in items)


def test_unknown_merchant_rule_rejected(data_dir):
    r = launch(data_dir).post("/api/rules", json={"pattern": "Nope Inc", "match": "merchant", "category": "X"})
    assert r.status_code == 422
