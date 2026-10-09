export type Kind = "expense" | "income" | "transfer" | "refund";
export type PaymentMethod = "credit" | "debit" | "transfer" | "check" | "cash";
export type AccountType = "credit_card" | "checking" | "savings" | "unknown";

export interface Transaction {
  id: string;
  date: string;
  month: string;
  description: string;
  merchant: string;
  amount: number;
  source_file: string;
  account: string;
  account_type: AccountType;
  payment_method: PaymentMethod;
  kind: Kind;
  category: string;
  category_source: "auto" | "rule" | "source" | "manual";
  source_category: string | null;
  is_recurring: boolean;
  recurring_id: string | null;
}

export interface TransactionPage {
  total: number;
  net_spending: number;
  items: Transaction[];
}

export type Breakdown = Record<string, number>;

export interface MonthSummary {
  month: string;
  spending: number;
  gross_spending: number;
  refunds: number;
  income: number;
  net_cashflow: number;
  transfers: number;
  recurring: number;
  one_time: number;
  transactions: number;
  by_category: Breakdown;
  by_payment_method: Breakdown;
  by_account: Breakdown;
  by_account_type: Breakdown;
}

export interface CategoryRow {
  category: string;
  spending: number;
  transactions: number;
  recurring: number;
  share: number;
  by_payment_method: Breakdown;
}

export interface Overview {
  months: number;
  first_month: string | null;
  last_month: string | null;
  transactions: number;
  total_spending: number;
  total_income: number;
  average_monthly_spending: number;
  average_monthly_income: number;
  average_basis_months?: number;
  recurring_monthly_cost: number;
  active_recurring: number;
  latest_month: MonthSummary | null;
  previous_month: MonthSummary | null;
  top_categories: CategoryRow[];
  by_payment_method: Breakdown;
  uncategorized: number;
}

export interface RecurringSeries {
  id: string;
  merchant: string;
  category: string;
  frequency: "weekly" | "biweekly" | "monthly" | "quarterly" | "yearly";
  average_amount: number;
  last_amount: number;
  monthly_cost: number;
  occurrences: number;
  first_date: string;
  last_date: string;
  next_expected: string;
  active: boolean;
  fixed_amount: boolean;
  payment_methods: PaymentMethod[];
  accounts: string[];
  transaction_ids: string[];
}

export interface Source {
  file_name: string;
  account: string;
  account_type: AccountType;
  transactions: number;
  duplicates: number;
  first_date: string | null;
  last_date: string | null;
  columns: Record<string, string | null>;
  inverted: boolean;
  warnings: string[];
  error: string | null;
  settings: { name?: string; account_type?: AccountType; invert_amounts?: boolean; day_first?: boolean };
  size_bytes: number;
  modified: string;
}

export interface Rule {
  id: string;
  pattern: string;
  category: string;
  match: "contains" | "regex";
  kind: Kind | null;
}

export interface Meta {
  categories: string[];
  accounts: string[];
  months: string[];
  payment_methods: PaymentMethod[];
  account_types: AccountType[];
  kinds: Kind[];
}

export interface AppConfig {
  data_dir: string;
  data_dir_exists: boolean;
  files: number;
  transactions: number;
  loaded_at: string;
}

/** Filters shared by the summary endpoints: which slice of money to look at. */
export interface ScopeFilter {
  payment_method?: PaymentMethod[];
  account?: string[];
  account_type?: AccountType[];
}
