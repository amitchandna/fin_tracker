import { useState, type FormEvent } from "react";
import { api } from "../api";
import { dateLabel, money, monthLabel } from "../format";
import type { ExpectedPay, PayFrequency, PaySchedule, PayScheduleInput } from "../types";
import { useAsync } from "../useAsync";
import { Card, ErrorNotice, Loading } from "./common";

const FREQ_LABELS: Record<PayFrequency, string> = {
  weekly: "Every week",
  biweekly: "Every 2 weeks",
  semimonthly: "Twice a month",
  monthly: "Once a month",
};

const STATUS: Record<ExpectedPay["status"], { label: string; cls: string }> = {
  received: { label: "✓ Received", cls: "badge-accent" },
  due: { label: "… Due", cls: "badge" },
  missed: { label: "⚠ Not found", cls: "badge-warn" },
  upcoming: { label: "Upcoming", cls: "badge" },
};

const dayLabel = (d: number) => (d >= 31 ? "Last day" : `${d}${["th", "st", "nd", "rd"][d % 10 > 3 || Math.floor(d / 10) === 1 ? 0 : d % 10]}`);
const DAY_OPTIONS = [...Array.from({ length: 28 }, (_, i) => i + 1), 31];

function describe(s: PaySchedule): string {
  if (s.frequency === "weekly" || s.frequency === "biweekly") {
    const wd = new Date(`${s.anchor_date}T00:00:00`).toLocaleDateString("en-US", { weekday: "long" });
    return `${FREQ_LABELS[s.frequency]} on ${wd}`;
  }
  const days = s.days.map((d) => (d >= 31 ? "last day" : dayLabel(d)));
  return `${FREQ_LABELS[s.frequency]} on the ${days.join(" and the ").replace("the the", "the")}`;
}

function currentMonth(offset = 0): string {
  const d = new Date();
  const m = new Date(d.getFullYear(), d.getMonth() + offset, 1);
  return `${m.getFullYear()}-${String(m.getMonth() + 1).padStart(2, "0")}`;
}

const EMPTY: PayScheduleInput = {
  name: "", amount: 0, frequency: "semimonthly", anchor_date: null, days: [15, 31], weekend: "before",
  account: null, match_text: null, tolerance: 0.1, start_date: null, end_date: null,
};

export function PaySchedules({ accounts, version, onDataChanged }: {
  accounts: string[];
  version: number;
  onDataChanged: () => void;
}) {
  const schedules = useAsync(() => api.paySchedules(), [version]);
  const expected = useAsync(() => api.expectedIncome(), [version]);
  const [editing, setEditing] = useState<{ id?: string; form: PayScheduleInput }>();
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);

  async function save(e: FormEvent) {
    e.preventDefault();
    if (!editing) return;
    setBusy(true);
    setError(undefined);
    try {
      await api.savePaySchedule(editing.form, editing.id);
      setEditing(undefined);
      onDataChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: string) {
    try {
      await api.deletePaySchedule(id);
      onDataChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  if (schedules.error) return <ErrorNotice error={schedules.error} onRetry={schedules.reload} />;
  if (!schedules.data) return <Loading />;
  const list = schedules.data;
  const thisMonth = currentMonth();
  const shownMonths = [thisMonth, currentMonth(1)];
  const upcoming = (expected.data ?? []).filter((e) => shownMonths.includes(e.month));
  const f = editing?.form;
  const set = (patch: Partial<PayScheduleInput>) => editing && setEditing({ ...editing, form: { ...editing.form, ...patch } });

  return (
    <Card
      title="Expected income"
      sub="Tell the app when you get paid and how much lands in your account. Deposits that match are confirmed as income automatically, and you can see whether each paycheck arrived."
      actions={!editing && (
        <button className="btn btn-primary btn-sm" onClick={() => setEditing({ form: { ...EMPTY } })}>+ Add paycheck</button>
      )}
    >
      {error && <ErrorNotice error={error} />}

      {editing && f && (
        <form className="card" style={{ background: "var(--surface-2)", marginBottom: 16 }} onSubmit={save}>
          <div className="form-row">
            <label className="field" style={{ flex: "2 1 200px" }}>
              Name
              <input className="input" required value={f.name} placeholder="e.g. Acme paycheck"
                     onChange={(e) => set({ name: e.target.value })} />
            </label>
            <label className="field" style={{ flex: "1 1 140px" }}>
              Amount that hits your account
              <input className="input" required type="number" min="0.01" step="0.01" inputMode="decimal"
                     value={f.amount || ""} placeholder="3850.00"
                     onChange={(e) => set({ amount: Number(e.target.value) })} />
            </label>
            <label className="field">
              How often
              <select className="select" value={f.frequency}
                      onChange={(e) => {
                        const freq = e.target.value as PayFrequency;
                        set({ frequency: freq, days: freq === "semimonthly" ? [15, 31] : freq === "monthly" ? [1] : [] });
                      }}>
                {Object.entries(FREQ_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            </label>
            {(f.frequency === "weekly" || f.frequency === "biweekly") && (
              <label className="field">
                One recent payday
                <input className="input" type="date" required value={f.anchor_date ?? ""}
                       onChange={(e) => set({ anchor_date: e.target.value || null })} />
              </label>
            )}
            {(f.frequency === "semimonthly" || f.frequency === "monthly") &&
              f.days.map((d, i) => (
                <label className="field" key={i}>
                  {f.frequency === "semimonthly" ? (i === 0 ? "First payday" : "Second payday") : "Payday"}
                  <select className="select" value={d}
                          onChange={(e) => set({ days: f.days.map((x, j) => (j === i ? Number(e.target.value) : x)) })}>
                    {DAY_OPTIONS.map((n) => <option key={n} value={n}>{dayLabel(n)}</option>)}
                  </select>
                </label>
              ))}
            <label className="field">
              If payday is a weekend
              <select className="select" value={f.weekend} onChange={(e) => set({ weekend: e.target.value as PayScheduleInput["weekend"] })}>
                <option value="before">Paid the Friday before</option>
                <option value="after">Paid the Monday after</option>
                <option value="none">Paid that day</option>
              </select>
            </label>
          </div>
          <details style={{ marginTop: 12 }}>
            <summary className="secondary" style={{ cursor: "pointer" }}>Matching options</summary>
            <div className="form-row" style={{ marginTop: 10 }}>
              <label className="field">
                Deposited into
                <select className="select" value={f.account ?? ""} onChange={(e) => set({ account: e.target.value || null })}>
                  <option value="">Any account</option>
                  {accounts.map((a) => <option key={a} value={a}>{a}</option>)}
                </select>
              </label>
              <label className="field" style={{ flex: "1 1 180px" }}>
                Description or memo contains
                <input className="input" value={f.match_text ?? ""} placeholder="e.g. PAYROLL"
                       onChange={(e) => set({ match_text: e.target.value || null })} />
              </label>
              <label className="field">
                Amount can vary by
                <select className="select" value={f.tolerance} onChange={(e) => set({ tolerance: Number(e.target.value) })}>
                  {[0.02, 0.05, 0.1, 0.2, 0.35].map((v) => <option key={v} value={v}>±{Math.round(v * 100)}%</option>)}
                </select>
              </label>
              <label className="field">
                Starting
                <input className="input" type="date" value={f.start_date ?? ""} onChange={(e) => set({ start_date: e.target.value || null })} />
              </label>
              <label className="field">
                Ending
                <input className="input" type="date" value={f.end_date ?? ""} onChange={(e) => set({ end_date: e.target.value || null })} />
              </label>
            </div>
          </details>
          <div style={{ display: "flex", gap: 8, marginTop: 14 }}>
            <button className="btn btn-primary" type="submit" disabled={busy}>{busy ? "Saving…" : "Save paycheck"}</button>
            <button className="btn" type="button" onClick={() => { setEditing(undefined); setError(undefined); }}>Cancel</button>
          </div>
        </form>
      )}

      {list.length === 0 && !editing ? (
        <div className="muted">
          No paychecks yet. Add one to track expected income, and every matching deposit will be confirmed as income
          automatically.
        </div>
      ) : (
        <div className="grid-2 grid-even" style={{ marginTop: 0 }}>
          <div>
            <h3 className="card-title" style={{ fontSize: 14, marginBottom: 8 }}>Your paychecks</h3>
            <div className="table-wrap">
            <table>
              <tbody>
                {list.map((s) => (
                  <tr key={s.id}>
                    <td>
                      <div><strong>{s.name}</strong></div>
                      <div className="small muted">
                        {money(s.amount)} · {describe(s)}
                        {s.account && ` · into ${s.account}`}
                      </div>
                    </td>
                    <td className="num">
                      <div>{money(s.monthly_amount)}<span className="muted small">/mo</span></div>
                    </td>
                    <td className="num" style={{ whiteSpace: "nowrap" }}>
                      <button className="btn btn-sm btn-ghost" onClick={() => {
                        const { id, monthly_amount: _m, ...form } = s;
                        void _m;
                        setEditing({ id, form });
                      }}>Edit</button>
                      <button className="btn btn-sm btn-ghost" onClick={() => remove(s.id)} aria-label={`Delete ${s.name}`}>Delete</button>
                    </td>
                  </tr>
                ))}
              </tbody>
              {list.length > 1 && (
                <tfoot>
                  <tr>
                    <td><strong>Total expected</strong></td>
                    <td className="num"><strong>{money(list.reduce((a, s) => a + s.monthly_amount, 0))}</strong><span className="muted small">/mo</span></td>
                    <td />
                  </tr>
                </tfoot>
              )}
            </table>
            </div>
          </div>
          <div>
            {shownMonths.map((m) => {
              const rows = upcoming.filter((e) => e.month === m);
              if (!rows.length) return null;
              const exp = rows.reduce((a, e) => a + e.amount, 0);
              const got = rows.reduce((a, e) => a + (e.actual_amount ?? 0), 0);
              return (
                <div key={m} style={{ marginBottom: 12 }}>
                  <h3 className="card-title" style={{ fontSize: 14, marginBottom: 2 }}>
                    Paydays in {monthLabel(m)}
                  </h3>
                  <div className="small muted" style={{ marginBottom: 6 }}>
                    {money(exp)} expected{got > 0 && ` · ${money(got)} received`}
                  </div>
                  <div className="table-wrap">
                  <table>
                    <tbody>
                      {rows.map((e) => (
                        <tr key={`${e.schedule_id}-${e.date}`}>
                          <td className="secondary" style={{ whiteSpace: "nowrap" }}>{dateLabel(e.date)}</td>
                          <td>{e.name}</td>
                          <td className="num">
                            {money(e.actual_amount ?? e.amount)}
                            {e.actual_amount !== null && Math.abs(e.actual_amount - e.amount) >= 0.01 && (
                              <div className="small muted">expected {money(e.amount)}</div>
                            )}
                          </td>
                          <td className="num"><span className={`badge ${STATUS[e.status].cls}`}>{STATUS[e.status].label}</span></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  </div>
                </div>
              );
            })}
            {(expected.data ?? []).some((e) => e.status === "missed") && (
              <div className="small muted">
                “Not found” means no deposit of about that amount arrived within 4 days of payday. Check that the
                account's latest export is in your folder.
              </div>
            )}
          </div>
        </div>
      )}
    </Card>
  );
}
