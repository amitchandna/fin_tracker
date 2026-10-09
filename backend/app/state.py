"""Persistent user state: custom rules, per-transaction category overrides and
per-file source settings. Stored as one JSON file, written atomically."""

from __future__ import annotations

import json
import os
import tempfile
import threading
import uuid
from pathlib import Path

from .categorizer import UserRule
from .paychecks import PaySchedule


def fingerprint(date: str, amount: float, description: str, occurrence: int = 0) -> str:
    """Identity of a transaction that doesn't depend on file or account names."""
    return f"{date}|{amount:.2f}|{' '.join(description.lower().split())}|{occurrence}"


class Marks:
    """Lookup for per-transaction choices: by ID first, then by fingerprint, so a
    choice survives renaming a file or an account."""

    def __init__(self, records: dict[str, dict]):
        self.by_id = records
        by_fp: dict[str, dict | None] = {}
        for rec in records.values():
            fp = rec.get("fingerprint")
            if fp:
                # Two marks with the same fingerprint are ambiguous; match neither.
                by_fp[fp] = None if fp in by_fp else rec
        self.by_fp = {k: v for k, v in by_fp.items() if v is not None}

    def get(self, txn_id: str, fp: str) -> dict | None:
        return self.by_id.get(txn_id) or self.by_fp.get(fp)

    def __len__(self) -> int:
        return len(self.by_id)


def _record(value, key: str, txn: dict | None) -> dict:
    rec = {key: value}
    if txn:
        rec.update({
            "date": txn["date"], "amount": txn["amount"], "description": txn["description"],
            "account": txn["account"],
            "fingerprint": fingerprint(txn["date"], txn["amount"], txn["description"], txn.get("occurrence", 0)),
        })
    return rec


def _upgrade(records: dict, key: str) -> dict[str, dict]:
    # Older state files stored bare values ({id: "Dining"}); keep reading them.
    return {k: (v if isinstance(v, dict) else {key: v}) for k, v in records.items()}


class StateStore:
    def __init__(self, state_dir: Path):
        self.path = state_dir / "state.json"
        self._lock = threading.RLock()
        self.version = 0
        self._data = {"rules": [], "overrides": {}, "sources": {}, "excluded": {}, "pay_schedules": []}
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text())
                for key in self._data:
                    if isinstance(data.get(key), type(self._data[key])):
                        self._data[key] = data[key]
            except (OSError, json.JSONDecodeError):
                # A corrupt state file shouldn't take the app down; keep it for inspection.
                self.path.replace(self.path.with_suffix(".corrupt.json"))

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".state-", suffix=".json")
        with os.fdopen(fd, "w") as f:
            json.dump(self._data, f, indent=2, sort_keys=True)
        os.replace(tmp, self.path)
        self.version += 1

    # Rules -----------------------------------------------------------------
    def rules(self) -> list[UserRule]:
        with self._lock:
            return [UserRule(**r) for r in self._data["rules"]]

    def add_rule(self, pattern: str, category: str, match: str = "contains", kind: str | None = None,
                 exclude: bool = False, direction: str = "any") -> UserRule:
        with self._lock:
            rule = UserRule(id=uuid.uuid4().hex[:10], pattern=pattern, category=category, match=match, kind=kind,
                            exclude=exclude, direction=direction)
            # Newest rules win, so they go first.
            self._data["rules"].insert(0, rule.to_dict())
            self._save()
            return rule

    def delete_rule(self, rule_id: str) -> bool:
        with self._lock:
            before = len(self._data["rules"])
            self._data["rules"] = [r for r in self._data["rules"] if r["id"] != rule_id]
            if len(self._data["rules"]) == before:
                return False
            self._save()
            return True

    # Per-transaction choices ---------------------------------------------------
    # Each is stored with the transaction's date, amount and description, which keeps
    # state.json readable and lets a choice find its transaction again if IDs change.
    def overrides(self) -> Marks:
        with self._lock:
            return Marks(_upgrade(self._data["overrides"], "category"))

    def set_override(self, txn_id: str, category: str | None, txn: dict | None = None) -> None:
        with self._lock:
            if category:
                self._data["overrides"][txn_id] = _record(category, "category", txn)
            else:
                self._drop("overrides", txn_id, txn)
            self._save()

    def excluded(self) -> Marks:
        """Budget exclusion: True = scrubbed, False = kept despite a rule."""
        with self._lock:
            return Marks(_upgrade(self._data["excluded"], "excluded"))

    def set_excluded(self, txn_id: str, excluded: bool | None, txn: dict | None = None) -> None:
        """``None`` clears the manual choice so rules decide again."""
        with self._lock:
            if excluded is None:
                self._drop("excluded", txn_id, txn)
            else:
                self._data["excluded"][txn_id] = _record(bool(excluded), "excluded", txn)
            self._save()

    def _drop(self, section: str, txn_id: str, txn: dict | None) -> None:
        records = self._data[section]
        records.pop(txn_id, None)
        if txn:
            # The mark may live under an older ID and have matched by fingerprint.
            fp = fingerprint(txn["date"], txn["amount"], txn["description"], txn.get("occurrence", 0))
            for k in [k for k, v in records.items() if isinstance(v, dict) and v.get("fingerprint") == fp]:
                records.pop(k)

    # Expected income ---------------------------------------------------------
    def pay_schedules(self) -> list[PaySchedule]:
        with self._lock:
            return [PaySchedule(**p) for p in self._data["pay_schedules"]]

    def save_pay_schedule(self, data: dict, schedule_id: str | None = None) -> PaySchedule | None:
        """Create (no id) or replace (id) a pay schedule. Returns None for an unknown id."""
        with self._lock:
            items = self._data["pay_schedules"]
            if schedule_id is None:
                sched = PaySchedule(id=uuid.uuid4().hex[:10], **data)
                items.append(sched.to_dict())
            else:
                idx = next((i for i, p in enumerate(items) if p["id"] == schedule_id), None)
                if idx is None:
                    return None
                sched = PaySchedule(id=schedule_id, **data)
                items[idx] = sched.to_dict()
            self._save()
            return sched

    def delete_pay_schedule(self, schedule_id: str) -> bool:
        with self._lock:
            before = len(self._data["pay_schedules"])
            self._data["pay_schedules"] = [p for p in self._data["pay_schedules"] if p["id"] != schedule_id]
            if len(self._data["pay_schedules"]) == before:
                return False
            self._save()
            return True

    # Source settings ---------------------------------------------------------
    def source_settings(self) -> dict[str, dict]:
        with self._lock:
            return {k: dict(v) for k, v in self._data["sources"].items()}

    def set_source_settings(self, file_name: str, settings: dict) -> None:
        with self._lock:
            clean = {k: v for k, v in settings.items() if v is not None}
            if clean:
                self._data["sources"][file_name] = clean
            else:
                self._data["sources"].pop(file_name, None)
            self._save()
