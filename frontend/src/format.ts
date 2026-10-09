import type { AccountType, Kind, PaymentMethod } from "./types";

const currency = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
const currencyWhole = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
const compact = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", notation: "compact", maximumFractionDigits: 1 });

export const money = (n: number) => currency.format(n);
export const moneyWhole = (n: number) => currencyWhole.format(n);
export const moneyCompact = (n: number) => (Math.abs(n) < 1000 ? currencyWhole.format(n) : compact.format(n));
export const percent = (n: number) => `${(n * 100).toFixed(n < 0.1 ? 1 : 0)}%`;

/** "2026-04" -> "Apr 2026" (or "Apr" when short). */
export function monthLabel(month: string, short = false): string {
  const [y, m] = month.split("-").map(Number);
  const d = new Date(Date.UTC(y, m - 1, 1));
  return d.toLocaleDateString("en-US", { month: "short", year: short ? undefined : "numeric", timeZone: "UTC" });
}

export function dateLabel(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString("en-US", {
    month: "short", day: "numeric", year: "numeric", timeZone: "UTC",
  });
}

export const PAYMENT_METHOD_LABELS: Record<PaymentMethod, string> = {
  credit: "Credit card",
  debit: "Debit / bank",
  transfer: "Bank transfer",
  check: "Check",
  cash: "Cash / ATM",
};

export const ACCOUNT_TYPE_LABELS: Record<AccountType, string> = {
  credit_card: "Credit card",
  checking: "Checking",
  savings: "Savings",
  unknown: "Unknown",
};

export const KIND_LABELS: Record<Kind, string> = {
  expense: "Expense",
  refund: "Refund",
  income: "Income",
  transfer: "Transfer",
};

export const FREQUENCY_LABELS: Record<string, string> = {
  weekly: "Weekly",
  biweekly: "Every 2 weeks",
  monthly: "Monthly",
  quarterly: "Quarterly",
  yearly: "Yearly",
};

/** Percentage change, or null when there's no meaningful base. */
export function change(current: number, previous: number | undefined | null): number | null {
  if (previous === undefined || previous === null || Math.abs(previous) < 0.01) return null;
  return (current - previous) / Math.abs(previous);
}
