"""FastAPI application: JSON API under /api, plus the built frontend when present."""

from __future__ import annotations

import csv
import io
import re
from datetime import date
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import analytics
from .categorizer import CATEGORIES
from .config import Settings
from .ledger import Ledger
from .models import AccountType, Kind, PaymentMethod, Transaction
from .state import StateStore


class RuleIn(BaseModel):
    pattern: str = Field(min_length=1, max_length=200)
    category: str = Field(min_length=1, max_length=60)
    match: Literal["contains", "regex", "merchant"] = "contains"
    kind: Literal["expense", "income", "transfer", "refund"] | None = None
    exclude: bool = False


class TransactionUpdate(BaseModel):
    """Only the fields sent are changed. ``category: null`` resets to automatic;
    ``excluded: null`` clears a manual choice so rules decide again."""

    category: str | None = Field(default=None, max_length=60)
    excluded: bool | None = None


class SourceSettingsIn(BaseModel):
    name: str | None = Field(default=None, max_length=80)
    account_type: Literal["credit_card", "checking", "savings"] | None = None
    invert_amounts: bool | None = None
    day_first: bool | None = None


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    state = StateStore(settings.state_dir)
    ledger = Ledger(settings.data_dir, state)

    app = FastAPI(title="Fin Tracker", version="1.0.0")
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                       allow_methods=["*"], allow_headers=["*"])
    app.state.ledger = ledger
    app.state.settings = settings

    def filtered(month: str | None = None, start: date | None = None, end: date | None = None,
                 category: list[str] | None = None, account: list[str] | None = None,
                 payment_method: list[str] | None = None, account_type: list[str] | None = None,
                 kind: list[str] | None = None, recurring: bool | None = None,
                 q: str | None = None, excluded: bool | None = None) -> list[Transaction]:
        txns = ledger.snapshot().transactions
        out = []
        ql = q.lower() if q else None
        for t in txns:
            if month and t.month != month:
                continue
            if start and t.date < start:
                continue
            if end and t.date > end:
                continue
            if category and t.category not in category:
                continue
            if account and t.account not in account:
                continue
            if payment_method and t.payment_method.value not in payment_method:
                continue
            if account_type and t.account_type.value not in account_type:
                continue
            if kind and t.kind.value not in kind:
                continue
            if recurring is not None and t.is_recurring != recurring:
                continue
            if excluded is not None and t.excluded != excluded:
                continue
            if ql and ql not in t.description.lower() and ql not in t.merchant.lower() and ql not in t.category.lower():
                continue
            out.append(t)
        return out

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/config")
    def config():
        snap = ledger.snapshot()
        return {
            "data_dir": str(settings.data_dir),
            "data_dir_exists": settings.data_dir.is_dir(),
            "state_file": str(state.path),
            "files": len(snap.sources),
            "transactions": len(snap.transactions),
            "loaded_at": snap.loaded_at.isoformat(timespec="seconds"),
        }

    @app.get("/api/meta")
    def meta():
        snap = ledger.snapshot()
        used = {t.category for t in snap.transactions}
        rules = state.rules()
        return {
            "categories": sorted(set(CATEGORIES) | used | {r.category for r in rules}),
            "accounts": sorted({t.account for t in snap.transactions}),
            "months": sorted({t.month for t in snap.transactions}),
            "payment_methods": [p.value for p in PaymentMethod],
            "account_types": [a.value for a in AccountType if a != AccountType.UNKNOWN],
            "kinds": [k.value for k in Kind],
        }

    @app.post("/api/rescan")
    def rescan():
        snap = ledger.snapshot(force=True)
        return {"files": len(snap.sources), "transactions": len(snap.transactions)}

    @app.get("/api/sources")
    def sources():
        return [s.to_dict() for s in ledger.snapshot().sources]

    @app.put("/api/sources/{file_name:path}")
    def update_source(file_name: str, body: SourceSettingsIn):
        known = {s.file_name for s in ledger.snapshot().sources}
        if file_name not in known:
            raise HTTPException(404, "Unknown source file")
        state.set_source_settings(file_name, body.model_dump())
        return next(s.to_dict() for s in ledger.snapshot().sources if s.file_name == file_name)

    @app.get("/api/transactions")
    def transactions(
        month: str | None = None, start: date | None = None, end: date | None = None,
        category: list[str] | None = Query(None), account: list[str] | None = Query(None),
        payment_method: list[str] | None = Query(None), account_type: list[str] | None = Query(None),
        kind: list[str] | None = Query(None), recurring: bool | None = None, q: str | None = None,
        excluded: bool | None = None,
        sort: Literal["date", "-date", "amount", "-amount", "category", "merchant"] = "-date",
        limit: int = Query(100, ge=1, le=5000), offset: int = Query(0, ge=0),
    ):
        txns = filtered(month, start, end, category, account, payment_method, account_type, kind, recurring, q,
                        excluded)
        key, reverse = sort.lstrip("-"), sort.startswith("-")
        sorters = {"date": lambda t: (t.date, t.id), "amount": lambda t: abs(t.amount),
                   "category": lambda t: t.category, "merchant": lambda t: t.merchant.lower()}
        txns = sorted(txns, key=sorters[key], reverse=reverse)
        total_spend = sum(analytics.spend_value(t) for t in analytics.budgeted(txns))
        return {
            "total": len(txns),
            "excluded": sum(1 for t in txns if t.excluded),
            "net_spending": round(total_spend, 2),
            "items": [t.to_dict() for t in txns[offset: offset + limit]],
        }

    @app.patch("/api/transactions/{txn_id}")
    def update_transaction(txn_id: str, body: TransactionUpdate):
        txn = next((t for t in ledger.snapshot().transactions if t.id == txn_id), None)
        if txn is None:
            raise HTTPException(404, "Transaction not found")
        ident = {**txn.to_dict(), "occurrence": txn.occurrence}
        if "category" in body.model_fields_set:
            state.set_override(txn_id, body.category, ident)
        if "excluded" in body.model_fields_set:
            state.set_excluded(txn_id, body.excluded, ident)
        snap = ledger.snapshot()
        txn = next(t for t in snap.transactions if t.id == txn_id)
        # How many other transactions from this merchant differ, so the UI can offer to
        # remember the choice for all of them (and future ones) with a merchant rule.
        same = [t for t in snap.transactions if t.merchant == txn.merchant and t.id != txn.id]
        return {
            **txn.to_dict(),
            "merchant_total": len(same),
            "merchant_different_category": sum(1 for t in same if t.category != txn.category),
            "merchant_different_excluded": sum(1 for t in same if t.excluded != txn.excluded),
        }

    @app.get("/api/transactions/export")
    def export(month: str | None = None, account: list[str] | None = Query(None),
               payment_method: list[str] | None = Query(None)):
        txns = filtered(month=month, account=account, payment_method=payment_method)
        buf = io.StringIO()
        fields = ["date", "description", "merchant", "amount", "category", "kind", "payment_method",
                  "account", "account_type", "is_recurring", "excluded", "source_file"]
        w = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for t in sorted(txns, key=lambda t: t.date):
            w.writerow(t.to_dict())
        return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                                 headers={"Content-Disposition": "attachment; filename=fin_tracker_export.csv"})

    @app.get("/api/summary/overview")
    def summary_overview(account: list[str] | None = Query(None), payment_method: list[str] | None = Query(None),
                         account_type: list[str] | None = Query(None)):
        txns = filtered(account=account, payment_method=payment_method, account_type=account_type)
        snap = ledger.snapshot()
        ids = {t.id for t in txns}
        recurring = [s for s in snap.recurring if any(i in ids for i in s.transaction_ids)]
        return analytics.overview(txns, recurring)

    @app.get("/api/summary/monthly")
    def summary_monthly(start: date | None = None, end: date | None = None,
                        account: list[str] | None = Query(None), payment_method: list[str] | None = Query(None),
                        account_type: list[str] | None = Query(None), category: list[str] | None = Query(None)):
        txns = filtered(start=start, end=end, account=account, payment_method=payment_method,
                        account_type=account_type, category=category)
        return analytics.monthly_summary(txns)

    @app.get("/api/summary/categories")
    def summary_categories(month: str | None = None, start: date | None = None, end: date | None = None,
                           account: list[str] | None = Query(None), payment_method: list[str] | None = Query(None),
                           account_type: list[str] | None = Query(None)):
        txns = filtered(month=month, start=start, end=end, account=account, payment_method=payment_method,
                        account_type=account_type)
        return analytics.category_breakdown(txns)

    @app.get("/api/summary/income")
    def summary_income(month: str | None = None, start: date | None = None, end: date | None = None,
                       account: list[str] | None = Query(None)):
        txns = filtered(month=month, start=start, end=end, account=account)
        return analytics.income_sources(txns)

    @app.get("/api/recurring")
    def recurring(include_inactive: bool = True):
        series = ledger.snapshot().recurring
        if not include_inactive:
            series = [s for s in series if s.active]
        return [s.to_dict() for s in series]

    @app.get("/api/rules")
    def rules():
        return [r.to_dict() for r in state.rules()]

    @app.post("/api/rules", status_code=201)
    def add_rule(body: RuleIn):
        if body.match == "merchant" and not any(
                t.merchant.lower() == body.pattern.strip().lower() for t in ledger.snapshot().transactions):
            raise HTTPException(422, f"No merchant named {body.pattern!r}")
        if body.match == "regex":
            try:
                re.compile(body.pattern)
            except re.error as exc:
                raise HTTPException(422, f"Invalid regular expression: {exc}") from exc
        rule = state.add_rule(body.pattern, body.category.strip(), body.match, body.kind, body.exclude)
        matched = sum(1 for t in ledger.snapshot().transactions if rule.matches(t.description))
        return {**rule.to_dict(), "matched": matched}

    @app.delete("/api/rules/{rule_id}", status_code=204)
    def delete_rule(rule_id: str):
        if not state.delete_rule(rule_id):
            raise HTTPException(404, "Rule not found")

    # Serve the built single-page app, if it has been built.
    dist = settings.frontend_dist
    if dist.is_dir() and (dist / "index.html").exists():
        if (dist / "assets").is_dir():
            app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            if path.startswith("api/"):
                raise HTTPException(404)
            candidate = (dist / path).resolve()
            if path and candidate.is_file() and dist.resolve() in candidate.parents:
                return FileResponse(candidate)
            return FileResponse(dist / "index.html")

    return app


app = create_app()
