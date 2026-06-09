# agience-server-ophan

Status: **Draft** — design phase; implementation begins Phase 1i
Date: 2026-03-05

**Domain**: Finance, Economic Logic & Performance — value transfers, crypto, fiat, bookkeeping, resource allocation, budgeting, performance metrics, licensing, entitlements, and commercial operations

---

## Responsibility

Ophan is the economic operations layer. It executes and records value transfers (crypto and fiat), maintains a double-entry ledger of transactions, reconciles accounts across banks and exchanges, tracks resource usage and budgets, measures system performance, and produces the auditable financial, licensing, and metrics artifacts that form the foundation of platform economics.

---

## Tool Surface

### Transactions & Transfers

| Tool | Status | Description |
|---|---|---|
| `send_payment` | 🔲 Phase 1i | Initiate a value transfer — crypto (on-chain) or fiat (bank/wire) |
| `record_transaction` | 🔲 Phase 1i | Record an external transaction as a double-entry ledger artifact |
| `get_transaction` | 🔲 Phase 1i | Fetch a transaction by ID or on-chain hash |
| `list_transactions` | 🔲 Phase 1i | List transactions for an account over a date range |
| `fetch_statement` | 🔲 Phase 1i | Import a bank, exchange, or payroll statement as workspace artifacts |

### Accounts & Ledger

| Tool | Status | Description |
|---|---|---|
| `get_balance` | 🔲 Phase 1i | Get current balance for a wallet, bank account, or ledger account |
| `reconcile_account` | 🔲 Phase 1i | Match transactions against a statement and flag discrepancies |
| `create_invoice` | 🔲 Phase 1i | Generate an invoice artifact (accounts receivable) |
| `apply_payment` | 🔲 Phase 1i | Mark an invoice as paid and update the ledger |
| `run_report` | 🔲 Phase 1i | Produce a P&L, balance sheet, or cash-flow report artifact |

### Market Data

| Tool | Status | Description |
|---|---|---|
| `get_price` | 🔲 Phase 1i | Get current or historical price for a crypto or equity ticker |
| `get_market_data` | 🔲 Phase 1i | Fetch OHLCV data for a symbol over a date range |
| `track_wallet` | 🔲 Phase 1i | Monitor a blockchain wallet address for incoming activity |
| `get_portfolio` | 🔲 Phase 1i | Retrieve holdings from a connected brokerage or exchange |
| `calculate_pnl` | 🔲 Phase 1i | Calculate realised/unrealised P&L for on-chain or brokerage positions |

### Resource & Performance Metrics

| Tool | Status | Description |
|---|---|---|
| `track_resource_usage` | 🔲 Phase 1i | Track resource consumption and allocation across workspaces |
| `get_metrics` | 🔲 Phase 1i | Get system performance and efficiency metrics |
| `calculate_budget` | 🔲 Phase 1i | Calculate or project budget for a workspace or project |

### Licensing & Commercial Operations

| Tool | Status | Description |
|---|---|---|
| `resolve_license_posture` | 🔲 Phase 1i | Determine whether an organization falls inside the public self-host grant or needs a commercial license |
| `issue_license` | 🔲 Phase 1i | Create and sign a license artifact from entitlement inputs or approved policy parameters |
| `renew_license` | 🔲 Phase 1i | Extend, replace, or reissue an existing license artifact |
| `revoke_license` | 🔲 Phase 1i | Revoke a license and record the resulting compliance event |
| `review_installation` | 🔲 Phase 1i | Inspect installation state, activation status, and lease freshness |
| `record_usage_snapshot` | 🔲 Phase 1i | Ingest or reconcile aggregate licensing and metering snapshots |
| `run_licensing_report` | 🔲 Phase 1i | Produce entitlement, installation, renewal, or overage report artifacts |

Licensing tools are entitlement-gated. Base installation review and usage flows require an active licensing entitlement; issuance, renewal, revocation, and reporting require advanced licensing-operations entitlement.

---

## Artifact Types Owned

- `application/vnd.agience.transaction+json` — double-entry transaction record (debit, credit, memo, counterparty)
- `application/vnd.agience.account+json` — ledger account (chart of accounts entry)
- `application/vnd.agience.invoice+json` — accounts receivable/payable invoice
- `application/vnd.agience.portfolio+json` — portfolio snapshot with holdings and valuation
- `application/vnd.agience.market+json` — OHLCV/price feed artifact

Licensing-related artifacts should also be operationally owned by Ophan, but should remain a small shared family rather than proliferating into many bespoke handlers. In practice, Ophan should back licensing artifacts such as license, entitlement, installation, usage, and licensing-event records through shared structured-data handling.

Current licensing artifact family:

- `application/vnd.agience.license+json`
- `application/vnd.agience.entitlement+json`
- `application/vnd.agience.license-installation+json`
- `application/vnd.agience.license-usage+json`
- `application/vnd.agience.license-event+json`

Canonical licensing-party identity should be represented by the general platform Organization artifact rather than by Ophan's financial account artifact:

- `application/vnd.agience.organization+json`

---

## Credentials (BYOK)

Financial credentials are **Bring Your Own Key**, stored as encrypted user secrets in the platform — never in environment variables:

| Source | Secret name |
|---|---|
| Coinbase | `COINBASE_API_KEY`, `COINBASE_API_SECRET` |
| Binance | `BINANCE_API_KEY`, `BINANCE_API_SECRET` |
| Alpaca (equities) | `ALPACA_API_KEY`, `ALPACA_API_SECRET` |
| Plaid (bank accounts) | `PLAID_CLIENT_ID`, `PLAID_SECRET` |
| Stripe | `STRIPE_SECRET_KEY` |
| CoinGecko Pro | `COINGECKO_API_KEY` |

The server itself only needs `AGIENCE_API_KEY` to authenticate with the platform; user-level credentials are retrieved per request.

---

## Quick Start

```bash
pip install -e .
export AGIENCE_API_KEY=<your-key>
export AGIENCE_API_URI=https://api.yourdomain.com
python server.py
```

---

## Seed Knowledge

`knowledge/prompts/` — transaction classification, reconciliation, ledger entry, PnL interpretation prompts

---

## Target Repo

`github.com/Agience/agience-server-ophan` (public)
