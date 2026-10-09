"""Core data types shared across the backend."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum


class AccountType(str, Enum):
    CREDIT_CARD = "credit_card"
    CHECKING = "checking"
    SAVINGS = "savings"
    UNKNOWN = "unknown"


class PaymentMethod(str, Enum):
    """How money moved. Credit-card rows are always ``credit``; bank rows are
    refined from the description (ACH, check, ATM, ...) and default to ``debit``."""

    CREDIT = "credit"
    DEBIT = "debit"
    TRANSFER = "transfer"  # ACH / wire / Zelle / Venmo / online bank transfers
    CHECK = "check"
    CASH = "cash"  # ATM withdrawals


class Kind(str, Enum):
    """What a transaction means for spending totals."""

    EXPENSE = "expense"  # money spent; counts toward spending
    REFUND = "refund"  # money returned for a purchase; offsets spending
    INCOME = "income"  # money earned
    TRANSFER = "transfer"  # moving money between your own accounts (incl. card payments)


@dataclass
class Transaction:
    id: str
    date: date
    description: str
    amount: float  # signed: negative = money out, positive = money in
    source_file: str
    account: str
    account_type: AccountType
    payment_method: PaymentMethod
    kind: Kind
    category: str
    merchant: str
    source_category: str | None = None
    category_source: str = "auto"  # auto | rule | source | manual
    is_recurring: bool = False
    recurring_id: str | None = None
    excluded: bool = False  # scrubbed from every budget total, still listed
    excluded_source: str | None = None  # manual | rule

    @property
    def month(self) -> str:
        return self.date.strftime("%Y-%m")

    @property
    def abs_amount(self) -> float:
        return abs(self.amount)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "date": self.date.isoformat(),
            "month": self.month,
            "description": self.description,
            "merchant": self.merchant,
            "amount": round(self.amount, 2),
            "source_file": self.source_file,
            "account": self.account,
            "account_type": self.account_type.value,
            "payment_method": self.payment_method.value,
            "kind": self.kind.value,
            "category": self.category,
            "category_source": self.category_source,
            "source_category": self.source_category,
            "is_recurring": self.is_recurring,
            "recurring_id": self.recurring_id,
            "excluded": self.excluded,
            "excluded_source": self.excluded_source,
        }


@dataclass
class RawRow:
    """A row after column mapping and sign normalisation, before categorisation."""

    date: date
    description: str
    amount: float  # signed: negative = money out
    source_category: str | None = None


@dataclass
class ParsedFile:
    file_name: str
    account: str
    account_type: AccountType
    rows: list[RawRow] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error: str | None = None
    columns: dict[str, str | None] = field(default_factory=dict)
    inverted: bool = False
    content_hash: str = ""
    skipped_rows: int = 0
