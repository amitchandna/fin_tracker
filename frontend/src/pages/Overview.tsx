import { useCallback, useMemo, useState } from "react";
import { api } from "../api";
import { colorMap, MAX_SERIES, PAYMENT_METHOD_ORDER, usePalette } from "../colors";
import { Card, ErrorNotice, Loading, Segmented, StatTile, Swatch } from "../components/common";
import { MonthlyChart, type Series } from "../components/MonthlyChart";
import { change, money, moneyWhole, monthLabel, PAYMENT_METHOD_LABELS, percent } from "../format";
import type { MonthSummary, PaymentMethod, ScopeFilter } from "../types";
import { useAsync } from "../useAsync";
import type { TxnFilters } from "./Transactions";

type GroupBy = "category" | "payment_method" | "account" | "recurring";

interface Props {
  scope: ScopeFilter;
  categoryOrder: string[];
  accounts: string[];
  version: number;
  onDrill: (filters: TxnFilters) => void;
}

const OTHER = "__other__";

export function Overview({ scope, categoryOrder, accounts, version, onDrill }: Props) {
  const palette = usePalette();
  const [groupBy, setGroupBy] = useState<GroupBy>("category");
  const [pickedMonth, setPickedMonth] = useState<string>();
  const scopeKey = JSON.stringify(scope);

  const overview = useAsync(() => api.overview(scope), [scopeKey, version]);
  const monthly = useAsync(() => api.monthly(scope), [scopeKey, version]);
  // Income and savings only make sense across every account, so they ignore the account filter.
  const scoped = scopeKey !== "{}";
  const allOverview = useAsync(() => (scoped ? api.overview() : Promise.resolve(undefined)), [scoped, version]);
  const allMonthly = useAsync(() => (scoped ? api.monthly() : Promise.resolve(undefined)), [scoped, version]);
  const months = monthly.data ?? [];
  const selectedMonth =
    pickedMonth && months.some((m) => m.month === pickedMonth) ? pickedMonth : months.at(-1)?.month;
  const categories = useAsync(
    () => (selectedMonth ? api.categories(selectedMonth, scope) : Promise.resolve([])),
    [selectedMonth, scopeKey, version],
  );

  const categoryColor = useMemo(() => colorMap(categoryOrder, palette), [categoryOrder, palette]);
  const methodColor = useMemo(() => colorMap(PAYMENT_METHOD_ORDER, palette), [palette]);
  const accountColor = useMemo(() => colorMap(accounts, palette), [accounts, palette]);

  const { series, value } = useMemo((): { series: Series[]; value: (m: MonthSummary, key: string) => number } => {
    const present = (pick: (m: MonthSummary) => Record<string, number>) =>
      new Set(months.flatMap((m) => Object.keys(pick(m))));
    if (groupBy === "category") {
      const keys = present((m) => m.by_category);
      const top = categoryOrder.slice(0, MAX_SERIES).filter((c) => keys.has(c));
      const hasOther = [...keys].some((k) => !top.includes(k));
      const s: Series[] = top.map((c) => ({ key: c, label: c, color: categoryColor(c) }));
      if (hasOther) s.push({ key: OTHER, label: "Everything else", color: palette.other });
      return {
        series: s,
        value: (m, key) =>
          key === OTHER
            ? Object.entries(m.by_category).filter(([c]) => !top.includes(c)).reduce((a, [, v]) => a + v, 0)
            : m.by_category[key] ?? 0,
      };
    }
    if (groupBy === "payment_method") {
      const keys = present((m) => m.by_payment_method);
      return {
        series: PAYMENT_METHOD_ORDER.filter((k) => keys.has(k)).map((k) => ({
          key: k, label: PAYMENT_METHOD_LABELS[k as PaymentMethod], color: methodColor(k),
        })),
        value: (m, key) => m.by_payment_method[key] ?? 0,
      };
    }
    if (groupBy === "account") {
      const keys = present((m) => m.by_account);
      const top = accounts.slice(0, MAX_SERIES).filter((a) => keys.has(a));
      const s: Series[] = top.map((a) => ({ key: a, label: a, color: accountColor(a) }));
      if ([...keys].some((k) => !top.includes(k))) s.push({ key: OTHER, label: "Other accounts", color: palette.other });
      return {
        series: s,
        value: (m, key) =>
          key === OTHER
            ? Object.entries(m.by_account).filter(([a]) => !top.includes(a)).reduce((acc, [, v]) => acc + v, 0)
            : m.by_account[key] ?? 0,
      };
    }
    return {
      series: [
        { key: "recurring", label: "Recurring", color: palette.series[0] },
        { key: "one_time", label: "One-time", color: palette.series[1] },
      ],
      value: (m, key) => (key === "recurring" ? m.recurring : m.one_time),
    };
  }, [groupBy, months, categoryOrder, accounts, categoryColor, methodColor, accountColor, palette]);

  const onSelectMonth = useCallback((m: string) => setPickedMonth(m), []);

  if (overview.error) return <ErrorNotice error={overview.error} onRetry={overview.reload} />;
  if (!overview.data || !monthly.data || (scoped && (!allOverview.data || !allMonthly.data))) return <Loading />;
  const o = overview.data;
  const all = scoped ? allOverview.data! : o;
  if (o.months === 0) {
    return <div className="empty card"><h2>No spending in this view</h2>Try clearing the filters above.</div>;
  }

  const current = months.find((m) => m.month === selectedMonth);
  const prevIdx = months.findIndex((m) => m.month === selectedMonth) - 1;
  const previous = prevIdx >= 0 ? months[prevIdx] : undefined;
  const delta = current ? change(current.spending, previous?.spending) : null;
  const flow = (scoped ? allMonthly.data! : months).find((m) => m.month === selectedMonth);
  const allNote = scoped ? " · all accounts" : "";
  const maxCategory = Math.max(...(categories.data ?? []).map((c) => c.spending), 1);

  return (
    <div>
      {o.uncategorized > 0 && (
        <div className="notice notice-info">
          {o.uncategorized} expense{o.uncategorized === 1 ? " is" : "s are"} uncategorized.{" "}
          <a href="#/transactions" onClick={(e) => { e.preventDefault(); onDrill({ category: ["Uncategorized"] }); }}>
            Review them
          </a>{" "}
          to make the breakdown more accurate.
        </div>
      )}

      {(all.needs_review ?? 0) > 0 && (
        <div className="notice notice-warn">
          {all.needs_review} deposit{all.needs_review === 1 ? "" : "s"} ({money(all.needs_review_amount ?? 0)}) need
          {all.needs_review === 1 ? "s" : ""} a label: income, or someone paying you back?{" "}
          <a href="#/income">Review on Income &amp; Savings</a>
        </div>
      )}

      {o.excluded_count > 0 && (
        <div className="notice notice-info">
          {o.excluded_count} transaction{o.excluded_count === 1 ? "" : "s"} ({money(o.excluded_amount)}){" "}
          {o.excluded_count === 1 ? "is" : "are"} excluded from these totals.{" "}
          <a href="#/transactions" onClick={(e) => { e.preventDefault(); onDrill({ excluded: true }); }}>
            Review
          </a>
        </div>
      )}

      <div className="tiles">
        <StatTile
          label="Average monthly income"
          value={moneyWhole(all.average_monthly_income)}
          foot={flow ? `${monthLabel(flow.month)}: ${moneyWhole(flow.income)}${allNote}` : allNote.slice(3)}
        />
        <StatTile
          label="Average monthly spending"
          value={moneyWhole(o.average_monthly_spending)}
          foot={
            <>
              {current && `${monthLabel(current.month)}: ${moneyWhole(current.spending)} `}
              {delta !== null && (
                <span className={delta > 0 ? "delta-up" : "delta-down"}>
                  {delta > 0 ? "▲" : "▼"} {percent(Math.abs(delta))} vs {previous && monthLabel(previous.month, true)}
                </span>
              )}
            </>
          }
        />
        <StatTile
          label="Saved per month"
          value={moneyWhole(all.average_monthly_savings)}
          foot={
            all.savings_rate === null ? "No income found" : (
              <>
                {percent(all.savings_rate)} of income
                {flow && <> · {monthLabel(flow.month, true)}: <span className={flow.savings >= 0 ? "delta-down" : "delta-up"}>{moneyWhole(flow.savings)}</span></>}
                {allNote}
              </>
            )
          }
        />
        <StatTile
          label="Recurring payments"
          value={`${moneyWhole(o.recurring_monthly_cost)}/mo`}
          foot={`${o.active_recurring} active subscription${o.active_recurring === 1 ? "" : "s"} and bills`}
        />
      </div>

      <Card
        title="Monthly spending"
        sub="Net of refunds. Card payments and transfers between your accounts are excluded so nothing is counted twice."
        actions={
          <Segmented<GroupBy>
            label="Group spending by"
            value={groupBy}
            onChange={setGroupBy}
            options={[
              { value: "category", label: "Category" },
              { value: "payment_method", label: "Credit vs debit" },
              { value: "account", label: "Account" },
              { value: "recurring", label: "Recurring" },
            ]}
          />
        }
      >
        {monthly.error ? <ErrorNotice error={monthly.error} /> : (
          <MonthlyChart
            months={months}
            series={series}
            value={value}
            selectedMonth={selectedMonth}
            onSelectMonth={onSelectMonth}
          />
        )}
      </Card>

      {current && (
        <div className="grid-2">
          <Card
            title={`Where the money went in ${monthLabel(current.month)}`}
            sub={`${money(current.spending)} across ${categories.data?.length ?? 0} categories`}
            actions={
              <select
                className="select"
                aria-label="Month"
                value={selectedMonth}
                onChange={(e) => setPickedMonth(e.target.value)}
              >
                {[...months].reverse().map((m) => (
                  <option key={m.month} value={m.month}>{monthLabel(m.month)}</option>
                ))}
              </select>
            }
          >
            {categories.loading && !categories.data ? <Loading /> : (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Category</th>
                      <th className="bar-col" style={{ width: "30%" }}><span className="sr-only">Share</span></th>
                      <th className="num">Spent</th>
                      <th className="num">Share</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(categories.data ?? []).map((c) => (
                      <tr
                        key={c.category}
                        className="clickable"
                        onClick={() => onDrill({ month: current.month, category: [c.category] })}
                        title="Show these transactions"
                      >
                        <td>
                          <Swatch color={categoryColor(c.category)} />
                          {c.category}
                          {c.recurring > 0 && (
                            <span className="muted small"> · {moneyWhole(c.recurring)} recurring</span>
                          )}
                        </td>
                        <td className="bar-col">
                          <div className="share-bar">
                            <span style={{
                              width: `${Math.max(0, (c.spending / maxCategory) * 100)}%`,
                              background: categoryColor(c.category),
                            }} />
                          </div>
                        </td>
                        <td className="num">{money(c.spending)}</td>
                        <td className="num secondary">{percent(Math.max(0, c.share))}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>

          <div className="stack">
            <Card title="How you paid" sub={monthLabel(current.month)}>
              <BreakdownList
                rows={PAYMENT_METHOD_ORDER.filter((k) => current.by_payment_method[k]).map((k) => ({
                  key: k,
                  label: PAYMENT_METHOD_LABELS[k as PaymentMethod],
                  value: current.by_payment_method[k],
                  color: methodColor(k),
                  onClick: () => onDrill({ month: current.month, payment_method: [k as PaymentMethod] }),
                }))}
                total={current.spending}
              />
            </Card>
            <Card title="Recurring vs one-time" sub={monthLabel(current.month)}>
              <BreakdownList
                rows={[
                  { key: "r", label: "Recurring", value: current.recurring, color: palette.series[0],
                    onClick: () => onDrill({ month: current.month, recurring: true }) },
                  { key: "o", label: "One-time", value: current.one_time, color: palette.series[1],
                    onClick: () => onDrill({ month: current.month, recurring: false }) },
                ]}
                total={current.spending}
              />
            </Card>
            {flow && (
              <Card title="Income, spending & savings" sub={`${monthLabel(flow.month)}${allNote}`}>
                <dl className="kv">
                  <dt>Income</dt><dd>{money(flow.income)}</dd>
                  <dt>Spending</dt><dd>{money(flow.spending)}</dd>
                  <dt>{flow.savings >= 0 ? "Saved" : "Overspent"}</dt>
                  <dd className={flow.savings >= 0 ? "delta-down" : "delta-up"}>
                    <strong>{money(flow.savings)}</strong>
                    {flow.savings_rate !== null && <span className="secondary"> ({percent(flow.savings_rate)} of income)</span>}
                  </dd>
                  <dt>Total saved so far</dt><dd>{money(flow.cumulative_savings)}</dd>
                  <dt>Moved between accounts</dt><dd className="secondary">{money(flow.transfers)}</dd>
                </dl>
                <a href="#/income" className="small">See income & savings →</a>
              </Card>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function BreakdownList({ rows, total }: {
  rows: { key: string; label: string; value: number; color: string; onClick: () => void }[];
  total: number;
}) {
  if (!rows.length) return <div className="muted">Nothing this month.</div>;
  return (
    <table>
      <tbody>
        {rows.map((r) => (
          <tr key={r.key} className="clickable" onClick={r.onClick} title="Show these transactions">
            <td><Swatch color={r.color} />{r.label}</td>
            <td className="num">{money(r.value)}</td>
            <td className="num secondary" style={{ width: 56 }}>{total > 0 ? percent(Math.max(0, r.value / total)) : "–"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
