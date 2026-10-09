# Fin Tracker

A local-first personal finance dashboard. Point it at a folder of CSV exports from your
banks and credit cards. It reads every file, categorizes each transaction and shows where
your money goes each month, across all of your accounts.

- **Monthly spending** by category, payment method (credit card, debit/bank, ACH, check, cash),
  account, or recurring vs. one-time.
- **Credit and debit are tracked separately but bucketed together.** A Netflix charge on a
  credit card and a grocery run on a debit card each go to their category (Subscriptions,
  Groceries). You can still filter or group by how each one was paid.
- **No double counting.** Paying your credit card from checking is a *transfer*, not
  spending, and so are moves between your own accounts. Refunds reduce spending in the
  category they came from.
- **Income and savings.** Shows how much comes in each month and from where (paychecks,
  interest, tax refunds). Whatever comes in and isn't spent is counted as saved, so you get
  monthly savings, your savings rate and a running total saved. Transfers to your savings or
  investment accounts aren't spending, so they count as saved too.
- **You decide what counts as income.** Every deposit is either **income** or **paid back**,
  meaning money that offsets something you spent. A friend paying you $15 for their movie
  ticket is paid back against Entertainment, so your Entertainment spending drops by $15
  and your income doesn't inflate. The app guesses until you choose, and lists unconfirmed
  deposits under *Money in to review*. One click can apply your choice to every deposit from
  that sender, including future ones.
- **Expected income.** Enter your paychecks: the amount that lands in your account and when.
  Schedules can be weekly, every 2 weeks, twice a month (e.g. the 15th and last day) or
  monthly, and paydays on weekends shift to the Friday before (or Monday after). The app shows
  expected vs. actual income per month and flags any paycheck that didn't arrive. Deposits
  that match a paycheck (within 4 days and ±10% by default) are confirmed as income
  automatically.
- **Exclude anything from the budget.** A one-off that doesn't belong (a reimbursed work trip,
  buying a car, money you moved for someone else) can be left out of every total, chart and
  savings figure with one click. It stays visible in the transaction list and you can add it
  back any time. A rule can also exclude every matching transaction automatically.
- **Recurring payments** (subscriptions, rent, utilities, insurance, loans) are detected from
  regular charges with consistent amounts. Each one shows its frequency, monthly cost, the
  card or account it bills to, and when the next charge is expected.
- **You can correct categories.** Change any transaction's category, or add rules like
  "description contains `JOE'S COFFEE` → Dining" that apply everywhere.
- **Your data stays local.** Nothing leaves your machine. `data/` is git-ignored.

## Quick start

Requirements: Python 3.11+ and Node 20+.

```bash
make install        # backend venv + frontend packages
make demo           # build the UI and serve it with the bundled sample data
# open http://localhost:8000
```

To use your own exports:

```bash
cp ~/Downloads/*.csv data/      # or keep them anywhere and pass DATA=
make run                        # uses ./data
make run DATA=~/Documents/bank-exports
```

Drop new files into the folder and press **Rescan**. The app also notices changed files on
its own. Subfolders are included. Overlapping exports (e.g. Jan–Mar and Feb–Apr of the same
card) are de-duplicated.

### Development

```bash
make dev-backend    # API with auto-reload on :8000
make dev-frontend   # Vite dev server on :5173 (proxies /api to :8000)
make test           # pytest + TypeScript typecheck + vitest
```

## Supported CSV formats

The parser adapts to the file's layout. It doesn't rely on a fixed list of banks:

| What varies | How it's handled |
|---|---|
| Column names | Matches common aliases: `Transaction Date`/`Posted Date`/`Date`, `Description`/`Payee`/`Merchant`/`Memo`, etc. |
| Amount layout | One signed `Amount` column, separate `Debit`/`Credit` (or `Withdrawal`/`Deposit`) columns, or an amount plus a `DR`/`CR` type column |
| Sign convention | Detects cards that list charges as **positive** (Amex, Discover) and flips them |
| Preamble rows | Skips account-info lines before the real header |
| No header | Infers date / amount / description columns from the data |
| Formats | `$1,234.56`, `(12.34)`, `12.34-`, `12.34 CR`, `1.234,56`, `,` `;` `\t` `\|` delimiters, ISO / US / day-first dates, UTF-8 / UTF-16 / Windows-1252 |
| Bank categories | When an export includes its own category column (e.g. Chase), it's used as a fallback |

The account type (credit card / checking / savings) is detected from the file name, the
columns and the content. You can override the account name, type and sign convention for
any file from the **Files** tab.

## How transactions are classified

Each transaction gets three labels:

- **Kind**: `expense`, `refund`, `income` or `transfer`. Only expenses minus refunds count
  as spending.
- **Payment method**: `credit` (anything on a credit card), `debit` (debit card / bank
  purchase), `transfer` (ACH, Zelle, bill pay), `check` or `cash` (ATM).
- **Category**: picked by the first match in this order: your manual override → your rules →
  ~500 built-in merchant keywords → the bank's own category → `Uncategorized`.

On top of these, a transaction can be **excluded from the budget**, either by you or by a
rule. Excluded transactions don't count toward spending, income, savings or recurring
detection, but you can still see them on the Transactions tab.

**Money in** is either *income* (category `Income`) or *paid back*, which is any other
category. Paid-back money reduces spending in that category. Deposits stay in the review
queue until you label them, a rule labels them, or they match an expected paycheck.

**Savings** for a month = income − spending. That assumes whatever wasn't spent was kept.

## Architecture

```
backend/                 FastAPI + stdlib csv (no pandas)
  app/parser.py          header detection, column mapping, amount/date parsing, sign normalisation
  app/categorizer.py     merchant normalisation, built-in rules, payment method, kind
  app/recurring.py       cadence + amount-consistency detection of recurring payments
  app/paychecks.py       pay schedules -> expected paydays, matched to real deposits
  app/ledger.py          scans the folder, de-duplicates, caches until files/settings change
  app/analytics.py       monthly / category / overview aggregations
  app/state.py           your rules, overrides and per-file settings (JSON, atomic writes)
  app/main.py            REST API; also serves the built frontend
  tests/                 parser, categorizer, recurring and API tests
frontend/                React + TypeScript + Vite + Recharts
sample_data/             realistic exports in four different formats (scripts/generate_sample_data.py)
```

### Your changes are saved

Every category change, budget exclusion, rule and per-file setting is saved straight away to
`<data dir>/.fintracker/state.json`, and reloaded the next time the app starts. To keep it
somewhere else, set `FIN_TRACKER_STATE_DIR`. Your CSV files are never modified: a fresh
download from your bank would overwrite edits made in them, and the originals stay
untouched as your record.

- **Saved choices survive restarts, account renames, file renames and re-exports.** Each one
  is stored with the transaction's date, amount and description. If its internal ID changes
  (e.g. this month's export is saved as `chase_oct.csv` instead of `chase_sept.csv`), it's
  matched to the transaction again by those details. The file is plain, readable JSON, and
  you can back it up with the rest of your data folder.
- **Categorize once per merchant.** After you change a category or exclude a transaction,
  the app offers to do the same for every other transaction from that merchant. Accepting
  creates a merchant rule, so new charges in future exports are handled automatically too.

### API

| Endpoint | Purpose |
|---|---|
| `GET /api/summary/overview` | headline numbers |
| `GET /api/summary/monthly` | per-month totals with breakdowns by category, payment method, account, recurring |
| `GET /api/summary/categories?month=YYYY-MM` | category breakdown |
| `GET /api/summary/income?month=YYYY-MM` | income by source |
| `GET /api/transactions` | filter by `month`, `category`, `account`, `payment_method`, `account_type`, `kind`, `recurring`, `excluded`, `needs_review`, `q`; sort and paginate |
| `PATCH /api/transactions/{id}` | set or reset a category (`category`), exclude from or add back to the budget (`excluded`) |
| `GET /api/transactions/export` | categorized CSV export |
| `GET/POST /api/income/schedules`, `PUT/DELETE /api/income/schedules/{id}` | your expected paychecks |
| `GET /api/income/expected?month=YYYY-MM` | expected paydays and whether each arrived |
| `GET /api/recurring` | detected recurring payments |
| `GET/POST/DELETE /api/rules` | custom rules (`contains`, `regex` or exact `merchant` match; optional `exclude`; `direction` limits a rule to money `in` or `out`) |
| `GET /api/sources`, `PUT /api/sources/{file}` | detected files and per-file overrides |
| `POST /api/rescan` | force a re-read |

Interactive docs are served at `http://localhost:8000/docs`.
