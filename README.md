# Portfolio Lens

A CSV-first Streamlit application with four tabs: upload and validation; current prices and covered valuation; historical reported activity; and security performance, risk and local CSV chat.

## Setup and launch

Python 3.11 or newer is required. From this project directory:

```bash
uv sync
uv run streamlit run main.py
```

In this workspace, uv was installed locally as `.tools/uv`, the virtual environment is `.venv`, and the package cache is `.uv-cache`. You can run the local executable directly:

```bash
.tools/uv sync --cache-dir .uv-cache
.tools/uv run --cache-dir .uv-cache streamlit run main.py
.tools/uv run --cache-dir .uv-cache pytest -q
```

Or add the local tool directory to the current shell's PATH:

```bash
export PATH="$PWD/.tools:$PATH"
export UV_CACHE_DIR="$PWD/.uv-cache"
uv sync
uv run streamlit run main.py
```

No virtual environment activation is needed with `uv run`. In your IDE, select `.venv/bin/python` as the interpreter. `uv.lock` records the resolved dependencies. The local uv executable, caches, environment, and secrets are ignored by Git. They are not portable project source; on another computer install uv using its [official instructions](https://docs.astral.sh/uv/getting-started/installation/).

## Local CSV assistant — no API key needed

The chatbot runs locally using fixed question patterns and deterministic calculations on the full validated CSV subset. It does not use an LLM, require a model download, read API credentials, or make network requests. No `OPENAI_API_KEY`, `OPENAI_MODEL`, or Groq settings are needed. Existing private credential files are left untouched and unused by the assistant.

Ask about biggest additions/reductions, the latest quarter, top reported holdings, exits/re-entries, a ticker’s history, missing inputs, or chart meanings. Short ticker follow-ups reuse the previous question’s topic. Unsupported questions receive an explanation and examples; arbitrary code and SQL are never executed. This is a limited rule-based assistant, not unrestricted ChatGPT.

Answers identify CSV scope and observation dates. All calculations honor the sidebar filters; source changes reset chat. Profit and risk questions use already-calculated values only when available. The assistant never fetches prices. The sidebar's explicit Yahoo market-data fetch remains an independent optional network feature, and reused Yahoo results are labeled as such.

## Use

1. Upload a CSV in **CSV Upload**.
2. Select the source columns to use. All are selected initially; changes apply automatically.
3. Use the sidebar and remaining tabs for research. Validation findings appear in the sidebar; fix blocking errors in the CSV and upload it again.

The upload tab contains no other options, previews, settings or action buttons. Interpretation is inferred from the original source schema, so deselecting columns never turns activity into current holdings. Dated holdings are treated as observations with unverified completeness. Import conventions: missing currency = USD, month-first ordinary dates, per-share cost basis, and percentage-point units for _pct/percent columns. Generic bare percentage values are unavailable rather than guessed; add explicit % suffixes in the CSV to clarify them. Original CSVs remain unchanged.

Original files and unmapped columns stay intact. The app stores the source preview, normalized data, and active validated subset separately in session memory. It does not save uploads to disk or use a database. The original local historical CSV is used only as a compatibility test, not as a hard-coded data source.

## Input contract

| Interpretation | Required for its main analysis | Meaning |
| --- | --- | --- |
| Current holdings | Ticker; quantity for valuation | Quantities represent the current position. Ticker-only data becomes a watchlist. |
| Complete historical snapshots | Ticker, date/period, shares | User asserts each snapshot is complete. Only the latest selected snapshot is valued; no older positions or weights are carried forward. |
| Reported position changes | Ticker, date/period, action | Rows are reported changes, not individual executed trades or a complete current portfolio. |

Common aliases are detected and all mappings can be changed. Supported fields include ticker, company, date/period, action, shares, price, value, weight, share change, percentage share change, portfolio percentage change, cost basis, currency, source URL, retrieval date, raw activity and locked fields. The provided CSV aliases (`shares_held_after`, `reported_price_usd`, `reported_value_usd`, `portfolio_pct`, `shares_change`, `shares_change_pct`, `portfolio_change_pct`, `activity_raw`, `locked_fields`) are included. Locked-field text is preserved as source metadata; missing values are never reconstructed from it.

Quarter labels such as `2024 Q2` become quarter-end observation dates. Ordinary dates use your day-first/month-first selection. Numbers accept commas as thousands separators, decimal points, parentheses for negatives and percent suffixes. Decimal commas and nonnumeric currency symbols must be cleaned in the source. `Percentage points` means `2.5` → 2.5%; `Fractions` means `0.025` → 2.5%. An explicit `%` suffix always denotes percentage points. Blanks remain missing. A weight of `0.00%` does not remove a position.

Actions normalize to `add`, `reduce`, `new_position`, `sold_out`, `initial_disclosure`. Initial disclosures never count as purchases. Unknown actions remain visible in validation and are excluded from action-specific summaries until mapped. An action mapping such as “buy” reflects the chosen dataset interpretation; it does not turn the app into a transaction ledger.

Negative balances, malformed numbers, invalid symbols, action-sign conflicts and nonzero exit balances require correction or explicit exclusion. Share-times-price differences above 2% plus one currency unit are warnings. Duplicate ticker or ticker-period rows are candidates for review: duplicates are not silently combined in valuation; same-period activity rows remain distinct reported events. Multiple actual transactions can be legitimate, but transaction-ledger interpretation and portfolio return reconstruction are not implemented.

## Calculation conventions and limitations

- **Valuation:** supplied shares × latest available Yahoo daily close. Allocation uses covered value in each currency. Missing prices/quantities, currency mismatches and duplicate security positions are uncovered. Totals are labeled partial when necessary. No foreign-exchange rates are assumed; different currencies have separate totals. Currency codes must match Yahoo (including any provider-specific subunit conventions); no unit conversion is inferred.
- **Cost basis:** user chooses per-share or total-position basis, assumed in the supplied position currency. Unrealized gains require both valid basis and a covered valuation. No realized P&L is inferred.
- **Exposure:** company names never automatically merge securities. Users can explicitly confirm share-class/company grouping; the original security rows remain. Sectors come from available Yahoo classifications, with missing classifications labeled unclassified.
- **Activity:** counts of reported changes are neither net dollar flows nor turnover. Historical changes do not establish the complete current portfolio. Boundary periods and gaps can be incomplete; no zero-activity periods are fabricated. Consecutive-quarter streaks require observations in adjacent calendar quarters. Durations are observed entry-to-exit intervals, not exact execution holding periods; initial disclosures and unclosed histories remain incomplete. Inconsistent quantities may reflect missing events or corporate actions.
- **Returns:** security series use Yahoo adjusted close when available, otherwise explicitly labeled price-only close. Comparisons require a common observed window and consistent adjustment labels; missing prices are not filled. Cumulative return is price / first common price − 1, equivalent to compounding observed interval returns. Drawdown is price / running peak − 1. These omit account cash, fees and trading behavior. Different security currencies produce local-currency returns, not a currency-hedged or common-currency comparison.
- **Risk:** sample standard deviation of adjacent daily returns × √252; at least 20 valid returns are needed for volatility. At least three common positive prices are needed for return/drawdown display. Gaps remain missing. Drawdown on common observed dates can miss extrema on excluded dates; the method is disclosed alongside results.
- **Actual portfolio returns:** unavailable under the supported CSV contract. The UI lists required total valuations including cash, external cash flows, complete dated holdings/transactions/corporate actions, and consistent currency conversion. It does not report time-weighted or money-weighted portfolio returns from incomplete data.
- **Market requests:** independent symbol failures retain successful results. A five-minute process cache is keyed by ticker and price-history dates. Session market results expire on the next UI interaction after five minutes; manual refresh bypasses the cache. Quotes show observation and retrieval timestamps and are daily/delayed, not a live trading feed. Adjusted histories may be revised by the provider.
- **Scope:** up to 100,000 CSV rows, 25 MB upload size, 100 manual tickers and 40 priced securities per request. All analytics are recomputed from the active validated dataset and filters. No persistent analysis cache, authentication, database, deployment infrastructure or investment-motive inference is included.

## Project layout

```text
main.py                         Page, state, sidebar, and four tabs
components/csv_upload.py        Source selection, mappings and validation UI
components/portfolio_overview.py Prices, covered valuation and exposure UI
components/historical_activity.py Reported activity UI
components/performance_chatbot.py Security risk and local CSV chat UI
utils/data_loader.py            CSV parsing and normalization
utils/validation.py             Row-level checks and analysis requirements
utils/market_data.py            Yahoo access and cache
utils/analytics.py              Independently testable calculations
utils/chatbot.py                Bounded context and text-only local CSV answers
utils/state.py                  Dataset/context invalidation
sample_data/                    Four example CSVs
 tests/                         Deterministic calculation/provider/UI tests
```

## Verification and troubleshooting

Run `uv run pytest -q`. Tests cover covered/partial values, currencies, basis conventions, missing data, mappings, percentage units, duplicates, action counts, re-entry and incomplete histories, snapshot selection, synthetic returns/drawdowns, mocked provider failures, bounded chat, missing credentials, state invalidation, and Streamlit's simulated UI. No test requires a live API key. See the verification record below for checks performed in this workspace.

If Yahoo returns no data, verify its symbol spelling (for example, Yahoo share-class symbols often use a hyphen), retry later, or choose fewer tickers. Historical/retired identifiers may be unavailable. A provider failure does not invalidate your uploaded activity history. If a question is not understood, try one of the starter questions or use an exact ticker symbol. The local assistant supports a bounded set of questions. If `uv` is not on PATH in this workspace, use `.tools/uv` as shown above. Run commands from the project root so examples and `.env` resolve correctly.

Implementation references: [Streamlit chart API](https://docs.streamlit.io/develop/api-reference/charts/st.plotly_chart), [yfinance history/download API](https://ranaroussi.github.io/yfinance/reference/api/yfinance.download.html).

### Verification record — October 10, 2026

- Installed uv 0.13.0 locally in `.tools/uv`, created `.venv`, resolved dependencies into `uv.lock`, and installed them successfully with uv.
- `uv run pytest -q`: **19 tests passed**. One upstream pandas/NumPy timedelta deprecation warning was emitted by the duplicate-position fixture; no test failed.
- Python bytecode compilation passed for the entry point, utilities, components and tests.
- Streamlit AppTest checked four tab labels/order, empty state, example selection and mapping, holdings valuation, performance display, activity drilldown, date grouping, ticker filtering, manual watchlist, dataset replacement/clearing, snapshots, missing OpenAI configuration and mocked market failures.
- Imported the original historical CSV without modifying it: **648 rows, 96 tickers**, observed dates from **2013 Q2 through 2026 Q2**. Normalization and validation produced no findings with explicitly selected percentage-point units. Counts: 237 additions, 233 reductions, 82 new positions, 75 sold-out events and 21 initial disclosures. This checks parsing compatibility, not the completeness or factual accuracy of the source.
- Launched Streamlit using the project virtual environment. Both `/` and `/_stcore/health` returned HTTP 200 on localhost.
- Limitations: no full browser-driven drag-and-drop or visual smoke test was performed. UI checks used Streamlit's simulated app harness; CSV byte parsing was separately tested. Live Yahoo and OpenAI responses were not tested; provider success/failure and chatbot requests were mocked. No OpenAI credentials were supplied.

Upload simplification checks: standard holdings import without advanced edits, collapsed advanced controls, no unnecessary percentage question for ticker/quantity files, and a single required confirmation for ambiguous percentage columns. Both Word prompt documents now require only the uploader and selectable column list.

Latest upload UI verification: 19 tests passed, including automatic import, column deselection, activity-type preservation, upload removal, provider failures and invalid-row blocking. Earlier setup/advanced-control checks describe the superseded UI.

The chatbot was subsequently switched to fully local rule-based analysis. Earlier API-specific verification notes describe the superseded integration. No chat request now uses an external provider.
