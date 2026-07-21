# HANDOFF.md — myquant project

**Last updated:** 2026-07-21

## What This Project Is

A personal macro-economic data collection system. Fetches financial/economic data from three government open APIs and stores everything in a **single unified SQLite database** (`macro.db`) for analysis.

**Repository:** https://github.com/eldela/myquant
**Stack:** Python 3.10+, pandas, requests, python-dotenv, sqlite3
**Virtual env:** `~/projects/myquant/src/.venv`

## Recent Major Changes

### 2026-07-21 — Daily normalization layer

Added a unified daily-frequency normalization layer on top of the existing macro and market data.

**What changed:**
- New module: `myquant/db/normalization.py`
- New table: `normalized_daily` with indexes `idx_normalized_daily_series_date` and `idx_normalized_daily_date`
- Resamples macro series (`observations`) and market prices (`market_prices`) to daily frequency
- FRED/ECOS macro series get `asset_type='macro'`; market symbols keep their `index`/`etf` type
- New CLI commands: `init-normalization`, `normalize`, `normalized-status`
- New tests: `tests/test_normalization.py` (13 tests)

### 2026-07-20 — Unified database architecture

The three previously separate database modules (`fred_db.py`, `ecos_db.py`, `treasury_db.py`) have been **unified** into a single `myquant.db` package backed by one `macro.db` file. The old modules remain as **deprecated shims** that delegate to the new unified module.

**What changed:**
- `fred.db`, `ecos.db`, `treasury.db` → single `macro.db`
- `fred_db.py`, `ecos_db.py`, `treasury_db.py` → deprecated shims (emit `DeprecationWarning`)
- New unified module: `myquant/db/` package + `myquant/macro_db.py` facade
- New unified CLI: `python -m myquant.macro_db`
- Legacy data can be migrated via `python -m myquant.macro_db migrate`

## Directory Structure

```
myquant/
├── .Cowork/
│   └── HANDOFF.md          ← This file
├── data/                    ← SQLite databases (git-ignored)
│   ├── macro.db             ← Unified database (NEW)
│   ├── fred.db              ← Legacy (migrate to macro.db)
│   ├── ecos.db              ← Legacy (migrate to macro.db)
│   └── treasury.db          ← Legacy (migrate to macro.db)
└── src/                     ← Main package (git repo)
    ├── .env                 ← API keys (FRED_API, ECOS_API, KRX_ID, KRX_PW) — NEVER commit
    ├── .gitignore
    ├── pyproject.toml
    ├── requirements.txt
    ├── tests/
    │   ├── test_macro_db.py    ← 55 unit tests
    │   └── test_normalization.py ← 13 normalization tests (NEW)
    └── myquant/
        ├── __init__.py      ← Lazy imports for deprecated shims
        ├── fred.py          ← FRED API client (unchanged)
        ├── ecos.py          ← ECOS API client (unchanged)
        ├── treasury.py      ← Treasury API client (unchanged)
        ├── fred_db.py       ← DEPRECATED shim → macro_db
        ├── ecos_db.py       ← DEPRECATED shim → macro_db
        ├── treasury_db.py   ← DEPRECATED shim → macro_db
        ├── macro_db.py      ← Facade re-exporting from myquant.db
        └── db/              ← Unified database package
            ├── __init__.py  ← Re-exports all public names
            ├── core.py      ← Helpers, schema, CORE_SERIES, init_db, fetch/query API
            ├── fred.py      ← FRED-specific fetch logic
            ├── ecos.py      ← ECOS-specific fetch logic
            ├── treasury.py  ← Treasury fetch/query functions
            ├── migration.py ← Legacy DB → macro.db migration
            ├── cli.py       ← CLI entry point (_main, _status)
            └── normalization.py ← Daily normalization (NEW)
```

## Data Sources

### 1. FRED (Federal Reserve Economic Data)

- **API:** https://api.stlouisfed.org/fred/
- **Auth:** API key in query param (`api_key`)
- **Key:** Stored in `.env` as `FRED_API` or `FRED_API_KEY`
- **DB table:** `series` (source='FRED'), `observations`, `update_log`

19 core series (daily + monthly + quarterly):
- Interest rates: FEDFUNDS, DGS10, DGS2, T10Y2Y, T10YIE, BAMLH0A0HYM2
- Inflation: CPIAUCSL, CPILFESL
- FX: DTWEXBGS (dollar index), DEXKOUS (KRW/USD)
- Commodities: GOLDAMGBD228NLBM (gold), DCOILWTICO (WTI crude)
- Market: SP500, VIXCLS
- Macro: GDPC1 (GDP), UNRATE, PAYEMS, UMCSENT, M2SL

### 2. ECOS (Bank of Korea Economic Statistics)

- **API:** http://ecos.bok.or.kr/api (HTTP only, key in URL path)
- **Auth:** API key embedded in URL path
- **Key:** Stored in `.env` as `ECOS_API` or `ECOS_SERVICE_KEY`
- **DB table:** `series` (source='ECOS'), `observations`, `update_log`

9 core series (monthly + quarterly):
- 901Y009_0: 소비자물가지수 총지수
- 901Y009_A: 소비자물가지수 식료품
- 722Y001_0101000: 한국은행 기준금리
- 200Y108_10601: 실질국내총생산(GDP)
- 102Y004_ABA1: 본원통화 M1
- 901Y118_T002: 수출금액
- 901Y118_T004: 수입금액
- 511Y002_FMAA: 현재생활형편CSI
- 513Y001_E1000: 경제심리지수

### 3. Treasury Fiscal Data (U.S. Treasury)

- **API:** https://api.fiscaldata.treasury.gov/services/api/fiscal_service/
- **Auth:** None required (fully public)
- **DB tables:** `debt`, `auctions`, `fetch_log` (separate from series schema)

2 datasets:
- Debt to the Penny: ~8,300 rows (1993-present), daily U.S. public debt
- Treasury Auctions: ~2,900 rows (2020-present), Bills/Notes/Bonds/TIPS/FRNs

## Unified Database Schema (macro.db)

```
series              — FRED + ECOS metadata (id, title, source, frequency, cycle, units, ...)
observations        — Time-series data points (series_id, date, value, realtime_start, realtime_end)
update_log          — Fetch history for series-based data
debt                — Treasury Debt to the Penny (record_date, amounts)
auctions            — Treasury auction results (auction_date, cusip, rates, amounts)
fetch_log           — Treasury fetch history
market_prices       — Daily OHLCV/adjusted close for watchlist symbols
market_watchlist    — Symbols to monitor
market_update_log   — Market fetch history
normalized_daily    — Unified daily-frequency view of macro + market data (NEW)
```

Key design decisions:
- `source` column in `series` table: 'FRED' or 'ECOS'
- `cycle` column in `series` table: 'D', 'W', 'M', 'Q', 'A' (for ECOS date formatting)
- Treasury tables are separate (not series-shaped data)
- ECOS `realtime_start`/`realtime_end` are set to NULL during migration (ECOS has no realtime metadata)
- `normalized_daily` is derived from `observations` and `market_prices`; use `normalize` CLI to refresh
- `normalized_daily.source` check constraint: 'FRED', 'ECOS', 'pykrx', 'yfinance'
- `normalized_daily.asset_type` check constraint: 'macro', 'index', 'etf'

## fetch_due Logic

The unified `fetch_due()` preserves source-specific scheduling:

| Source | Frequency | fetch_due window |
|--------|-----------|-----------------|
| FRED Daily | D | Every day |
| FRED Monthly | M | 1st–15th of month (CPI ~10th, unemployment ~1st Friday) |
| FRED Quarterly | Q | Within 30 days of quarter end |
| ECOS Monthly | M | 1st–5th of month |
| ECOS Quarterly | Q | Within 30 days of quarter end |
| Treasury | on-demand | Incremental (max stored date + 1) |

**Important:** FRED and ECOS have different monthly due-day thresholds (15 vs 5). This is preserved in the unified module.

## CLI Commands

```bash
cd ~/projects/myquant/src
source .venv/bin/activate

# Initialize database (create tables + seed 28 series)
python -m myquant.macro_db init

# Initialize market tables and watchlist
python -m myquant.macro_db init-market

# Initialize normalized_daily table
python -m myquant.macro_db init-normalization

# Fetch all data (FRED + ECOS + Treasury)
python -m myquant.macro_db fetch-all

# Fetch market data
python -m myquant.macro_db fetch-market

# Normalize all data to daily frequency
python -m myquant.macro_db normalize

# Normalize a single series or symbol
python -m myquant.macro_db normalize --series DGS10

# Show normalization status
python -m myquant.macro_db normalized-status

# Fetch only due series (respects frequency scheduling)
python -m myquant.macro_db fetch-due
python -m myquant.macro_db fetch-due --source fred

# Treasury-specific commands
python -m myquant.macro_db fetch-debt
python -m myquant.macro_db fetch-auctions

# Show database status
python -m myquant.macro_db status

# Migrate legacy databases
python -m myquant.macro_db migrate

# Custom DB path
python -m myquant.macro_db init --db-path /path/to/custom.db
```

## Migration from Legacy Databases

If you have existing `fred.db`, `ecos.db`, `treasury.db` files:

```bash
python -m myquant.macro_db migrate --source-dir ~/projects/myquant/data
```

Migration is **idempotent** — running twice produces no duplicate rows. It:
1. Checks for ID collisions between FRED and ECOS
2. Copies series, observations, update_log from fred.db and ecos.db
3. Copies debt, auctions, fetch_log from treasury.db
4. Sets ECOS `realtime_start`/`realtime_end` to NULL (no realtime metadata)

## Known Issues

1. **ECOS uses HTTP only** — API key is exposed in URL path. No HTTPS available from Bank of Korea.
2. **FRED rate limits** — 429 errors possible if fetching too many series rapidly. Add delays if needed.
3. **ECOS item codes** — Must be looked up via `StatisticItemList` before adding new series. Codes are not intuitive (e.g., "0101000" for base rate, "ABA1" for M1).
4. **No automated scheduling yet** — `fetch_due()` exists but needs cron/launchd to run periodically.

## Current Status

- [x] Unified DB architecture with single `macro.db`
- [x] FRED/ECOS/Treasury fetch and storage
- [x] Market data (pykrx/yfinance) fetch and storage
- [x] Daily normalization layer (`normalized_daily`)
- [ ] Automated scheduling for periodic fetches
- [ ] Dashboard/analysis scripts

## What to Do Next

- **Schedule periodic fetches:** Set up macOS launchd or cron to run `python -m myquant.macro_db fetch-due` daily
- **Refresh normalization:** Run `python -m myquant.macro_db normalize` after each fetch cycle
- **Add gold price API:** goldapi.io or similar, store in macro.db
- **Dashboard/analysis:** Build analysis scripts on top of `normalized_daily`
- **ECOS expansion:** Add more Korean series (found via StatisticTableList search)
- **Remove deprecated shims:** Once all external scripts are updated to use `myquant.macro_db`, remove `fred_db.py`, `ecos_db.py`, `treasury_db.py`

## Test Suite

```bash
cd ~/projects/myquant/src
source .venv/bin/activate
pytest tests/ -q
```

68 tests covering:
- Schema creation and validation (10 tests)
- FRED fetch with mocked API (6 tests)
- ECOS fetch with mocked API (7 tests)
- Treasury fetch with mocked API (5 tests)
- Migration idempotency (5 tests)
- CLI commands (10 tests)
- Query functions and fetch window resolution (5 tests)
- Normalization resampling and integration (7 tests)
- Normalization table/query helpers (6 tests)
