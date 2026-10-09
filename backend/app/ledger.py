"""The ledger: scans the data directory, parses every CSV, classifies and
de-duplicates transactions, and caches the result until files or settings change."""

from __future__ import annotations

import hashlib
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .categorizer import CARD_PAYMENT, INCOME, TRANSFERS, classify, detect_payment_method, normalize_merchant
from .models import Kind, ParsedFile, Transaction
from .parser import account_name_from_file, parse_csv_file
from .recurring import RecurringSeries, detect_recurring
from .state import StateStore, fingerprint


@dataclass
class SourceInfo:
    file_name: str
    account: str
    account_type: str
    transactions: int
    duplicates: int
    first_date: str | None
    last_date: str | None
    columns: dict
    inverted: bool
    warnings: list[str]
    error: str | None
    settings: dict
    size_bytes: int
    modified: str

    def to_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class Snapshot:
    transactions: list[Transaction] = field(default_factory=list)
    sources: list[SourceInfo] = field(default_factory=list)
    recurring: list[RecurringSeries] = field(default_factory=list)
    loaded_at: datetime = field(default_factory=datetime.now)


def _txn_id(account: str, date: str, amount: float, description: str, n: int) -> str:
    raw = f"{account.lower()}|{date}|{amount:.2f}|{description.lower()}|{n}"
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


class Ledger:
    def __init__(self, data_dir: Path, state: StateStore):
        self.data_dir = data_dir
        self.state = state
        self._lock = threading.Lock()
        self._signature: tuple | None = None
        self._snapshot = Snapshot()

    def csv_files(self) -> list[Path]:
        if not self.data_dir.is_dir():
            return []
        return sorted(
            p for p in self.data_dir.rglob("*")
            if p.is_file() and p.suffix.lower() == ".csv"
            and not any(part.startswith(".") for part in p.relative_to(self.data_dir).parts)
        )

    def _current_signature(self, files: list[Path]) -> tuple:
        stats = []
        for p in files:
            try:
                st = p.stat()
                stats.append((str(p), st.st_mtime_ns, st.st_size))
            except OSError:
                continue
        return (tuple(stats), self.state.version)

    def snapshot(self, force: bool = False) -> Snapshot:
        with self._lock:
            files = self.csv_files()
            sig = self._current_signature(files)
            if force or sig != self._signature:
                self._snapshot = self._build(files)
                self._signature = sig
            return self._snapshot

    def _build(self, files: list[Path]) -> Snapshot:
        rules = self.state.rules()
        overrides = self.state.overrides()
        exclusions = self.state.excluded()
        settings = self.state.source_settings()

        transactions: list[Transaction] = []
        sources: list[SourceInfo] = []
        seen_ids: set[str] = set()
        seen_hashes: dict[str, str] = {}

        for path in files:
            rel = str(path.relative_to(self.data_dir))
            file_settings = settings.get(rel, {})
            parsed: ParsedFile = parse_csv_file(path, file_settings, display_name=rel)
            st = path.stat()
            duplicates = 0
            identical = False
            added = 0
            dates = []

            if parsed.content_hash and parsed.content_hash in seen_hashes and not parsed.error:
                parsed.warnings.append(f"Identical to {seen_hashes[parsed.content_hash]}; skipped")
                duplicates = len(parsed.rows)
                identical = True
                parsed.rows = []
            elif parsed.content_hash:
                seen_hashes[parsed.content_hash] = rel

            occurrence: dict[tuple, int] = {}
            for row in parsed.rows:
                key = (row.date, round(row.amount, 2), row.description.lower())
                n = occurrence.get(key, 0)
                occurrence[key] = n + 1
                # IDs come from the file name, not the display name, so renaming an account keeps them.
                tid = _txn_id(account_name_from_file(path.name), row.date.isoformat(), row.amount,
                              row.description, n)
                if tid in seen_ids:
                    # Overlapping exports of the same account (e.g. Jan-Mar and Feb-Apr).
                    duplicates += 1
                    continue
                seen_ids.add(tid)

                c = classify(row.description, row.amount, parsed.account_type, row.source_category, rules)
                category, kind, category_source = c.category, c.kind, c.category_source
                fp = fingerprint(row.date.isoformat(), row.amount, row.description, n)
                override = overrides.get(tid, fp)
                if override and override.get("category"):
                    category, category_source = override["category"], "manual"
                    kind = _kind_for_manual(category, row.amount, kind)
                excluded, excluded_source = c.excluded, ("rule" if c.excluded else None)
                exclusion = exclusions.get(tid, fp)
                if exclusion and "excluded" in exclusion:
                    excluded, excluded_source = bool(exclusion["excluded"]), "manual"

                transactions.append(Transaction(
                    id=tid,
                    date=row.date,
                    description=row.description,
                    amount=row.amount,
                    source_file=rel,
                    account=parsed.account,
                    account_type=parsed.account_type,
                    payment_method=detect_payment_method(row.description, parsed.account_type),
                    kind=kind,
                    category=category,
                    merchant=normalize_merchant(row.description),
                    source_category=row.source_category,
                    category_source=category_source,
                    excluded=excluded,
                    excluded_source=excluded_source if excluded else None,
                    occurrence=n,
                ))
                dates.append(row.date)
                added += 1

            if duplicates and not identical:
                parsed.warnings.append(f"{duplicates} transaction(s) already present in another file were skipped")

            sources.append(SourceInfo(
                file_name=rel,
                account=parsed.account,
                account_type=parsed.account_type.value,
                transactions=added,
                duplicates=duplicates,
                first_date=min(dates).isoformat() if dates else None,
                last_date=max(dates).isoformat() if dates else None,
                columns=parsed.columns,
                inverted=parsed.inverted,
                warnings=parsed.warnings,
                error=parsed.error,
                settings=file_settings,
                size_bytes=st.st_size,
                modified=datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
            ))

        transactions.sort(key=lambda t: (t.date, t.id), reverse=True)
        recurring = detect_recurring([t for t in transactions if not t.excluded])
        by_id = {t.id: t for t in transactions}
        for s in recurring:
            for tid in s.transaction_ids:
                if tid in by_id:
                    by_id[tid].is_recurring = True
                    by_id[tid].recurring_id = s.id
        return Snapshot(transactions=transactions, sources=sources, recurring=recurring)


def _kind_for_manual(category: str, amount: float, current: Kind) -> Kind:
    if category in (CARD_PAYMENT, TRANSFERS):
        return Kind.TRANSFER
    if category == INCOME:
        return Kind.INCOME if amount > 0 else Kind.EXPENSE
    if amount < 0:
        return Kind.EXPENSE
    # Money in, re-labelled as a spending category: treat it as a refund against that category.
    return Kind.REFUND
