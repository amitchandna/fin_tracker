import { useEffect, useState } from "react";
import { api } from "../api";
import { ErrorNotice, Loading } from "../components/common";
import { dateLabel, KIND_LABELS, money, monthLabel, PAYMENT_METHOD_LABELS } from "../format";
import type { Kind, Meta, PaymentMethod, ScopeFilter, Transaction, TransactionUpdate } from "../types";
import { useAsync } from "../useAsync";

export interface TxnFilters {
  month?: string;
  category?: string[];
  account?: string[];
  payment_method?: PaymentMethod[];
  kind?: Kind[];
  recurring?: boolean;
  /** true = only scrubbed transactions, false = only those counted in the budget */
  excluded?: boolean;
  /** only money in that still needs labelling as income or paid back */
  needs_review?: boolean;
  q?: string;
}

type Sort = "-date" | "date" | "-amount" | "amount" | "category" | "merchant";

/** Offer to remember a one-off choice for every transaction from the same merchant. */
interface Suggestion {
  txn: TransactionUpdate;
  action: "category" | "exclude";
  count: number;
}

interface Props {
  meta: Meta;
  stateFile: string;
  scope: ScopeFilter;
  filters: TxnFilters;
  onFiltersChange: (f: TxnFilters) => void;
  version: number;
  onDataChanged: () => void;
}

const PAGE = 50;
const SOURCE_LABEL: Record<Transaction["category_source"], string> = {
  auto: "Auto-categorized",
  memo: "From the memo",
  rule: "From your rule",
  source: "From the bank's category",
  manual: "Set by you",
  paycheck: "Matched to expected pay",
};

export function Transactions({ meta, stateFile, scope, filters, onFiltersChange, version, onDataChanged }: Props) {
  const [sort, setSort] = useState<Sort>("-date");
  const [page, setPage] = useState(0);
  const [search, setSearch] = useState(filters.q ?? "");
  const [saving, setSaving] = useState<string>();
  const [saveError, setSaveError] = useState<string>();
  const [suggestion, setSuggestion] = useState<Suggestion>();
  const [savedNote, setSavedNote] = useState<string>();

  // Keep the box in sync when filters change from elsewhere (e.g. drilling in from the overview).
  useEffect(() => setSearch(filters.q ?? ""), [filters.q]);

  // Debounce the search box into the filters.
  useEffect(() => {
    const t = setTimeout(() => {
      if ((filters.q ?? "") !== search) onFiltersChange({ ...filters, q: search || undefined });
    }, 250);
    return () => clearTimeout(t);
  }, [search]); // eslint-disable-line react-hooks/exhaustive-deps

  const filterKey = JSON.stringify([filters, scope]);
  useEffect(() => setPage(0), [filterKey, sort]);

  // Scope (top bar) narrows payment method / account unless the page sets its own.
  const params = {
    ...filters,
    payment_method: filters.payment_method ?? scope.payment_method,
    account: filters.account ?? scope.account,
    account_type: scope.account_type,
    recurring: filters.recurring === undefined ? undefined : String(filters.recurring),
    excluded: filters.excluded === undefined ? undefined : String(filters.excluded),
    needs_review: filters.needs_review ? "true" : undefined,
    sort,
    limit: PAGE,
    offset: page * PAGE,
  };
  const result = useAsync(() => api.transactions(params), [filterKey, sort, page, version]);

  const set = <K extends keyof TxnFilters>(key: K, value: TxnFilters[K]) =>
    onFiltersChange({ ...filters, [key]: value });
  const single = (v: string) => (v ? [v] : undefined);

  async function changeCategory(t: Transaction, category: string) {
    setSaving(t.id);
    setSaveError(undefined);
    try {
      const reset = category === "__reset__";
      const r = await api.setCategory(t.id, reset ? null : category);
      setSavedNote(reset ? `Reset ${r.merchant} to automatic.` : `Saved: ${r.merchant} is now ${r.category}.`);
      setSuggestion(!reset && r.merchant_different_category > 0
        ? { txn: r, action: "category", count: r.merchant_different_category }
        : undefined);
      onDataChanged();
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(undefined);
    }
  }

  async function toggleExcluded(t: Transaction) {
    setSaving(t.id);
    setSaveError(undefined);
    try {
      // Adding back a rule-excluded row needs an explicit "keep"; otherwise just clear the manual choice.
      const next = t.excluded ? (t.excluded_source === "rule" ? false : null) : true;
      const r = await api.setExcluded(t.id, next);
      setSavedNote(`Saved: ${r.merchant} is ${r.excluded ? "excluded from" : "back in"} the budget.`);
      setSuggestion(r.excluded && r.merchant_different_excluded > 0
        ? { txn: r, action: "exclude", count: r.merchant_different_excluded }
        : undefined);
      onDataChanged();
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(undefined);
    }
  }

  async function applySuggestion(sg: Suggestion) {
    setSaveError(undefined);
    try {
      const rule = await api.addRule({
        pattern: sg.txn.merchant,
        match: "merchant",
        category: sg.txn.category,
        kind: null,
        exclude: sg.action === "exclude",
      });
      setSavedNote(
        `Saved as a rule: all ${rule.matched} ${sg.txn.merchant} transactions, and any new ones in future exports, ` +
          (sg.action === "exclude" ? "are excluded from the budget." : `are ${sg.txn.category}.`),
      );
      setSuggestion(undefined);
      onDataChanged();
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : String(e));
    }
  }

  const toggleSort = (key: "date" | "amount") => setSort(sort === `-${key}` ? key : (`-${key}` as Sort));
  const arrow = (key: string) => (sort === key ? " ↑" : sort === `-${key}` ? " ↓" : "");
  const active = Object.values(filters).some((v) => v !== undefined && !(Array.isArray(v) && !v.length));
  const data = result.data;

  return (
    <div>
      <div className="filters" role="search">
        <input
          className="input"
          type="search"
          placeholder="Search description, merchant, category…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{ flex: "1 1 240px" }}
          aria-label="Search transactions"
        />
        <select className="select" aria-label="Month" value={filters.month ?? ""} onChange={(e) => set("month", e.target.value || undefined)}>
          <option value="">All months</option>
          {[...meta.months].reverse().map((m) => <option key={m} value={m}>{monthLabel(m)}</option>)}
        </select>
        <select className="select" aria-label="Category" value={filters.category?.[0] ?? ""} onChange={(e) => set("category", single(e.target.value))}>
          <option value="">All categories</option>
          {meta.categories.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
        <select className="select" aria-label="Paid with" value={filters.payment_method?.[0] ?? ""} onChange={(e) => set("payment_method", single(e.target.value) as PaymentMethod[] | undefined)}>
          <option value="">Any payment method</option>
          {meta.payment_methods.map((p) => <option key={p} value={p}>{PAYMENT_METHOD_LABELS[p]}</option>)}
        </select>
        <select className="select" aria-label="Account" value={filters.account?.[0] ?? ""} onChange={(e) => set("account", single(e.target.value))}>
          <option value="">All accounts</option>
          {meta.accounts.map((a) => <option key={a} value={a}>{a}</option>)}
        </select>
        <select
          className="select"
          aria-label="Type"
          value={filters.needs_review ? "__review__" : filters.kind?.[0] ?? ""}
          onChange={(e) => {
            const v = e.target.value;
            onFiltersChange({ ...filters, needs_review: v === "__review__" || undefined,
                              kind: v && v !== "__review__" ? [v as Kind] : undefined });
          }}
        >
          <option value="">All types</option>
          {meta.kinds.map((k) => <option key={k} value={k}>{KIND_LABELS[k]}</option>)}
          <option value="__review__">Money in to review</option>
        </select>
        <select
          className="select"
          aria-label="Recurring"
          value={filters.recurring === undefined ? "" : String(filters.recurring)}
          onChange={(e) => set("recurring", e.target.value === "" ? undefined : e.target.value === "true")}
        >
          <option value="">Recurring + one-time</option>
          <option value="true">Recurring only</option>
          <option value="false">One-time only</option>
        </select>
        <select
          className="select"
          aria-label="Budget"
          value={filters.excluded === undefined ? "" : String(filters.excluded)}
          onChange={(e) => set("excluded", e.target.value === "" ? undefined : e.target.value === "true")}
        >
          <option value="">In budget + excluded</option>
          <option value="false">In budget only</option>
          <option value="true">Excluded only</option>
        </select>
        {active && (
          <button className="btn btn-ghost" onClick={() => { setSearch(""); onFiltersChange({}); }}>Clear filters</button>
        )}
      </div>

      {saveError && <ErrorNotice error={saveError} />}
      {(savedNote || suggestion) && (
        <div className="notice notice-info" role="status" style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
          <span style={{ flex: "1 1 320px" }}>
            {savedNote && <>✓ {savedNote} </>}
            {suggestion && (
              <>
                Do the same for the {suggestion.count} other <strong>{suggestion.txn.merchant}</strong>{" "}
                transaction{suggestion.count === 1 ? "" : "s"} and any future ones?
              </>
            )}
          </span>
          {suggestion && (
            <button className="btn btn-sm btn-primary" onClick={() => applySuggestion(suggestion)}>
              {suggestion.action === "exclude" ? "Exclude all" : `Make all ${suggestion.txn.category}`}
            </button>
          )}
          <button className="btn btn-sm btn-ghost" onClick={() => { setSuggestion(undefined); setSavedNote(undefined); }}>
            Dismiss
          </button>
        </div>
      )}
      {result.error && <ErrorNotice error={result.error} onRetry={result.reload} />}

      <section className="card">
        <div className="card-head">
          <div>
            <h2 className="card-title">{data ? `${data.total.toLocaleString()} transaction${data.total === 1 ? "" : "s"}` : "Transactions"}</h2>
            {data && (
              <p className="card-sub">
                Net spending in this list: {money(data.net_spending)}
                {data.excluded > 0 && ` · ${data.excluded} excluded from the budget`}
                <br />
                <span className="small muted" title={stateFile}>
                  Category changes and exclusions are saved automatically and kept the next time you open the app.
                </span>
              </p>
            )}
          </div>
          <a className="btn" href={api.exportUrl({ month: filters.month, account: params.account, payment_method: params.payment_method })}>
            Export CSV
          </a>
        </div>
        {!data ? <Loading /> : data.items.length === 0 ? (
          <div className="empty">No transactions match these filters.</div>
        ) : (
          <div className="table-wrap" style={{ opacity: result.loading ? 0.6 : 1 }}>
            <table>
              <thead>
                <tr>
                  <th className="sortable" onClick={() => toggleSort("date")} aria-sort={sort.endsWith("date") ? (sort === "date" ? "ascending" : "descending") : "none"}>Date{arrow("date")}</th>
                  <th>Description</th>
                  <th>Category</th>
                  <th>Paid with</th>
                  <th>Account</th>
                  <th className="num sortable" onClick={() => toggleSort("amount")} aria-sort={sort.endsWith("amount") ? (sort === "amount" ? "ascending" : "descending") : "none"}>Amount{arrow("amount")}</th>
                  <th><span className="sr-only">Budget</span></th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((t) => (
                  <tr key={t.id} className={t.excluded ? "excluded" : undefined}>
                    <td className="secondary" style={{ whiteSpace: "nowrap" }}>{dateLabel(t.date)}</td>
                    <td>
                      <div className="desc" title={t.description}>{t.merchant}</div>
                      <div className="small muted desc" title={t.description}>
                        {t.description}
                      </div>
                      {t.memo && (
                        <div className="small muted desc memo" title={t.memo}>Memo: {t.memo}</div>
                      )}
                      <div style={{ display: "flex", gap: 4, marginTop: 2, flexWrap: "wrap" }}>
                        {t.is_recurring && <span className="badge badge-accent">↻ Recurring</span>}
                        {t.kind !== "expense" && <span className="badge">{t.kind === "refund" && t.amount > 0 ? "Paid back" : KIND_LABELS[t.kind]}</span>}
                        {t.needs_review && <span className="badge badge-warn" title="Is this income, or someone paying you back? Pick Income or the category it offsets.">? Review</span>}
                        {t.category === "Uncategorized" && t.amount < 0 && !t.excluded && (
                          <span className="badge badge-warn" title="Neither the description nor the memo says what this was for. Pick a category.">? Categorize</span>
                        )}
                        {t.excluded && (
                          <span className="badge badge-warn">
                            ⊘ Excluded from budget{t.excluded_source === "rule" ? " by rule" : ""}
                          </span>
                        )}
                      </div>
                    </td>
                    <td>
                      <select
                        className="select"
                        value={t.category}
                        disabled={saving === t.id}
                        onChange={(e) => changeCategory(t, e.target.value)}
                        aria-label={`Category for ${t.merchant}`}
                        title={SOURCE_LABEL[t.category_source]}
                        style={{ maxWidth: 190 }}
                      >
                        {!meta.categories.includes(t.category) && <option value={t.category}>{t.category}</option>}
                        {meta.categories.map((c) => <option key={c} value={c}>{c}</option>)}
                        {t.category_source === "manual" && <option value="__reset__">↺ Reset to automatic</option>}
                      </select>
                      <div className="small muted">
                        {t.category === "Uncategorized" && t.category_source === "auto"
                          ? "Nothing to go on: pick one"
                          : SOURCE_LABEL[t.category_source]}
                      </div>
                    </td>
                    <td className="secondary">{PAYMENT_METHOD_LABELS[t.payment_method]}</td>
                    <td className="secondary small">{t.account}</td>
                    <td className={`num amount ${t.amount > 0 ? "amount-in" : ""}`}>
                      {t.amount > 0 ? "+" : ""}{money(t.amount)}
                    </td>
                    <td className="num">
                      <button
                        className="btn btn-sm"
                        disabled={saving === t.id}
                        onClick={() => toggleExcluded(t)}
                        title={t.excluded ? "Count this in totals again" : "Leave this out of every total, chart and savings figure"}
                        aria-label={`${t.excluded ? "Add back to budget" : "Remove from budget"}: ${t.merchant}`}
                      >
                        {t.excluded ? "Add back" : "Exclude"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {data && data.total > PAGE && (
          <div className="pager">
            <span>
              Showing {page * PAGE + 1}–{Math.min((page + 1) * PAGE, data.total)} of {data.total.toLocaleString()}
            </span>
            <span style={{ display: "flex", gap: 8 }}>
              <button className="btn btn-sm" disabled={page === 0} onClick={() => setPage(page - 1)}>Previous</button>
              <button className="btn btn-sm" disabled={(page + 1) * PAGE >= data.total} onClick={() => setPage(page + 1)}>Next</button>
            </span>
          </div>
        )}
      </section>
    </div>
  );
}
