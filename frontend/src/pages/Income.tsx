import { useMemo, useState, type ReactNode } from "react";
import {
  Bar, BarChart, CartesianGrid, Cell, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import type { TooltipContentProps } from "recharts";
import type { NameType, ValueType } from "recharts/types/component/DefaultTooltipContent";
import { api } from "../api";
import { usePalette } from "../colors";
import { Card, ErrorNotice, Loading, StatTile, Swatch } from "../components/common";
import { MoneyInReview } from "../components/MoneyInReview";
import { PaySchedules } from "../components/PaySchedules";
import { dateLabel, money, moneyCompact, moneyWhole, monthLabel, percent } from "../format";
import type { Meta, MonthSummary } from "../types";
import { useAsync } from "../useAsync";
import type { TxnFilters } from "./Transactions";

const axisTick = { fill: "var(--text-muted)", fontSize: 12 };

function rate(r: number | null | undefined): string {
  return r === null || r === undefined ? "—" : percent(r);
}

function ChartTooltip({ title, rows }: { title: string; rows: { label: string; value: ReactNode; color?: string }[] }) {
  return (
    <div className="tooltip">
      <div className="tooltip-title">{title}</div>
      {rows.map((r) => (
        <div className="tooltip-row" key={r.label}>
          <span>{r.color && <Swatch color={r.color} />}{r.label}</span>
          <span>{r.value}</span>
        </div>
      ))}
    </div>
  );
}

export function Income({ meta, version, onDrill, onDataChanged }: {
  meta: Meta;
  version: number;
  onDrill: (f: TxnFilters) => void;
  onDataChanged: () => void;
}) {
  const palette = usePalette();
  const [sourceMonth, setSourceMonth] = useState("");
  const overview = useAsync(() => api.overview(), [version]);
  const monthly = useAsync(() => api.monthly(), [version]);
  const sources = useAsync(() => api.income(sourceMonth || undefined), [sourceMonth, version]);

  const months = monthly.data ?? [];
  const colors = useMemo(() => ({
    income: palette.series[0],
    spending: palette.series[1],
    saved: palette.series[0],
    overspent: palette.series[7],
  }), [palette]);

  if (overview.error) return <ErrorNotice error={overview.error} onRetry={overview.reload} />;
  if (monthly.error) return <ErrorNotice error={monthly.error} onRetry={monthly.reload} />;
  if (!overview.data || !monthly.data) return <Loading />;
  const o = overview.data;
  const best = months.reduce<MonthSummary | undefined>((b, m) => (!b || m.savings > b.savings ? m : b), undefined);
  const last = months.at(-1);

  const setup = (
    <div className="stack" style={{ marginBottom: 16 }}>
      <MoneyInReview categories={meta.categories} version={version} onDataChanged={onDataChanged} />
      <PaySchedules accounts={meta.accounts} version={version} onDataChanged={onDataChanged} />
    </div>
  );
  const hasExpected = months.some((m) => m.expected_income != null);

  if (o.total_income <= 0) {
    return (
      <>
      {setup}
      <div className="card empty">
        <h2>No income found yet</h2>
        <p>
          Income comes from deposits into checking or savings accounts, like paychecks, interest and tax refunds.
          Add a CSV export from the account your pay goes into, then press Rescan.
        </p>
        <p className="small">
          If a deposit is being treated as something else, change its category to <strong>Income</strong> on
          the Transactions tab, or add a rule.
        </p>
      </div>
      </>
    );
  }

  const incomeTooltip = ({ active, payload, label }: TooltipContentProps<ValueType, NameType>) => {
    if (!active || !payload?.length) return null;
    const m = months.find((x) => x.month === label);
    if (!m) return null;
    return (
      <ChartTooltip
        title={monthLabel(m.month)}
        rows={[
          { label: "Income", value: money(m.income), color: colors.income },
          ...(m.expected_income != null ? [{ label: "Expected income", value: money(m.expected_income) }] : []),
          { label: "Spending", value: money(m.spending), color: colors.spending },
          { label: m.savings >= 0 ? "Saved" : "Overspent", value: <strong>{money(m.savings)}</strong> },
          { label: "Savings rate", value: rate(m.savings_rate) },
        ]}
      />
    );
  };

  const cumulativeTooltip = ({ active, payload, label }: TooltipContentProps<ValueType, NameType>) => {
    if (!active || !payload?.length) return null;
    const m = months.find((x) => x.month === label);
    if (!m) return null;
    return (
      <ChartTooltip
        title={`Through ${monthLabel(m.month)}`}
        rows={[
          { label: "Total saved", value: <strong>{money(m.cumulative_savings)}</strong> },
          { label: "This month", value: money(m.savings) },
        ]}
      />
    );
  };

  return (
    <div>
      {setup}
      <div className="tiles">
        <StatTile
          label="Average monthly income"
          value={moneyWhole(o.average_monthly_income)}
          foot={last ? (
            <>
              {monthLabel(last.month)}: {moneyWhole(last.income)}
              {last.expected_income != null && <> of {moneyWhole(last.expected_income)} expected</>}
            </>
          ) : undefined}
        />
        <StatTile
          label="Average saved per month"
          value={moneyWhole(o.average_monthly_savings)}
          foot={`Income minus spending, across ${o.average_basis_months ?? o.months} months`}
        />
        <StatTile
          label="Savings rate"
          value={rate(o.savings_rate)}
          foot={`Of income kept · saved in ${o.months_saved} of ${o.months} months`}
        />
        <StatTile
          label="Total saved"
          value={moneyWhole(o.total_savings)}
          foot={o.first_month ? `Since ${monthLabel(o.first_month)}` : undefined}
        />
      </div>

      {o.months_overspent > 0 && (
        <div className="notice notice-warn">
          ⚠ You spent more than you earned in {o.months_overspent} month{o.months_overspent === 1 ? "" : "s"}.
        </div>
      )}

      <Card
        title="Income vs spending"
        sub="Whatever comes in and isn't spent is counted as saved. Transfers to your savings or investment accounts aren't spending, so they count as saved."
      >
        <ul className="legend" aria-label="Legend">
          <li><Swatch color={colors.income} />Income</li>
          <li><Swatch color={colors.spending} />Spending</li>
        </ul>
        <div style={{ width: "100%", height: 300 }}>
          <ResponsiveContainer>
            <BarChart data={months} margin={{ top: 8, right: 8, left: 4, bottom: 0 }} barGap={2}>
              <CartesianGrid vertical={false} stroke="var(--grid)" />
              <XAxis dataKey="month" tickFormatter={(m: string) => monthLabel(m, months.length > 8)} tickLine={false}
                     axisLine={{ stroke: "var(--axis)" }} tick={axisTick} />
              <YAxis tickFormatter={moneyCompact} tickLine={false} axisLine={false} width={64} tick={axisTick} />
              <Tooltip content={incomeTooltip} cursor={{ fill: "var(--accent-wash)" }} />
              <Bar dataKey="income" name="Income" fill={colors.income} radius={[4, 4, 0, 0]} maxBarSize={36}
                   isAnimationActive={false} />
              <Bar dataKey="spending" name="Spending" fill={colors.spending} radius={[4, 4, 0, 0]} maxBarSize={36}
                   isAnimationActive={false} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>

      <div className="grid-2 grid-even">
        <Card title="Saved each month" sub="Income minus spending">
          <ul className="legend" aria-label="Legend">
            <li><Swatch color={colors.saved} />Saved</li>
            {months.some((m) => m.savings < 0) && <li><Swatch color={colors.overspent} />Overspent</li>}
          </ul>
          <div style={{ width: "100%", height: 220 }}>
            <ResponsiveContainer>
              <BarChart data={months} margin={{ top: 8, right: 8, left: 4, bottom: 0 }}>
                <CartesianGrid vertical={false} stroke="var(--grid)" />
                <XAxis dataKey="month" tickFormatter={(m: string) => monthLabel(m, true)} tickLine={false}
                       axisLine={false} tick={axisTick} />
                <YAxis tickFormatter={moneyCompact} tickLine={false} axisLine={false} width={64} tick={axisTick} />
                <ReferenceLine y={0} stroke="var(--axis)" />
                <Tooltip content={incomeTooltip} cursor={{ fill: "var(--accent-wash)" }} />
                <Bar dataKey="savings" maxBarSize={40} isAnimationActive={false}>
                  {months.map((m) => (
                    <Cell key={m.month} fill={m.savings >= 0 ? colors.saved : colors.overspent} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
        <Card title="Total saved over time" sub={best ? `Best month: ${monthLabel(best.month)} (${moneyWhole(best.savings)})` : undefined}>
          <div style={{ width: "100%", height: 248 }}>
            <ResponsiveContainer>
              <LineChart data={months} margin={{ top: 8, right: 12, left: 4, bottom: 0 }}>
                <CartesianGrid vertical={false} stroke="var(--grid)" />
                <XAxis dataKey="month" tickFormatter={(m: string) => monthLabel(m, true)} tickLine={false}
                       axisLine={{ stroke: "var(--axis)" }} tick={axisTick} />
                <YAxis tickFormatter={moneyCompact} tickLine={false} axisLine={false} width={64} tick={axisTick} />
                <Tooltip content={cumulativeTooltip} cursor={{ stroke: "var(--axis)" }} />
                <Line type="monotone" dataKey="cumulative_savings" stroke={colors.saved} strokeWidth={2}
                      dot={{ r: 4, fill: colors.saved, stroke: "var(--surface-1)", strokeWidth: 2 }}
                      activeDot={{ r: 5 }} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </div>

      <div className="grid-2">
        <Card title="Month by month" sub="Click a month to see where its income came from">
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Month</th>
                  {hasExpected && <th className="num">Expected</th>}
                  <th className="num">Income</th>
                  <th className="num">Spending</th>
                  <th className="num">Saved</th>
                  <th className="num">Rate</th>
                  <th className="num">Total saved</th>
                </tr>
              </thead>
              <tbody>
                {[...months].reverse().map((m) => (
                  <tr key={m.month} className="clickable" onClick={() => setSourceMonth(m.month)}
                      aria-selected={sourceMonth === m.month}
                      style={sourceMonth === m.month ? { background: "var(--accent-wash)" } : undefined}>
                    <td>{monthLabel(m.month)}</td>
                    {hasExpected && (
                      <td className="num secondary">{m.expected_income != null ? money(m.expected_income) : "—"}</td>
                    )}
                    <td className="num">
                      {money(m.income)}
                      {m.expected_income != null && m.income < m.expected_income - 0.5 && (
                        <div className="small delta-up">{money(m.income - m.expected_income)}</div>
                      )}
                    </td>
                    <td className="num">{money(m.spending)}</td>
                    <td className={`num ${m.savings >= 0 ? "delta-down" : "delta-up"}`}>
                      <strong>{money(m.savings)}</strong>
                    </td>
                    <td className="num secondary">{rate(m.savings_rate)}</td>
                    <td className="num secondary">{money(m.cumulative_savings)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>

        <Card
          title="Where income comes from"
          sub={sourceMonth ? monthLabel(sourceMonth) : `All months · ${money(o.total_income)} total`}
          actions={
            <select className="select" aria-label="Month" value={sourceMonth}
                    onChange={(e) => setSourceMonth(e.target.value)}>
              <option value="">All months</option>
              {[...months].reverse().map((m) => <option key={m.month} value={m.month}>{monthLabel(m.month)}</option>)}
            </select>
          }
        >
          {sources.error ? <ErrorNotice error={sources.error} onRetry={sources.reload} /> : !sources.data ? <Loading /> :
            sources.data.length === 0 ? <div className="muted">No income this month.</div> : (
              <table>
                <tbody>
                  {sources.data.map((s) => (
                    <tr key={s.source} className="clickable" title="Show these deposits"
                        onClick={() => onDrill({ kind: ["income"], q: s.source, month: sourceMonth || undefined })}>
                      <td>
                        <div>{s.source}</div>
                        <div className="small muted">
                          {s.transactions} deposit{s.transactions === 1 ? "" : "s"} · {s.accounts.join(", ")} · last{" "}
                          {dateLabel(s.last_date)}
                        </div>
                      </td>
                      <td className="num">{money(s.amount)}</td>
                      <td className="num secondary" style={{ width: 56 }}>{percent(s.share)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
        </Card>
      </div>
    </div>
  );
}
