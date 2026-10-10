import { useMemo, useState, type FormEvent } from "react";
import { api } from "../api";
import { money, moneyWhole } from "../format";
import type { BudgetLine, BudgetSuggestions } from "../types";
import { ErrorNotice } from "./common";

const NOT_BUDGETABLE = new Set(["Income", "Credit Card Payment", "Transfers", "Uncategorized"]);

/** Set a monthly amount for each spending category. Blank or 0 means no budget. */
export function BudgetEditor({ categories, current, suggestions, averageIncome, onSaved, onCancel }: {
  categories: string[];
  current: BudgetLine[];
  suggestions: BudgetSuggestions;
  averageIncome: number;
  onSaved: () => void;
  onCancel?: () => void;
}) {
  const rows = useMemo(() => {
    const names = new Set([...categories, ...current.map((b) => b.category)]);
    const list = [...names].filter((c) => !NOT_BUDGETABLE.has(c));
    // Categories you actually spend in first, biggest first.
    return list.sort((a, b) => (suggestions[b]?.average ?? -1) - (suggestions[a]?.average ?? -1) || a.localeCompare(b));
  }, [categories, current, suggestions]);

  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(current.map((b) => [b.category, String(b.amount)])));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();

  const amount = (c: string) => {
    const n = Number(values[c]);
    return Number.isFinite(n) && n > 0 ? n : 0;
  };
  const total = rows.reduce((acc, c) => acc + amount(c), 0);
  const fillSuggestions = (overwrite: boolean) =>
    setValues((v) => {
      const next = { ...v };
      for (const [c, s] of Object.entries(suggestions)) {
        if (!NOT_BUDGETABLE.has(c) && (overwrite || !next[c])) next[c] = String(s.suggested);
      }
      return next;
    });

  async function save(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(undefined);
    try {
      await api.saveBudgets(rows.map((c) => ({ category: c, amount: amount(c) })).filter((b) => b.amount > 0));
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={save}>
      <div className="filters" style={{ justifyContent: "space-between" }}>
        <span className="secondary small">
          Suggestions are your average monthly spending over the last few complete months, rounded up to $10.
        </span>
        <span style={{ display: "flex", gap: 8 }}>
          <button type="button" className="btn btn-sm" onClick={() => fillSuggestions(false)}>Fill blanks with suggestions</button>
          <button type="button" className="btn btn-sm btn-ghost" onClick={() => fillSuggestions(true)}>Use all suggestions</button>
        </span>
      </div>
      {error && <ErrorNotice error={error} />}
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Category</th>
              <th className="num">You usually spend</th>
              <th className="num">Monthly budget</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((c) => {
              const s = suggestions[c];
              return (
                <tr key={c}>
                  <td>{c}</td>
                  <td className="num secondary">
                    {s ? <>{money(s.average)}/mo <span className="muted small">· suggest {moneyWhole(s.suggested)}</span></> : "—"}
                  </td>
                  <td className="num" style={{ width: 170 }}>
                    <input
                      className="input budget-input"
                      type="number"
                      min="0"
                      step="1"
                      inputMode="decimal"
                      placeholder="No budget"
                      value={values[c] ?? ""}
                      aria-label={`Monthly budget for ${c}`}
                      onChange={(e) => setValues({ ...values, [c]: e.target.value })}
                    />
                  </td>
                </tr>
              );
            })}
          </tbody>
          <tfoot>
            <tr>
              <td><strong>Total monthly budget</strong></td>
              <td className="num secondary small">
                {averageIncome > 0 && `Average income ${moneyWhole(averageIncome)}/mo`}
              </td>
              <td className="num">
                <strong>{money(total)}</strong>
                {averageIncome > 0 && (
                  <div className={`small ${total > averageIncome ? "delta-up" : "secondary"}`}>
                    {total > averageIncome
                      ? `${moneyWhole(total - averageIncome)} more than you earn`
                      : `leaves ${moneyWhole(averageIncome - total)} for savings & the rest`}
                  </div>
                )}
              </td>
            </tr>
          </tfoot>
        </table>
      </div>
      <div style={{ display: "flex", gap: 8, marginTop: 14 }}>
        <button className="btn btn-primary" type="submit" disabled={busy}>{busy ? "Saving…" : "Save budget"}</button>
        {onCancel && <button className="btn" type="button" onClick={onCancel}>Cancel</button>}
      </div>
    </form>
  );
}
