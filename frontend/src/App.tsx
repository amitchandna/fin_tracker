import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "./api";
import { ErrorNotice, Loading, Segmented } from "./components/common";
import { Overview } from "./pages/Overview";
import { Recurring } from "./pages/Recurring";
import { Rules } from "./pages/Rules";
import { Sources } from "./pages/Sources";
import { Transactions, type TxnFilters } from "./pages/Transactions";
import type { ScopeFilter } from "./types";
import { useAsync } from "./useAsync";

const TABS = [
  { id: "overview", label: "Overview" },
  { id: "transactions", label: "Transactions" },
  { id: "recurring", label: "Recurring" },
  { id: "sources", label: "Files" },
  { id: "rules", label: "Rules" },
] as const;
type TabId = (typeof TABS)[number]["id"];

type ScopeKind = "all" | "credit" | "bank";

function tabFromHash(): TabId {
  const id = window.location.hash.replace(/^#\/?/, "");
  return (TABS.find((t) => t.id === id)?.id ?? "overview") as TabId;
}

export default function App() {
  const [tab, setTab] = useState<TabId>(tabFromHash);
  const [version, setVersion] = useState(0);
  const [scopeKind, setScopeKind] = useState<ScopeKind>("all");
  const [account, setAccount] = useState("");
  const [txnFilters, setTxnFilters] = useState<TxnFilters>({});
  const [rescanning, setRescanning] = useState(false);

  useEffect(() => {
    const onHash = () => setTab(tabFromHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const go = useCallback((id: TabId) => {
    window.location.hash = `/${id}`;
    setTab(id);
  }, []);

  const bump = useCallback(() => setVersion((v) => v + 1), []);
  const config = useAsync(() => api.config(), [version]);
  const meta = useAsync(() => api.meta(), [version]);
  // Unscoped category ranking: gives every category a stable colour across all views.
  const baseline = useAsync(() => api.categories(), [version]);

  const scope: ScopeFilter = useMemo(() => ({
    account_type: scopeKind === "credit" ? ["credit_card"] : scopeKind === "bank" ? ["checking", "savings"] : undefined,
    account: account ? [account] : undefined,
  }), [scopeKind, account]);

  const categoryOrder = useMemo(() => (baseline.data ?? []).map((c) => c.category), [baseline.data]);

  const drill = useCallback((filters: TxnFilters) => {
    setTxnFilters(filters);
    go("transactions");
  }, [go]);

  async function rescan() {
    setRescanning(true);
    try {
      await api.rescan();
    } finally {
      setRescanning(false);
      bump();
    }
  }

  const ready = config.data && meta.data;
  const noData = config.data && config.data.transactions === 0;
  const showScope = tab === "overview" || tab === "transactions";

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <svg className="brand-mark" viewBox="0 0 32 32" aria-hidden>
            <rect width="32" height="32" rx="7" fill="var(--accent)" />
            <rect x="7" y="16" width="4" height="9" rx="1.5" fill="#fff" />
            <rect x="14" y="10" width="4" height="15" rx="1.5" fill="#fff" />
            <rect x="21" y="6" width="4" height="19" rx="1.5" fill="#fff" />
          </svg>
          Fin Tracker
        </div>
        <div className="topbar-meta">
          {config.data && (
            <span className="data-dir" title={config.data.data_dir}>
              {config.data.files} file{config.data.files === 1 ? "" : "s"} · {config.data.data_dir}
            </span>
          )}
          <button className="btn" onClick={rescan} disabled={rescanning} title="Re-read the CSV folder">
            {rescanning ? <span className="spinner" aria-hidden /> : "↻"} Rescan
          </button>
        </div>
      </header>

      <nav className="tabs" role="tablist" aria-label="Sections">
        {TABS.map((t) => (
          <button key={t.id} role="tab" className="tab" aria-selected={tab === t.id} onClick={() => go(t.id)}>
            {t.label}
          </button>
        ))}
      </nav>

      {config.error && <ErrorNotice error={`Can't reach the backend (${config.error})`} onRetry={bump} />}

      {showScope && ready && !noData && (
        <div className="filters">
          <Segmented<ScopeKind>
            label="Which accounts to include"
            value={scopeKind}
            onChange={setScopeKind}
            options={[
              { value: "all", label: "All accounts" },
              { value: "credit", label: "Credit cards" },
              { value: "bank", label: "Debit & bank" },
            ]}
          />
          <select className="select" aria-label="Account" value={account} onChange={(e) => setAccount(e.target.value)}>
            <option value="">Every account</option>
            {meta.data!.accounts.map((a) => <option key={a} value={a}>{a}</option>)}
          </select>
        </div>
      )}

      <main>
        {!ready ? (config.error ? null : <Loading />) : noData && tab !== "sources" && tab !== "rules" ? (
          <div className="card empty">
            <h2>No transactions yet</h2>
            <p>
              Put bank or credit card CSV exports in <code>{config.data!.data_dir}</code>, then press Rescan.
            </p>
            <p className="small">
              Most banks offer CSV download from the account activity page. Any mix of credit, debit, checking
              and savings exports works.
            </p>
            <button className="btn" onClick={() => go("sources")}>See detected files</button>
          </div>
        ) : tab === "overview" ? (
          <Overview scope={scope} categoryOrder={categoryOrder} accounts={meta.data!.accounts} version={version}
                    onDrill={drill} />
        ) : tab === "transactions" ? (
          <Transactions meta={meta.data!} scope={scope} filters={txnFilters} onFiltersChange={setTxnFilters}
                        version={version} onDataChanged={bump} />
        ) : tab === "recurring" ? (
          <Recurring version={version} onDrill={drill} />
        ) : tab === "sources" ? (
          <Sources config={config.data!} version={version} onDataChanged={bump} />
        ) : (
          <Rules meta={meta.data!} version={version} onDataChanged={bump} />
        )}
      </main>
    </div>
  );
}
