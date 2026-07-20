# myquant

宏观经济数据 수집 시스템. FRED(미국), ECOS(한국), U.S. Treasury(미국 국채/부채)에서 경제 지표를 자동으로 가져와 SQLite에 저장합니다.

## 데이터 소스

| Source | Region | Series | DB |
|--------|--------|--------|----|
| [FRED](https://fred.stlouisfed.org/) | 🇺🇸 미국 | 18개 (금리, 물가, 환율, 주식, 고용) | `data/fred.db` |
| [ECOS](https://ecos.bok.or.kr/api/) | 🇰🇷 한국 | 9개 (물가, 금리, GDP, 무역, 심리) | `data/ecos.db` |
| [Treasury Fiscal Data](https://fiscaldata.treasury.gov/) | 🇺🇸 미국 | 2개 (부채 추이, 국채 입찰) | `data/treasury.db` |

## 빠른 시작

```bash
cd src
source .venv/bin/activate

# .env 설정
echo "FRED_API=your_key" >> .env
echo "ECOS_API=your_key" >> .env

# 데이터 수집
python -m myquant.fred_db fetch-all
python -m myquant.ecos_db fetch-all
python -m myquant.treasury_db fetch-all

# 상태 확인
python -m myquant.fred_db status
python -m myquant.ecos_db status
python -m myquant.treasury_db status
```

## 주요 시리즈

### 🇺🇸 FRED (미국 경제)

| 카테고리 | 시리즈 | 주기 |
|----------|--------|------|
| 금리 | DGS10, DGS2, T10Y2Y, T10YIE, BAMLH0A0HYM2 | 일간 |
| 물가 | CPIAUCSL, CPILFESL | 월간 |
| 환율 | DTWEXBGS (달러인덱스), DEXKOUS (원/달러) | 일간 |
| 원자재 | DCOILWTICO (WTI 원유) | 일간 |
| 주식 | SP500, VIXCLS | 일간 |
| 성장 | GDPC1 (실질GDP) | 분기 |
| 고용 | UNRATE, PAYEMS | 월간 |
| 심리 | UMCSENT | 월간 |
| 통화 | M2SL | 월간 |

### 🇰🇷 ECOS (한국 경제)

| 시리즈 | 설명 | 주기 |
|--------|------|------|
| 901Y009 | 소비자물가지수 | 월간 |
| 722Y001 | 한국은행 기준금리 | 월간 |
| 200Y108 | 실질 GDP | 분기 |
| 102Y004 | 본원통화 M1 | 월간 |
| 901Y118 | 수출/수입금액 | 월간 |
| 511Y002 | 소비자심리 CSI | 월간 |
| 513Y001 | 경제심리지수 | 월간 |

### 🇺🇸 Treasury (미국 국채)

| 데이터셋 | 설명 | 주기 |
|----------|------|------|
| Debt to the Penny | 미국 국채 잔액 추이 (~$39.5T) | 일간 |
| Auctions | Bills/Notes/Bonds/TIPS/FRNs 입찰 | 입찰 시 |

## 아키텍처

```
┌─────────────┐   ┌─────────────┐   ┌─────────────┐
│  FRED API   │   │  ECOS API   │   │  Treasury   │
│ (HTTPS/key) │   │ (HTTP/path) │   │ (HTTPS/free)│
└──────┬──────┘   └──────┬──────┘   └──────┬──────┘
       │                 │                 │
  ┌────▼────┐      ┌────▼────┐      ┌────▼────┐
  │ fred.py │      │ ecos.py │      │treasury │
  └────┬────┘      └────┬────┘      └────┬────┘
       │                │                │
  ┌────▼─────┐     ┌────▼─────┐     ┌────▼─────┐
  │fred_db.py│     │ecos_db.py│     │treasury_ │
  │  SQLite  │     │  SQLite  │     │  db.py   │
  └────┬─────┘     └────┬─────┘     └────┬─────┘
       │                │                │
       ▼                ▼                ▼
    fred.db          ecos.db         treasury.db
```

## 보안

- API 키는 `.env` 파일에 저장 (git 제외)
- 모든 모듈에서 API 키를 예외 메시지에서 마스킹
- SSL 인증서 검증 활성화 (FRED)
- ECOS는 HTTP만 지원 — URL path에 키 노출 불가피

## 설치

```bash
# 클론
git clone git@github.com:eldela/myquant.git
cd myquant/src

# 가상환경
uv venv .venv
source .venv/bin/activate
uv pip install -r requirements.txt

# .env 설정
echo "FRED_API=your_key" > .env
echo "ECOS_API=your_key" >> .env
```

## 라이선스

MIT
