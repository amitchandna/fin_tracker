import { useState } from "react";
import { api } from "../api";
import { dateLabel, money } from "../format";
import type { Transaction, TransactionUpdate } from "../types";
import { useAsync } from "../useAsync";
import { Card, ErrorNotice, Loading } from "./common";

const NOT_SPENDING = new Set(["Income", "Credit Card Payment", "Transfers", "Uncategorized"]);

interface Suggestion {
  txn: TransactionUpdate;
  count: number;
}

/**
 * Every deposit the app only guessed at. The user says whether it's income, or
 * someone paying them back (which offsets spending in the category they pick).
 */
export function MoneyInReview({ categories, version, onDataChanged }: {
  categories: string[];
  version: number;
  onDataChanged: () => void;
}) {
  const queue = useAsync(() => api.transactions({ needs_review: "true", sort: "-date", limit: 200 }), [version]);
  const [busy, setBusy] = useState<string>();
  const [error, setError] = useState<string>();
  const [note, setNote] = useState<string>();
  const [suggestion, setSuggestion] = useState<Suggestion>();
  const spendCategories = categories.filter((c) => !NOT_SPENDING.has(c));

  async function label(t: Transaction, category: string) {
    setBusy(t.id);
    setError(undefined);
    try {
      const r = await api.setCategory(t.id, category);
      setNote(category === "Income"
        ? `${r.merchant} (${money(r.amount)}) saved as income.`
        : `${r.merchant} (${money(r.amount)}) saved as paid back. It reduces your ${category} spending instead of counting as income.`);
      // Offer to label the rest from this sender: any still unreviewed, or already labelled differently.
      const count = Math.max(r.merchant_needs_review, r.merchant_different_category);
      setSuggestion(count > 0 ? { txn: r, count } : undefined);
      onDataChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(undefined);
    }
  }

  async function exclude(t: Transaction) {
    setBusy(t.id);
    try {
      await api.setExcluded(t.id, true);
      setNote(`${t.merchant} (${money(t.amount)}) left out of the budget.`);
      setSuggestion(undefined);
      onDataChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(undefined);
    }
  }

  async function applyToMerchant(sg: Suggestion) {
    try {
      const rule = await api.addRule({
        pattern: sg.txn.merchant, match: "merchant", category: sg.txn.category, kind: null, exclude: false,
        direction: "in",
      });
      setNote(`Saved as a rule: money in from ${sg.txn.merchant} (${rule.matched} so far, and future ones) is ` +
        (sg.txn.category === "Income" ? "income." : `paid back against ${sg.txn.category}.`));
      setSuggestion(undefined);
      onDataChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  const items = queue.data?.items ?? [];
  if (queue.error) return <ErrorNotice error={queue.error} onRetry={queue.reload} />;
  if (!queue.data) return <Loading />;
  if (!items.length && !note) return null;

  return (
    <Card
      title={items.length ? `Money in to review (${items.length})` : "Money in to review"}
      sub={
        <>
          Is each deposit <strong>income</strong>, or someone <strong>paying you back</strong> (e.g. a friend
          covering their movie ticket)? Paid-back money reduces spending in the category you pick instead of
          counting as income. Until you choose, the app uses its best guess.
        </>
      }
    >
      {(note || suggestion) && (
        <div className="notice notice-info" role="status" style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
          <span style={{ flex: "1 1 300px" }}>
            {note && <>✓ {note} </>}
            {suggestion && (
              <>Do the same for the {suggestion.count} other deposit{suggestion.count === 1 ? "" : "s"} from{" "}
                <strong>{suggestion.txn.merchant}</strong> and any future ones?</>
            )}
          </span>
          {suggestion && (
            <button className="btn btn-sm btn-primary" onClick={() => applyToMerchant(suggestion)}>Apply to all</button>
          )}
          <button className="btn btn-sm btn-ghost" onClick={() => { setNote(undefined); setSuggestion(undefined); }}>
            Dismiss
          </button>
        </div>
      )}
      {error && <ErrorNotice error={error} />}
      {items.length === 0 ? (
        <div className="muted">All caught up. Every deposit is labelled.</div>
      ) : (
        <div className="table-wrap">
          <table className="review-table">
            <thead>
              <tr>
                <th>Date</th>
                <th>From</th>
                <th className="num">Amount</th>
                <th>What is it?</th>
              </tr>
            </thead>
            <tbody>
              {items.map((t) => (
                <tr key={t.id} style={{ opacity: busy === t.id ? 0.5 : 1 }}>
                  <td className="secondary" style={{ whiteSpace: "nowrap" }}>{dateLabel(t.date)}</td>
                  <td>
                    <div>{t.merchant}</div>
                    <div className="small muted desc" title={t.description}>{t.description} · {t.account}</div>
                    <div className="small muted">
                      Best guess: {t.kind === "income" ? "income" : `paid back for ${t.category}`}
                    </div>
                  </td>
                  <td className="num amount-in">+{money(t.amount)}</td>
                  <td>
                    <div className="review-actions">
                      <button className="btn btn-sm" disabled={busy === t.id} onClick={() => label(t, t.category)}
                              title="The guess is right">
                        ✓ {t.kind === "income" ? "Income" : `Paid back: ${t.category}`}
                      </button>
                      {t.kind !== "income" && (
                        <button className="btn btn-sm" disabled={busy === t.id} onClick={() => label(t, "Income")}>
                          Income
                        </button>
                      )}
                      <select
                        className="select"
                        value=""
                        disabled={busy === t.id}
                        onChange={(e) => e.target.value && label(t, e.target.value)}
                        aria-label={`Paid back for which category: ${t.merchant}`}
                      >
                        <option value="">Paid back for…</option>
                        {spendCategories.map((c) => <option key={c} value={c}>{c}</option>)}
                      </select>
                      <button className="btn btn-sm btn-ghost" disabled={busy === t.id} onClick={() => exclude(t)}
                              title="Leave it out of income and spending entirely">
                        Ignore
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
