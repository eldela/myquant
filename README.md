# myquant

宏观经济数据 수집 시스템. FRED(미국), ECOS(한국), U.S. Treasury(미국 국채/부채)에서 경제 지표를 자동으로 가져와 단일 `macro.db` SQLite 데이터베이스에 통합 저장합니다. 이전 버전의 분리된 개별 데이터베이스 방식은 폐기되었고, `myquant.db` 패키지와 `macro_db.py` facade를 중심으로 한 통합 아키텍처로 재작성되었습니다.

## 데이터 소스

모든 데이터는 단일 SQLite 데이터베이스 `data/macro.db`에 저장됩니다.

| Source | Region | Series | DB |
|--------|--------|--------|----|
| [FRED](https://fred.stlouisfed.org/) | 🇺🇸 미국 | 19개 (금리, 물가, 환율, 주식, 고용, 통화) | `data/macro.db` |
| [ECOS](https://ecos.bok.or.kr/api/) | 🇰🇷 한국 | 9개 (물가, 금리, GDP, 무역, 심리) | `data/macro.db` |
| [Treasury Fiscal Data](https://fiscaldata.treasury.gov/) | 🇺🇸 미국 | 2개 (부채 추이, 국채 입찰) | `data/macro.db` |
| [pykrx](https://github.com/sharebook-kr/pykrx) | 🇰🇷 한국 | 5개 (코스피, 코스닥, KODEX, TIGER) | `data/macro.db` |
| [yfinance](https://github.com/ranaroussi/yfinance) | 🇺🇸 미국 | 10개 (S&P500, NASDAQ, ETF) | `data/macro.db` |

## 빠른 시작

```bash
cd src
source .venv/bin/activate

# .env 설정
echo "FRED_API=your_key" >> .env
echo "ECOS_API=your_key" >> .env
echo "KRX_ID=your_id" >> .env
echo "KRX_PW=your_pw" >> .env

# DB 초기화 (테이블 생성 + 28개 시리즈 등록)
python -m myquant.macro_db init

# 시장 데이터 초기화 (watchlist 15개 종목 등록)
python -m myquant.db init-market

# 전체 데이터 수집 (FRED + ECOS + Treasury)
python -m myquant.macro_db fetch-all

# 시장 데이터 수집 (한국 pykrx + 미국 yfinance)
python -m myquant.db fetch-market

# 갱신이 필요한 시리즈만 수집
python -m myquant.macro_db fetch-due

# 특정 소스만 수집
python -m myquant.macro_db fetch-all --source fred
python -m myquant.macro_db fetch-all --source ecos
python -m myquant.macro_db fetch-all --source treasury

# 국채 데이터 수집
python -m myquant.macro_db fetch-debt
python -m myquant.macro_db fetch-auctions

# 상태 확인
python -m myquant.macro_db status
```

## 주요 시리즈

### 🇺🇸 FRED (미국 경제)

| 카테고리 | 시리즈 | ID | 주기 | 단위 |
|----------|--------|----|------|------|
| 금리 | Federal Funds Effective Rate | FEDFUNDS | M | Percent |
| 금리 | 10-Year Treasury Constant Maturity Rate | DGS10 | D | Percent |
| 금리 | 2-Year Treasury Constant Maturity Rate | DGS2 | D | Percent |
| 금리 | Treasury Spread 10Y minus 2Y | T10Y2Y | D | Percent |
| 금리 | 10-Year Breakeven Inflation Rate | T10YIE | D | Percent |
| 금리 | ICE BofA US High Yield OAS | BAMLH0A0HYM2 | D | Percent |
| 물가 | CPI All Urban Consumers (SA) | CPIAUCSL | M | Index 1982-84=100 |
| 물가 | CPI Less Food and Energy (SA) | CPILFESL | M | Index 1982-84=100 |
| 환율 | Trade Weighted U.S. Dollar Index: Broad | DTWEXBGS | D | Index |
| 환율 | US Dollar to South Korean Won | DEXKOUS | D | KRW/USD |
| 원자재 | Gold Fixing Price (London AM) | GOLDAMGBD228NLBM | D | USD/Troy oz |
| 원자재 | WTI Crude Oil Spot Price | DCOILWTICO | D | USD/barrel |
| 성장 | Real Gross Domestic Product | GDPC1 | Q | Billions of 2017 USD |
| 고용 | Unemployment Rate | UNRATE | M | Percent |
| 고용 | All Employees, Total Nonfarm | PAYEMS | M | Thousands |
| 심리 | University of Michigan Consumer Sentiment | UMCSENT | M | Index 1966Q1=100 |
| 주식 | S&P 500 Index | SP500 | D | Index |
| 주식 | CBOE Volatility Index | VIXCLS | D | Index |
| 통화 | M2 Money Supply | M2SL | M | Billions of USD |

### 🇰🇷 ECOS (한국 경제)

| ID | 설명 | 주기 | 통계코드 | 품목코드 |
|----|------|------|----------|----------|
| 901Y009_0 | 소비자물가지수 총지수 | M | 901Y009 | 0 |
| 901Y009_A | 소비자물가지수 식료품 | M | 901Y009 | A |
| 722Y001_0101000 | 한국은행 기준금리 | M | 722Y001 | 0101000 |
| 200Y108_10601 | 실질국내총생산(GDP) | Q | 200Y108 | 10601 |
| 102Y004_ABA1 | 본원통화 M1 | M | 102Y004 | ABA1 |
| 901Y118_T002 | 수출금액 | M | 901Y118 | T002 |
| 901Y118_T004 | 수입금액 | M | 901Y118 | T004 |
| 511Y002_FMAA | 현재생활형편CSI | M | 511Y002 | FMAA |
| 513Y001_E1000 | 경제심리지수(원계열) | M | 513Y001 | E1000 |

### 🇺🇸 Treasury (미국 국채)

| 데이터셋 | 설명 | 주기 | 테이블 |
|----------|------|------|--------|
| Debt to the Penny | 미국 국채 잔액 추이 | 일간 | `debt` |
| Auctions | Bills/Notes/Bonds/TIPS/FRNs 입찰 결과 | 입찰 시 | `auctions` |

## CLI 레퍼런스

`python -m myquant.macro_db`가 권장하는 진입점입니다. 모든 명령은 기본적으로 `DEFAULT_DB_PATH` (`~/projects/myquant/data/macro.db`)를 사용하며, `--db-path`로 재정의할 수 있습니다.

| 명령 | 설명 | 옵션 |
|------|------|------|
| `init` | 데이터베이스와 6개 테이블을 생성하고 `series` 테이블에 28개 시리즈를 등록합니다. | `--db-path` |
| `fetch-all` | 선택한 소스의 모든 시리즈를 가져옵니다. | `--source {fred,ecos,treasury,all}`, `--db-path` |
| `fetch-due` | 갱신 주기에 따라 오늘 가져와야 할 시리즈만 가져옵니다. | `--source {fred,ecos,treasury,all}`, `--db-path` |
| `fetch-debt` | Treasury Debt to the Penny 데이터를 가져와 `debt` 테이블에 저장합니다. | `--db-path` |
| `fetch-auctions` | Treasury 국채 입찰 결과를 가져와 `auctions` 테이블에 저장합니다. | `--db-path` |
| `status` | 시리즈별 관측값 개수, 마지막 성공한 fetch 시각, 마지막 추가 row 수를 출력합니다. | `--db-path` |
| `migrate` | 레거시 DB의 데이터를 `macro.db`로 이전합니다. | `--source-dir`, `--db-path` |
| `init-market` | 시장 테이블을 생성하고 watchlist를 초기화합니다. | `--db-path` |
| `fetch-market` | watchlist의 모든 종목 가격 데이터를 수집합니다. | `--db-path` |
| `market-status` | 시장 모니터링 상태를 확인합니다. | `--db-path` |
| `market-history <symbol>` | 특정 종목의 가격 이력을 조회합니다. | `--db-path` |

### 갱신 일정

`fetch-due`는 각 시리즈의 `frequency`와 `source`를 기준으로 갱신 시점을 결정합니다.

- 일간(D): 매일 갱신
- 주간(W): 이번 주 월요일 이후 한 번
- 월간(M): 매월 1일부터 달력 기준 일자 이내에 한 번. FRED는 15일 이전까지, ECOS는 5일 이전까지 허용
- 분기(Q): 전 분기 종료 후 1~30일 사이에 한 번

## 데이터베이스 스키마

`myquant.db.core.SCHEMA`에 정의된 6개 테이블과 2개 인덱스로 구성됩니다.

### 1. `series`

FRED와 ECOS 시리즈 메타데이터를 통합 저장합니다.

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `id` | TEXT PRIMARY KEY | 시리즈 ID (예: `FEDFUNDS`, `901Y009_0`) |
| `title` | TEXT | 시리즈 설명 |
| `source` | TEXT NOT NULL | `'FRED'` 또는 `'ECOS'` |
| `frequency` | TEXT NOT NULL | `'D'`, `'W'`, `'M'`, `'Q'` 중 하나 |
| `cycle` | TEXT NOT NULL | ECOS 날짜 포맷 기준 `'D'`, `'W'`, `'M'`, `'Q'`, `'A'` |
| `units` | TEXT | 단위 |
| `observation_start` | DATE | 최초 관측 시작일 |
| `observation_end` | DATE | 마지막 관측 종료일 |
| `last_updated` | TEXT | 마지막으로 API에서 업데이트된 시점 |

### 2. `observations`

FRED와 ECOS의 시계열 데이터를 저장합니다.

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `series_id` | TEXT NOT NULL | 시리즈 ID (FK) |
| `date` | TEXT NOT NULL | ISO 8601 날짜 |
| `value` | REAL | 관측값 |
| `realtime_start` | TEXT | FRED 실시간 기간 시작 (ECOS는 NULL) |
| `realtime_end` | TEXT | FRED 실시간 기간 종료 (ECOS는 NULL) |

- PK: (`series_id`, `date`)
- 인덱스: `idx_observations_series_date`

### 3. `update_log`

FRED/ECOS 시리즈별 fetch 이력을 저장합니다.

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `id` | INTEGER PK AUTOINCREMENT | 로그 ID |
| `series_id` | TEXT NOT NULL | 시리즈 ID (FK) |
| `fetch_date` | TEXT NOT NULL | fetch 실행일 |
| `observation_start` | TEXT | 이번 fetch의 시작 관측일 |
| `observation_end` | TEXT | 이번 fetch의 종료 관측일 |
| `rows_added` | INTEGER | 추가된 row 수 |
| `status` | TEXT | `'ok'` 또는 에러 상태 |
| `message` | TEXT | 에러 메시지 등 |
| `updated_at` | TEXT | 로그 생성 시각 |

- 인덱스: `idx_update_log_series_fetch`

### 4. `debt`

Treasury Debt to the Penny 데이터.

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `record_date` | TEXT PRIMARY KEY | 기록일 |
| `debt_held_public_amt` | REAL | 일반인 보유 국채 잔액 |
| `intragov_hold_amt` | REAL | 정부 기관 보유 잔액 |
| `tot_pub_debt_out_amt` | REAL | 총 공공 부채 잔액 |

### 5. `auctions`

Treasury 국채 입찰 결과.

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `record_date` | TEXT | 기록일 |
| `cusip` | TEXT | CUSIP |
| `security_type` | TEXT | 종류 |
| `security_term` | TEXT | 만기 |
| `auction_date` | TEXT | 입찰일 |
| `issue_date` | TEXT | 발행일 |
| `maturity_date` | TEXT | 만기일 |
| `interest_rate` | REAL | 금리 |
| `average_price` | REAL | 평균 가격 |
| `bid_to_cover_ratio` | REAL | 입찰 경쟁률 |
| `total_accepted` | REAL | 총 낙찰액 |
| `competitive_accepted` | REAL | 경쟁 입찰 낙찰액 |

- PK: (`auction_date`, `cusip`)

### 6. `fetch_log`

Treasury 데이터셋별 fetch 이력.

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `id` | INTEGER PK AUTOINCREMENT | 로그 ID |
| `dataset` | TEXT NOT NULL | 데이터셋 이름 |
| `fetch_date` | TEXT NOT NULL | fetch 실행일 |
| `records_added` | INTEGER | 추가된 레코드 수 |
| `status` | TEXT | 상태 |
| `message` | TEXT | 메시지 |
| `updated_at` | TEXT | 로그 생성 시각 |

### 7. `market_prices`

한국/미국 지수 및 ETF 가격 데이터.

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `symbol` | TEXT NOT NULL | 종목 코드 (예: `KOSPI`, `SPY`) |
| `date` | TEXT NOT NULL | ISO 8601 날짜 |
| `open` | REAL | 시가 |
| `high` | REAL | 고가 |
| `low` | REAL | 저가 |
| `close` | REAL | 종가 |
| `volume` | INTEGER | 거래량 |
| `adj_close` | REAL | 수정 종가 |
| `source` | TEXT NOT NULL | `'pykrx'` 또는 `'yfinance'` |
| `asset_type` | TEXT NOT NULL | `'index'` 또는 `'etf'` |
| `name` | TEXT | 종목명 |

- PK: (`symbol`, `date`)
- 인덱스: `idx_market_prices_symbol_date`

### 8. `market_watchlist`

모니터링 대상 종목 목록.

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `symbol` | TEXT PRIMARY KEY | 종목 코드 |
| `name` | TEXT NOT NULL | 종목명 |
| `source` | TEXT NOT NULL | `'pykrx'` 또는 `'yfinance'` |
| `asset_type` | TEXT NOT NULL | `'index'` 또는 `'etf'` |
| `category` | TEXT | 카테고리 (`'market_cap'`, `'equal_weight'` 등) |
| `is_active` | INTEGER | 활성화 여부 (1=활성) |
| `added_date` | TEXT | 추가일 |
| `notes` | TEXT | 비고 |

### 9. `market_update_log`

시장 데이터 fetch 이력.

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `id` | INTEGER PK AUTOINCREMENT | 로그 ID |
| `symbol` | TEXT NOT NULL | 종목 코드 |
| `fetch_date` | TEXT NOT NULL | fetch 실행일 |
| `records_added` | INTEGER | 추가된 레코드 수 |
| `status` | TEXT | 상태 |
| `message` | TEXT | 메시지 |
| `updated_at` | TEXT | 로그 생성 시각 |

- 인덱스: `idx_market_update_log_symbol_fetch`

## 아키텍처

```
┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐
│    FRED API     │   │    ECOS API     │   │ Treasury Fiscal │
│   (HTTPS/key)   │   │   (HTTP/path)   │   │   (HTTPS/free)  │
└────────┬────────┘   └────────┬────────┘   └────────┬────────┘
         │                     │                     │
    ┌────▼────┐           ┌────▼────┐           ┌────▼────┐
    │ fred.py │           │ ecos.py │           │treasury │
    │ (client)│           │ (client)│           │(client) │
    └────┬────┘           └────┬────┘           └────┬────┘
         │                     │                     │
         └──────────┬──────────┴──────────┬──────────┘
                    │                     │
             ┌──────▼─────────────────────▼──────┐
             │           myquant.db                │
             │  ┌──────────────────────────────┐ │
             │  │         core.py              │ │
             │  │  CORE_SERIES, SCHEMA, fetch  │ │
             │  └──────────────────────────────┘ │
             │  ┌──────────────────────────────┐ │
             │  │        treasury.py           │ │
             │  │  debt/auctions/fetch_log     │ │
             │  └──────────────────────────────┘ │
             │  ┌──────────────────────────────┐ │
             │  │         cli.py               │ │
             │  │  init/fetch-all/fetch-due/...│ │
             │  └──────────────────────────────┘ │
             └────────────────┬────────────────────┘
                              │
                       ┌──────▼──────┐
                       │  macro.db   │
                       │  (SQLite)   │
                       └─────────────┘

┌────────────────────────────────────────────────────────────┐
│  myquant.macro_db.py (facade)                                │
│  myquant.db.*의 public API를 재export해서 하위 호환성 제공  │
└────────────────────────────────────────────────────────────┘
```

## 마이그레이션

기존에 별도로 운영하던 `fred.db`, `ecos.db`, `treasury.db`가 있다면, `migrate` 명령으로 `macro.db`로 한 번에 이전할 수 있습니다. 이 명령은 멱등성을 보장합니다. 두 번 실행해도 중복 row가 생기지 않습니다.

```bash
python -m myquant.macro_db migrate
```

- `series`, `observations`, `update_log`는 `fred.db`와 `ecos.db`에서 복사됩니다.
- `debt`, `auctions`, `fetch_log`는 `treasury.db`에서 복사됩니다.
- FRED와 ECOS의 시리즈 ID가 겹치면 마이그레이션이 중단됩니다.
- ECOS의 `realtime_start`/`realtime_end` 컬럼은 마이그레이션 중 NULL로 채워집니다.
- 기본적으로 `--db-path`와 같은 디렉터리에서 레거시 DB를 찾습니다. 다른 위치라면 `--source-dir`를 지정하세요.

## 레거시 모듈

`myquant/fred_db.py`, `myquant/ecos_db.py`, `myquant/treasury_db.py`는 더 이상 사용하지 않는 shim 모듈입니다. 이 모듈들은 `myquant.db`의 public API를 재export하면서 `DeprecationWarning`을 출력합니다. 새로운 코드는 다음 import 방식을 사용하세요.

```python
from myquant.db import fetch_all, fetch_due, init_db
from myquant.db import fetch_debt, fetch_auctions

# 또는 facade 모듈
from myquant.macro_db import fetch_all, init_db
```

`myquant/__init__.py`는 `__getattr__`을 통해 이러한 shim 이름을 lazy하게 로드합니다. 이 덕분에 `import myquant` 시점에 레거시 모듈이 즉시 로드되지 않아 `RuntimeWarning`이 발생하지 않습니다.

## 보안

- API 키와 인증 정보는 `.env` 파일에 저장하고 Git에 포함하지 마세요.
- `.env` 파일에 포함된 키:
  - `FRED_API` — FRED API 키
  - `ECOS_API` — ECOS API 키
  - `KRX_ID` — 한국거래소 로그인 ID
  - `KRX_PW` — 한국거래소 로그인 비밀번호
- 모든 모듈은 예외 메시지에서 API 키를 마스킹합니다.
- FRED 요청은 HTTPS와 SSL 인증서 검증을 사용합니다.
- ECOS는 공개 API가 HTTP만 지원합니다. URL path에 인증키가 포함되므로, 네트워크 트래픽이 노출될 가능성이 있습니다. 이는 ECOS API의 한계이며, 클라이언트 차원에서 해결할 수 없습니다.
- pykrx는 KRX 로그인 후 1시간 동안 유효합니다.

## 테스트

`pytest`로 55개 unit test를 실행할 수 있습니다.

```bash
pytest tests/test_macro_db.py -q
```

테스트는 `myquant.macro_db`의 schema, fetch, migration, CLI 동작을 검증합니다. 실제 API 호출은 `unittest.mock`으로 대체됩니다.

## 설치

```bash
# 저장소 클론
git clone git@github.com:eldela/myquant.git
cd myquant/src

# 가상환경 생성
python -m venv .venv
source .venv/bin/activate

# 의존성 설치
pip install -r requirements.txt

# 또는 uv 사용
uv venv .venv
source .venv/bin/activate
uv pip install -r requirements.txt

# .env 설정
echo "FRED_API=your_key" > .env
echo "ECOS_API=your_key" >> .env
```

필요한 Python 버전은 3.8 이상입니다. `pyproject.toml`에 정의된 의존성은 `pandas>=1.0`, `requests>=2.25`, `python-dotenv>=1.0`입니다.

## 라이선스

MIT
