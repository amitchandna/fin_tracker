import type {
  AppConfig, CategoryRow, IncomeSource, Meta, MonthSummary, Overview, RecurringSeries, Rule, ScopeFilter, Source,
  Transaction, TransactionPage,
} from "./types";

type Params = Record<string, string | number | boolean | string[] | undefined | null>;

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export function toQuery(params: Params = {}): string {
  const qs = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    if (Array.isArray(value)) value.forEach((v) => qs.append(key, v));
    else qs.append(key, String(value));
  }
  const s = qs.toString();
  return s ? `?${s}` : "";
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: init?.body ? { "Content-Type": "application/json", ...init.headers } : init?.headers,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detail);
  }
  return res.status === 204 ? (undefined as T) : res.json();
}

const scope = (s?: ScopeFilter): Params => ({ ...s });

export const api = {
  config: () => request<AppConfig>("/api/config"),
  meta: () => request<Meta>("/api/meta"),
  rescan: () => request<{ files: number; transactions: number }>("/api/rescan", { method: "POST" }),
  overview: (s?: ScopeFilter) => request<Overview>(`/api/summary/overview${toQuery(scope(s))}`),
  monthly: (s?: ScopeFilter) => request<MonthSummary[]>(`/api/summary/monthly${toQuery(scope(s))}`),
  categories: (month?: string, s?: ScopeFilter) =>
    request<CategoryRow[]>(`/api/summary/categories${toQuery({ month, ...scope(s) })}`),
  income: (month?: string) => request<IncomeSource[]>(`/api/summary/income${toQuery({ month })}`),
  transactions: (params: Params) => request<TransactionPage>(`/api/transactions${toQuery(params)}`),
  exportUrl: (params: Params) => `/api/transactions/export${toQuery(params)}`,
  setCategory: (id: string, category: string | null) =>
    request<Transaction>(`/api/transactions/${id}`, { method: "PATCH", body: JSON.stringify({ category }) }),
  /** true = remove from budget, false = keep (overrides rules), null = let rules decide. */
  setExcluded: (id: string, excluded: boolean | null) =>
    request<Transaction>(`/api/transactions/${id}`, { method: "PATCH", body: JSON.stringify({ excluded }) }),
  recurring: () => request<RecurringSeries[]>("/api/recurring"),
  sources: () => request<Source[]>("/api/sources"),
  updateSource: (file: string, settings: Source["settings"]) =>
    request<Source>(`/api/sources/${file.split("/").map(encodeURIComponent).join("/")}`, {
      method: "PUT",
      body: JSON.stringify(settings),
    }),
  rules: () => request<Rule[]>("/api/rules"),
  addRule: (rule: Omit<Rule, "id">) =>
    request<Rule & { matched: number }>("/api/rules", { method: "POST", body: JSON.stringify(rule) }),
  deleteRule: (id: string) => request<void>(`/api/rules/${id}`, { method: "DELETE" }),
};
