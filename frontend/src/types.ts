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
  category_source: "auto" | "memo" | "rule" | "source" | "manual" | "paycheck";
  /** Free-text notes from the file's memo-like columns. */
  memo: string | null;
  source_category: string | null;
  is_recurring: boolean;
  recurring_id: string | null;
  /** Scrubbed from every budget total (still listed). */
  excluded: boolean;
  excluded_source: "manual" | "rule" | null;
  /** Money in the app only guessed at: the user should say income or paid back. */
  needs_review: boolean;
}

/** PATCH result: the updated transaction plus how many others share its merchant. */
export interface TransactionUpdate extends Transaction {
  merchant_total: number;
  merchant_different_category: number;
  merchant_different_excluded: number;
  /** Other money in from this merchant still waiting for a label. */
  merchant_needs_review: number;
}

export interface TransactionPage {
  total: number;
  excluded: number;
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
  /** income - spending: what's assumed saved this month */
  savings: number;
  /** savings / income, or null when there was no income */
  savings_rate: number | null;
  cumulative_savings: number;
  /** From your pay schedules; null when none cover this month. */
  expected_income?: number | null;
  transfers: number;
  recurring: number;
  one_time: number;
  transactions: number;
  by_category: Breakdown;
  by_payment_method: Breakdown;
  by_account: Breakdown;
  by_account_type: Breakdown;
  by_income_source: Breakdown;
}

export interface IncomeSource {
  source: string;
  category: string;
  amount: number;
  transactions: number;
  share: number;
  accounts: string[];
  months_received: number;
  average_monthly: number;
  last_date: string;
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
  total_savings: number;
  average_monthly_savings: number;
  savings_rate: number | null;
  months_saved: number;
  months_overspent: number;
  excluded_count: number;
  excluded_amount: number;
  needs_review?: number;
  needs_review_amount?: number;
}

export type PayFrequency = "weekly" | "biweekly" | "semimonthly" | "monthly";

export interface PaySchedule {
  id: string;
  name: string;
  amount: number;
  frequency: PayFrequency;
  anchor_date: string | null;
  days: number[];
  weekend: "before" | "after" | "none";
  account: string | null;
  match_text: string | null;
  tolerance: number;
  start_date: string | null;
  end_date: string | null;
  monthly_amount: number;
}

export type PayScheduleInput = Omit<PaySchedule, "id" | "monthly_amount">;

export interface ExpectedPay {
  schedule_id: string;
  name: string;
  date: string;
  month: string;
  amount: number;
  status: "received" | "due" | "missed" | "upcoming";
  transaction_id: string | null;
  actual_amount: number | null;
  actual_date: string | null;
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
  match: "contains" | "regex" | "merchant";
  kind: Kind | null;
  exclude: boolean;
  direction?: "any" | "in" | "out";
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
  /** Where categories, exclusions and rules are saved. */
  state_file: string;
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
