import { useState, type FormEvent } from "react";
import { api } from "../api";
import { Card, ErrorNotice, Loading } from "../components/common";
import { KIND_LABELS } from "../format";
import type { Kind, Meta, Rule } from "../types";
import { useAsync } from "../useAsync";

export function Rules({ meta, version, onDataChanged }: { meta: Meta; version: number; onDataChanged: () => void }) {
  const rules = useAsync(() => api.rules(), [version]);
  const [pattern, setPattern] = useState("");
  const [category, setCategory] = useState("");
  const [match, setMatch] = useState<Rule["match"]>("contains");
  const [kind, setKind] = useState<Kind | "">("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const [message, setMessage] = useState<string>();

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!pattern.trim() || !category.trim()) return;
    setBusy(true);
    setError(undefined);
    setMessage(undefined);
    try {
      const r = await api.addRule({ pattern: pattern.trim(), category: category.trim(), match, kind: kind || null });
      setMessage(`Rule added — it now categorizes ${r.matched} transaction${r.matched === 1 ? "" : "s"}.`);
      setPattern("");
      onDataChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: string) {
    try {
      await api.deleteRule(id);
      onDataChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <div className="stack">
      <Card
        title="Add a categorization rule"
        sub="Rules run before the built-in categories. Use them to teach the app about merchants it gets wrong. Newest rules win."
      >
        <form className="form-row" onSubmit={submit}>
          <label className="field" style={{ flex: "2 1 220px" }}>
            When the description {match === "regex" ? "matches the pattern" : "contains"}
            <input className="input" value={pattern} onChange={(e) => setPattern(e.target.value)}
                   placeholder={match === "regex" ? "e.g. ^SQ \\*JOE" : "e.g. JOE'S COFFEE"} required />
          </label>
          <label className="field" style={{ flex: "1 1 180px" }}>
            Set category to
            <input className="input" list="category-options" value={category}
                   onChange={(e) => setCategory(e.target.value)} placeholder="Pick or type a new one" required />
            <datalist id="category-options">
              {meta.categories.map((c) => <option key={c} value={c} />)}
            </datalist>
          </label>
          <label className="field">
            Match type
            <select className="select" value={match} onChange={(e) => setMatch(e.target.value as Rule["match"])}>
              <option value="contains">Contains text</option>
              <option value="regex">Regular expression</option>
            </select>
          </label>
          <label className="field">
            Treat as
            <select className="select" value={kind} onChange={(e) => setKind(e.target.value as Kind | "")}>
              <option value="">Automatic</option>
              {meta.kinds.map((k) => <option key={k} value={k}>{KIND_LABELS[k]}</option>)}
            </select>
          </label>
          <button className="btn btn-primary" type="submit" disabled={busy}>{busy ? "Adding…" : "Add rule"}</button>
        </form>
        {message && <div className="notice notice-info" style={{ marginTop: 12, marginBottom: 0 }}>{message}</div>}
        {error && <div style={{ marginTop: 12 }}><ErrorNotice error={error} /></div>}
      </Card>

      <Card title="Your rules">
        {rules.error ? <ErrorNotice error={rules.error} onRetry={rules.reload} /> : !rules.data ? <Loading /> :
          rules.data.length === 0 ? (
            <div className="muted">No rules yet. You can also fix a single transaction from the Transactions tab.</div>
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr><th>Pattern</th><th>Category</th><th>Treat as</th><th /></tr>
                </thead>
                <tbody>
                  {rules.data.map((r) => (
                    <tr key={r.id}>
                      <td>
                        <span className="mono">{r.pattern}</span>
                        {r.match === "regex" && <span className="badge" style={{ marginLeft: 6 }}>regex</span>}
                      </td>
                      <td>{r.category}</td>
                      <td className="secondary">{r.kind ? KIND_LABELS[r.kind] : "Automatic"}</td>
                      <td className="num">
                        <button className="btn btn-sm" onClick={() => remove(r.id)} aria-label={`Delete rule ${r.pattern}`}>
                          Delete
                        </button>
                      </td>
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
