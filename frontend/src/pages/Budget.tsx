import { useState } from "react";
import { api } from "../api";
import { BudgetEditor } from "../components/BudgetEditor";
import { Card, ErrorNotice, Loading, StatTile } from "../components/common";
import { dateLabel, money, moneyWhole, monthLabel, percent } from "../format";
import type { BudgetRow, BudgetStatus, Meta } from "../types";
import { useAsync } from "../useAsync";
import type { TxnFilters } from "./Transactions";

// Status always pairs colour with an icon and a word, never colour alone.
export const STATUS: Record<BudgetStatus, { label: string; icon: string; cls: string }> = {
  on_track: { label: "On track", icon: "✓", cls: "status-good" },
  at_risk: { label: "At risk", icon: "!", cls: "status-warn" },
  over: { label: "Over", icon: "▲", cls: "status-bad" },
};

function StatusChip({ status }: { status: BudgetStatus }) {
  const s = STATUS[status];
  return <span className={`status-chip ${s.cls}`}><span aria-hidden>{s.icon}</span> {s.label}</span>;
}

function BudgetBar({ row, inProgress }: { row: BudgetRow; inProgress: boolean }) {
  const used = row.budget > 0 ? row.spent / row.budget : 0;
  // When over, the bar is scaled so the budget mark sits inside it and the overshoot shows.
  const scale = Math.max(1, used);
  const fill = Math.min(used / scale, 1) * 100;
  const budgetMark = (1 / scale) * 100;
  const paceMark = inProgress ? (row.pace / row.budget / scale) * 100 : null;
  return (
    <div className="budget-bar" role="img"
         aria-label={`${money(row.spent)} of ${money(row.budget)} spent (${percent(used)})`}>
      <span className={`budget-fill ${STATUS[row.status].cls}`} style={{ width: `${fill}%` }} />
      {used > 1 && <span className="budget-mark" style={{ left: `${budgetMark}%` }} title="Budget" />}
      {paceMark !== null && paceMark > 0 && paceMark < 100 && (
        <span className="pace-mark" style={{ left: `${paceMark}%` }} title={`Even pace so far: ${money(row.pace)}`} />
      )}
    </div>
  );
}

export function Budget({ meta, version, onDrill, onDataChanged }: {
  meta: Meta;
  version: number;
  onDrill: (f: TxnFilters) => void;
  onDataChanged: () => void;
}) {
  const [month, setMonth] = useState<string>();
  const [editing, setEditing] = useState(false);
  const budgets = useAsync(() => api.budgets(), [version]);
  const suggestions = useAsync(() => api.budgetSuggestions(), [version]);
  const progress = useAsync(() => api.budgetProgress(month), [month, version]);
  const history = useAsync(() => api.budgetHistory(6), [version]);
  const overview = useAsync(() => api.overview(), [version]);

  const err = budgets.error || progress.error || suggestions.error;
  if (err) return <ErrorNotice error={err} onRetry={() => { budgets.reload(); progress.reload(); }} />;
  if (!budgets.data || !progress.data || !suggestions.data) return <Loading />;

  const saved = () => { setEditing(false); onDataChanged(); };
  const editor = (
    <BudgetEditor
      categories={meta.categories}
      current={budgets.data.budgets}
      suggestions={suggestions.data}
      averageIncome={overview.data?.average_monthly_income ?? 0}
      onSaved={saved}
      onCancel={budgets.data.budgets.length ? () => setEditing(false) : undefined}
    />
  );

  if (!budgets.data.budgets.length && !editing) {
    return (
      <div className="card empty">
        <h2>Set a monthly budget</h2>
        <p>Choose how much you want to spend in each category per month, then track how each month is going.</p>
        <p className="small">Amounts start from what you usually spend, so it only takes a minute.</p>
        <button className="btn btn-primary" onClick={() => setEditing(true)}>Create my budget</button>
      </div>
    );
  }
  if (editing) {
    return <Card title="Your monthly budget" sub="How much you want to spend in each category per month.">{editor}</Card>;
  }

  const p = progress.data;
  const t = p.totals;
  const months = [...meta.months].reverse();
  const shownMonths = (history.data ?? []).map((h) => h.month);
  const budgetMap = Object.fromEntries(budgets.data.budgets.map((b) => [b.category, b.amount]));

  return (
    <div>
      <div className="filters" style={{ justifyContent: "space-between" }}>
        <label>
          Month
          <select className="select" value={p.month} onChange={(e) => setMonth(e.target.value)}>
            {months.map((m) => <option key={m} value={m}>{monthLabel(m)}</option>)}
          </select>
        </label>
        <button className="btn" onClick={() => setEditing(true)}>Edit budget</button>
      </div>

      {p.in_progress && p.data_through && (
        <div className="notice notice-info">
          {monthLabel(p.month)} is {percent(p.elapsed)} done. Your files go up to {dateLabel(p.data_through)}.
          The marker on each bar shows where an even pace would be by now.
        </div>
      )}

      <div className="tiles">
        <StatTile label="Monthly budget" value={moneyWhole(t.budget)}
                  foot={`${p.categories.length} categor${p.categories.length === 1 ? "y" : "ies"}`} />
        <StatTile label={`Spent in ${monthLabel(p.month, true)}`} value={moneyWhole(t.spent)}
                  foot={t.budget > 0 ? `${percent(t.spent / t.budget)} of budget` : undefined} />
        <StatTile
          label={t.remaining >= 0 ? "Left to spend" : "Over budget by"}
          value={moneyWhole(Math.abs(t.remaining))}
          foot={
            t.over > 0 || t.at_risk > 0 ? (
              <>
                {t.over > 0 && (
                  <span className="status-chip status-bad">
                    ▲ {t.over} categor{t.over === 1 ? "y" : "ies"} over
                  </span>
                )}
                {t.over > 0 && t.at_risk > 0 && " · "}
                {t.at_risk > 0 && <span className="status-chip status-warn">! {t.at_risk} at risk</span>}
              </>
            ) : t.status ? <StatusChip status={t.status} /> : undefined
          }
        />
        {p.in_progress ? (
          <StatTile label="Projected for the month" value={moneyWhole(t.projected)}
                    foot={t.projected > t.budget ? `${moneyWhole(t.projected - t.budget)} over at this pace` : "Within budget at this pace"} />
        ) : (
          <StatTile label="Spent outside your budget" value={moneyWhole(t.unbudgeted)}
                    foot={`${p.unbudgeted.length} categor${p.unbudgeted.length === 1 ? "y has" : "ies have"} no budget`} />
        )}
      </div>

      <div className="grid-2">
        <Card title={`Budget progress, ${monthLabel(p.month)}`} sub="Click a category to see its transactions.">
          <div className="budget-list">
            {p.categories.map((r) => (
              <button key={r.category} type="button" className="budget-row"
                      onClick={() => onDrill({ month: p.month, category: [r.category] })}>
                <div className="budget-row-head">
                  <strong>{r.category}</strong>
                  <StatusChip status={r.status} />
                </div>
                <BudgetBar row={r} inProgress={p.in_progress} />
                <div className="budget-row-foot">
                  <span>{money(r.spent)} <span className="muted">of {money(r.budget)}</span></span>
                  <span className={r.remaining < 0 ? "delta-up" : "secondary"}>
                    {r.remaining >= 0 ? `${money(r.remaining)} left` : `${money(-r.remaining)} over`}
                    {p.in_progress && r.status !== "over" && r.projected > r.budget &&
                      ` · on pace for ${moneyWhole(r.projected)}`}
                  </span>
                </div>
              </button>
            ))}
          </div>
        </Card>

        <Card title="Not in your budget" sub={`${monthLabel(p.month)} spending in categories without a budget`}
              actions={p.unbudgeted.length > 0 && <button className="btn btn-sm" onClick={() => setEditing(true)}>Add budgets</button>}>
          {p.unbudgeted.length === 0 ? (
            <div className="muted">Everything you spent this month is covered by your budget.</div>
          ) : (
            <table>
              <tbody>
                {p.unbudgeted.map((u) => (
                  <tr key={u.category} className="clickable" onClick={() => onDrill({ month: p.month, category: [u.category] })}>
                    <td>{u.category}</td>
                    <td className="num">{money(u.spent)}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr><td><strong>Total</strong></td><td className="num"><strong>{money(t.unbudgeted)}</strong></td></tr>
              </tfoot>
            </table>
          )}
        </Card>
      </div>

      {history.data && history.data.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <Card title="Month by month" sub="Spending in each budgeted category. ▲ marks a month over budget.">
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Category</th>
                    <th className="num">Budget</th>
                    {shownMonths.map((m) => <th key={m} className="num">{monthLabel(m, true)}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {budgets.data.budgets.map((b) => (
                    <tr key={b.category}>
                      <td>{b.category}</td>
                      <td className="num secondary">{moneyWhole(b.amount)}</td>
                      {history.data!.map((h) => {
                        const v = h.spent[b.category] ?? 0;
                        const over = v > budgetMap[b.category] + 0.005;
                        return (
                          <td key={h.month} className={`num ${over ? "delta-up" : ""}`}
                              title={over ? `${money(v - budgetMap[b.category])} over budget` : "Within budget"}>
                            {over && <span aria-label="over budget">▲ </span>}{moneyWhole(v)}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr>
                    <td><strong>Total</strong></td>
                    <td className="num"><strong>{moneyWhole(t.budget)}</strong></td>
                    {history.data.map((h) => (
                      <td key={h.month} className={`num ${h.total_spent > h.total_budget + 0.005 ? "delta-up" : ""}`}>
                        <strong>{h.total_spent > h.total_budget + 0.005 && "▲ "}{moneyWhole(h.total_spent)}</strong>
                      </td>
                    ))}
                  </tr>
                </tfoot>
              </table>
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}
