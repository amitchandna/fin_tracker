import { useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { TooltipContentProps } from "recharts";
import type { NameType, ValueType } from "recharts/types/component/DefaultTooltipContent";
import { money, moneyCompact, monthLabel } from "../format";
import type { MonthSummary } from "../types";
import { Swatch } from "./common";

export interface Series {
  key: string;
  label: string;
  color: string;
}

interface Props {
  months: MonthSummary[];
  series: Series[];
  value: (m: MonthSummary, key: string) => number;
  selectedMonth?: string;
  onSelectMonth: (month: string) => void;
}

type Row = { month: string; total: number } & Record<string, number | string>;

export function MonthlyChart({ months, series, value, selectedMonth, onSelectMonth }: Props) {
  const [showTable, setShowTable] = useState(false);

  const rows: Row[] = useMemo(
    () =>
      months.map((m) => {
        const row: Row = { month: m.month, total: 0 };
        for (const s of series) {
          const v = Math.max(0, value(m, s.key));
          row[s.key] = v;
          row.total += v;
        }
        return row;
      }),
    [months, series, value],
  );

  const labelFor = (key: string) => series.find((s) => s.key === key);

  const renderTooltip = ({ active, payload, label }: TooltipContentProps<ValueType, NameType>) => {
    if (!active || !payload?.length) return null;
    const items = payload
      .filter((p) => typeof p.value === "number" && p.value > 0.005)
      .sort((a, b) => Number(b.value) - Number(a.value));
    const total = items.reduce((acc, p) => acc + (p.value as number), 0);
    return (
      <div className="tooltip">
        <div className="tooltip-title">{monthLabel(String(label))}</div>
        {items.map((p) => {
          const s = labelFor(String(p.dataKey));
          return (
            <div className="tooltip-row" key={String(p.dataKey)}>
              <span>
                <Swatch color={s?.color ?? "gray"} />
                {s?.label}
              </span>
              <span>{money(p.value as number)}</span>
            </div>
          );
        })}
        <div className="tooltip-row tooltip-total">
          <span>Total</span>
          <span>{money(total)}</span>
        </div>
        <div className="muted small" style={{ marginTop: 6 }}>Click to see this month</div>
      </div>
    );
  };

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "flex-start" }}>
        <ul className="legend" aria-label="Legend">
          {series.map((s) => (
            <li key={s.key}>
              <Swatch color={s.color} />
              {s.label}
            </li>
          ))}
        </ul>
        <button className="btn btn-sm btn-ghost" onClick={() => setShowTable((v) => !v)} aria-pressed={showTable}>
          {showTable ? "Show chart" : "Show table"}
        </button>
      </div>

      {showTable ? (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Month</th>
                {series.map((s) => (
                  <th key={s.key} className="num">{s.label}</th>
                ))}
                <th className="num">Total</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.month} className="clickable" onClick={() => onSelectMonth(r.month)}>
                  <td>{monthLabel(r.month)}</td>
                  {series.map((s) => (
                    <td key={s.key} className="num">{money(r[s.key] as number)}</td>
                  ))}
                  <td className="num"><strong>{money(r.total)}</strong></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div style={{ width: "100%", height: 320 }}>
          <ResponsiveContainer>
            <BarChart
              data={rows}
              margin={{ top: 8, right: 8, left: 4, bottom: 0 }}
              onClick={(state) => {
                const idx = state?.activeTooltipIndex;
                if (idx !== undefined && idx !== null && rows[Number(idx)]) onSelectMonth(rows[Number(idx)].month);
              }}
              style={{ cursor: "pointer" }}
            >
              <CartesianGrid vertical={false} stroke="var(--grid)" />
              <XAxis
                dataKey="month"
                tickFormatter={(m: string) => monthLabel(m, rows.length > 8)}
                tickLine={false}
                axisLine={{ stroke: "var(--axis)" }}
                tick={{ fill: "var(--text-muted)", fontSize: 12 }}
              />
              <YAxis
                tickFormatter={moneyCompact}
                tickLine={false}
                axisLine={false}
                width={64}
                tick={{ fill: "var(--text-muted)", fontSize: 12 }}
              />
              <Tooltip content={renderTooltip} cursor={{ fill: "var(--accent-wash)" }} />
              {series.map((s, i) => (
                <Bar
                  key={s.key}
                  dataKey={s.key}
                  stackId="spend"
                  fill={s.color}
                  stroke="var(--surface-1)"
                  strokeWidth={1}
                  maxBarSize={56}
                  radius={i === series.length - 1 ? [4, 4, 0, 0] : 0}
                  isAnimationActive={false}
                >
                  {rows.map((r) => (
                    <Cell key={r.month} fillOpacity={!selectedMonth || selectedMonth === r.month ? 1 : 0.4} />
                  ))}
                </Bar>
              ))}
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
