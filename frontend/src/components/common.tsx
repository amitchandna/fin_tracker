import type { ReactNode } from "react";

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="loading-block" role="status">
      <span className="spinner" aria-hidden /> {label}
    </div>
  );
}

export function ErrorNotice({ error, onRetry }: { error: string; onRetry?: () => void }) {
  return (
    <div className="notice notice-error" role="alert">
      Something went wrong: {error}{" "}
      {onRetry && (
        <button className="btn btn-sm" onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  );
}

export function Segmented<T extends string>({
  value, options, onChange, label,
}: {
  value: T;
  options: { value: T; label: string }[];
  onChange: (v: T) => void;
  label: string;
}) {
  return (
    <div className="seg" role="group" aria-label={label}>
      {options.map((o) => (
        <button key={o.value} type="button" aria-pressed={o.value === value} onClick={() => onChange(o.value)}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function StatTile({ label, value, foot }: { label: string; value: string; foot?: ReactNode }) {
  return (
    <div className="card">
      <div className="tile-label">{label}</div>
      <div className="tile-value">{value}</div>
      {foot && <div className="tile-foot">{foot}</div>}
    </div>
  );
}

export function Swatch({ color }: { color: string }) {
  return <span className="swatch" style={{ background: color }} aria-hidden />;
}

export function Card({ title, sub, actions, children }: {
  title: string;
  sub?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="card">
      <div className="card-head">
        <div>
          <h2 className="card-title">{title}</h2>
          {sub && <p className="card-sub">{sub}</p>}
        </div>
        {actions && <div className="filters" style={{ margin: 0 }}>{actions}</div>}
      </div>
      {children}
    </section>
  );
}
