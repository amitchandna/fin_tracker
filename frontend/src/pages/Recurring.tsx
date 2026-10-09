import { useMemo, useState } from "react";
import { api } from "../api";
import { Card, ErrorNotice, Loading, Segmented, StatTile } from "../components/common";
import { dateLabel, FREQUENCY_LABELS, money, moneyWhole, PAYMENT_METHOD_LABELS } from "../format";
import type { RecurringSeries } from "../types";
import { useAsync } from "../useAsync";
import type { TxnFilters } from "./Transactions";

type Show = "active" | "all";

export function Recurring({ version, onDrill }: { version: number; onDrill: (f: TxnFilters) => void }) {
  const [show, setShow] = useState<Show>("active");
  const result = useAsync(() => api.recurring(), [version]);
  const all = result.data ?? [];
  const list = show === "active" ? all.filter((s) => s.active) : all;

  const totals = useMemo(() => {
    const active = all.filter((s) => s.active);
    const byMethod = (pred: (s: RecurringSeries) => boolean) =>
      active.filter(pred).reduce((a, s) => a + s.monthly_cost, 0);
    return {
      monthly: active.reduce((a, s) => a + s.monthly_cost, 0),
      credit: byMethod((s) => s.payment_methods.includes("credit")),
      bank: byMethod((s) => !s.payment_methods.includes("credit")),
      count: active.length,
    };
  }, [all]);

  if (result.error) return <ErrorNotice error={result.error} onRetry={result.reload} />;
  if (!result.data) return <Loading />;

  return (
    <div>
      <div className="tiles">
        <StatTile label="Recurring per month" value={moneyWhole(totals.monthly)} foot={`${totals.count} active`} />
        <StatTile label="Per year" value={moneyWhole(totals.monthly * 12)} foot="If nothing changes" />
        <StatTile label="Billed to credit cards" value={`${moneyWhole(totals.credit)}/mo`} foot="Subscriptions on cards" />
        <StatTile label="Paid from bank" value={`${moneyWhole(totals.bank)}/mo`} foot="Debit, ACH and checks" />
      </div>

      <Card
        title="Recurring payments"
        sub="Detected from regular charges at the same merchant with consistent amounts."
        actions={
          <Segmented<Show>
            label="Which recurring payments to show"
            value={show}
            onChange={setShow}
            options={[
              { value: "active", label: "Active" },
              { value: "all", label: `All (${all.length})` },
            ]}
          />
        }
      >
        {list.length === 0 ? (
          <div className="empty">No recurring payments detected yet. They appear once a charge repeats at least three times.</div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Merchant</th>
                  <th>How often</th>
                  <th className="num">Amount</th>
                  <th className="num">Per month</th>
                  <th>Paid with</th>
                  <th>Last charged</th>
                  <th>Next expected</th>
                </tr>
              </thead>
              <tbody>
                {list.map((s) => (
                  <tr key={s.id} className="clickable" onClick={() => onDrill({ q: s.merchant, recurring: true })}
                      title="Show these charges">
                    <td>
                      <div><strong>{s.merchant}</strong></div>
                      <div className="small muted">
                        {s.category} · {s.occurrences} charges
                        {!s.active && <> · <span className="badge badge-warn">Stopped?</span></>}
                      </div>
                    </td>
                    <td>{FREQUENCY_LABELS[s.frequency]}</td>
                    <td className="num">
                      {money(s.average_amount)}
                      {!s.fixed_amount && <div className="small muted">varies</div>}
                    </td>
                    <td className="num"><strong>{money(s.monthly_cost)}</strong></td>
                    <td className="secondary">
                      {s.payment_methods.map((p) => PAYMENT_METHOD_LABELS[p]).join(", ")}
                      <div className="small muted">{s.accounts.join(", ")}</div>
                    </td>
                    <td className="secondary">{dateLabel(s.last_date)}</td>
                    <td className="secondary">{s.active ? dateLabel(s.next_expected) : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
