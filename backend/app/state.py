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


class StateStore:
    def __init__(self, state_dir: Path):
        self.path = state_dir / "state.json"
        self._lock = threading.RLock()
        self.version = 0
        self._data = {"rules": [], "overrides": {}, "sources": {}}
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

    def add_rule(self, pattern: str, category: str, match: str = "contains", kind: str | None = None) -> UserRule:
        with self._lock:
            rule = UserRule(id=uuid.uuid4().hex[:10], pattern=pattern, category=category, match=match, kind=kind)
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

    # Overrides ---------------------------------------------------------------
    def overrides(self) -> dict[str, str]:
        with self._lock:
            return dict(self._data["overrides"])

    def set_override(self, txn_id: str, category: str | None) -> None:
        with self._lock:
            if category:
                self._data["overrides"][txn_id] = category
            else:
                self._data["overrides"].pop(txn_id, None)
            self._save()

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
