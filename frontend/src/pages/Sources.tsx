import { useState } from "react";
import { api } from "../api";
import { ErrorNotice, Loading } from "../components/common";
import { ACCOUNT_TYPE_LABELS, dateLabel } from "../format";
import type { AccountType, AppConfig, Source } from "../types";
import { useAsync } from "../useAsync";

export function Sources({ config, version, onDataChanged }: {
  config: AppConfig;
  version: number;
  onDataChanged: () => void;
}) {
  const result = useAsync(() => api.sources(), [version]);
  if (result.error) return <ErrorNotice error={result.error} onRetry={result.reload} />;
  if (!result.data) return <Loading />;

  return (
    <div>
      <div className="notice notice-info">
        Reading every <code>.csv</code> file in <span className="mono">{config.data_dir}</span> (including
        subfolders). Drop new exports there and press <strong>Rescan</strong>. Exports that overlap are
        de-duplicated automatically.
      </div>
      {result.data.length === 0 ? (
        <div className="card empty">
          <h2>No CSV files found</h2>
          Export transactions from your bank or card and save the CSV files to <code>{config.data_dir}</code>.
        </div>
      ) : (
        <div className="source-grid">
          {result.data.map((s) => <SourceCard key={s.file_name} source={s} onSaved={onDataChanged} />)}
        </div>
      )}
    </div>
  );
}

function SourceCard({ source: s, onSaved }: { source: Source; onSaved: () => void }) {
  const [name, setName] = useState(s.settings.name ?? "");
  const [type, setType] = useState<AccountType | "">(s.settings.account_type ?? "");
  const [invert, setInvert] = useState<"" | "true" | "false">(
    s.settings.invert_amounts === undefined ? "" : s.settings.invert_amounts ? "true" : "false",
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const dirty =
    name !== (s.settings.name ?? "") ||
    type !== (s.settings.account_type ?? "") ||
    invert !== (s.settings.invert_amounts === undefined ? "" : String(s.settings.invert_amounts));

  async function save() {
    setBusy(true);
    setError(undefined);
    try {
      await api.updateSource(s.file_name, {
        name: name.trim() || undefined,
        account_type: type || undefined,
        invert_amounts: invert === "" ? undefined : invert === "true",
      });
      onSaved();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card">
      <div className="card-head" style={{ marginBottom: 6 }}>
        <div style={{ minWidth: 0 }}>
          <h2 className="card-title">{s.account}</h2>
          <p className="card-sub mono" style={{ overflowWrap: "anywhere" }}>{s.file_name}</p>
        </div>
        {s.error ? <span className="badge badge-error">✕ Not loaded</span> : (
          <span className="badge badge-accent">{ACCOUNT_TYPE_LABELS[s.account_type]}</span>
        )}
      </div>

      {s.error && <div className="notice notice-error" style={{ margin: "8px 0" }}>{s.error}</div>}
      {s.warnings.map((w) => <div key={w} className="notice notice-warn" style={{ margin: "8px 0", padding: "6px 10px" }}>⚠ {w}</div>)}

      <dl className="kv">
        <dt>Transactions</dt>
        <dd>{s.transactions.toLocaleString()}{s.duplicates > 0 && <span className="muted"> ({s.duplicates} duplicates skipped)</span>}</dd>
        <dt>Date range</dt>
        <dd>{s.first_date && s.last_date ? `${dateLabel(s.first_date)} – ${dateLabel(s.last_date)}` : "—"}</dd>
        <dt>Columns used</dt>
        <dd className="small">
          {Object.entries(s.columns).filter(([, v]) => v).map(([k, v]) => `${k}: ${v}`).join(" · ") || "—"}
        </dd>
        <dt>Last modified</dt>
        <dd>{s.modified.replace("T", " ")}</dd>
      </dl>

      <details>
        <summary className="secondary" style={{ cursor: "pointer" }}>Adjust how this file is read</summary>
        <div className="stack" style={{ gap: 10, marginTop: 10 }}>
          <label className="field">
            Account name
            <input className="input" value={name} placeholder={s.account} onChange={(e) => setName(e.target.value)} />
          </label>
          <label className="field">
            Account type
            <select className="select" value={type} onChange={(e) => setType(e.target.value as AccountType | "")}>
              <option value="">Detect automatically</option>
              <option value="credit_card">Credit card</option>
              <option value="checking">Checking / debit</option>
              <option value="savings">Savings</option>
            </select>
          </label>
          <label className="field">
            Amount signs
            <select className="select" value={invert} onChange={(e) => setInvert(e.target.value as "" | "true" | "false")}>
              <option value="">Detect automatically{s.inverted ? " (currently flipped)" : ""}</option>
              <option value="false">Purchases are negative</option>
              <option value="true">Purchases are positive (flip)</option>
            </select>
          </label>
          {error && <div className="notice notice-error">{error}</div>}
          <div>
            <button className="btn btn-primary" disabled={!dirty || busy} onClick={save}>
              {busy ? "Saving…" : "Save"}
            </button>
          </div>
        </div>
      </details>
    </section>
  );
}
