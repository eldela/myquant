# HANDOFF.md — myquant project

**Last updated:** 2026-07-20

## What This Project Is

A personal macro-economic data collection system. Fetches financial/economic data from three government open APIs and stores everything in local SQLite databases for analysis.

**Repository:** https://github.com/eldela/myquant  
**Stack:** Python 3.12, pandas, requests, python-dotenv, sqlite3  
**Virtual env:** `~/projects/myquant/src/.venv`

## Directory Structure

```
myquant/
├── .Cowork/          ← This file
│   └── HANDOFF.md
├── context_backup/   ← API specs and OpenCode prompts (reference only)
├── data/             ← SQLite databases (git-ignored)
│   ├── fred.db
│   ├── ecos.db
│   └── treasury.db
└── src/              ← Main package (git repo)
    ├── .env          ← API keys (FRED_API, ECOS_API) — NEVER commit
    ├── .gitignore
    ├── pyproject.toml
    ├── requirements.txt
    └── myquant/
        ├── __init__.py
        ├── fred.py        ← FRED API client
        ├── fred_db.py     ← FRED SQLite layer + CLI
        ├── ecos.py        ← ECOS API client
        ├── ecos_db.py     ← ECOS SQLite layer + CLI
        ├── treasury.py    ← Treasury Fiscal Data client
        └── treasury_db.py ← Treasury SQLite layer + CLI
```

## Data Sources

### 1. FRED (Federal Reserve Economic Data)

- **API:** https://api.stlouisfed.org/fred/
- **Auth:** API key in query param (`api_key`)
- **Key:** Stored in `.env` as `FRED_API` or `FRED_API_KEY`
- **DB:** `data/fred.db`
- **CLI:** `python -m myquant.fred_db {init|fetch-all|fetch-due|status}`

18 core series (daily + monthly + quarterly):
- Interest rates: DGS10, DGS2, T10Y2Y, T10YIE, BAMLH0A0HYM2
- Inflation: CPIAUCSL, CPILFESL
- FX: DTWEXBGS (dollar index), DEXKOUS (KRW/USD)
- Commodities: DCOILWTICO (WTI crude)
- Market: SP500, VIXCLS
- Macro: GDPC1 (GDP), UNRATE, PAYEMS, UMCSENT, M2SL
- Note: GOLDAMGBD228NLBM was removed — FRED doesn't have gold spot prices

### 2. ECOS (Bank of Korea Economic Statistics)

- **API:** http://ecos.bok.or.kr/api (HTTP only, key in URL path)
- **Auth:** API key embedded in URL path
- **Key:** Stored in `.env` as `ECOS_API` or `ECOS_SERVICE_KEY`
- **DB:** `data/ecos.db`
- **CLI:** `python -m myquant.ecos_db {init|fetch-all|fetch-due|status}`

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
- **DB:** `data/treasury.db`
- **CLI:** `python -m myquant.treasury_db {init|fetch-debt|fetch-auctions|fetch-all|status}`

2 datasets:
- Debt to the Penny: ~8,300 rows (1993-present), daily U.S. public debt
- Treasury Auctions: ~2,900 rows (2020-present), Bills/Notes/Bonds/TIPS/FRNs

## fetch_due Logic

Each module has a `fetch_due()` that intelligently decides what to fetch:

| Source | Frequency | fetch_due window |
|--------|-----------|-----------------|
| FRED Daily | D | Every day |
| FRED Monthly | M | 1st–15th of month (CPI ~10th, unemployment ~1st Friday) |
| FRED Quarterly | Q | Within 30 days of quarter end |
| ECOS Monthly | M | 1st–5th of month |
| ECOS Quarterly | Q | Within 30 days of quarter end |
| Treasury | on-demand | Incremental (max stored date + 1) |

## How to Run

```bash
cd ~/projects/myquant/src
source .venv/bin/activate

# FRED
python -m myquant.fred_db fetch-due
python -m myquant.fred_db status

# ECOS
python -m myquant.ecos_db fetch-due
python -m myquant.ecos_db status

# Treasury
python -m myquant.treasury_db fetch-all
python -m myquant.treasury_db status
```

## Known Issues

1. **ECOS uses HTTP only** — API key is exposed in URL path. No HTTPS available from Bank of Korea.
2. **FRED rate limits** — 429 errors possible if fetching too many series rapidly. Add delays if needed.
3. **ECOS item codes** — Must be looked up via `StatisticItemList` before adding new series. Codes are not intuitive (e.g., "0101000" for base rate, "ABA1" for M1).
4. **Gold price** — Not available from FRED. Would need a separate API (e.g., goldapi.io).
5. **No automated scheduling yet** — `fetch_due()` exists but needs cron/launchd to run periodically.

## What to Do Next

- **Schedule periodic fetches:** Set up macOS launchd or cron to run `fetch-due` daily
- **Add gold price API:** goldapi.io or similar, store in a separate SQLite DB
- **Dashboard/analysis:** Build analysis scripts on top of the collected data
- **ECOS expansion:** Add more Korean series (found via StatisticTableList search)
