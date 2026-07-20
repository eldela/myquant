# AGENTS.md — myquant 프로젝트 AI 에이전트 지침

이 문서는 OpenCode, Hermes Agent 등 AI 코딩 에이전트가 이 프로젝트에서 작업할 때 따라야 할 지침입니다.

## 프로젝트 구조

```
~/projects/myquant/
├── src/
│   ├── myquant/
│   │   ├── db/
│   │   │   ├── core.py          # 공통 SQLite, FRED/ECOS fetch
│   │   │   ├── fred.py          # FRED 시리즈 정의
│   │   │   ├── ecos.py          # ECOS 시리즈 정의
│   │   │   ├── treasury.py      # Treasury fetch
│   │   │   ├── market.py        # 시장 데이터 (pykrx/yfinance)
│   │   │   ├── cli.py           # CLI 명령어
│   │   │   └── migration.py     # 레거시 DB 마이그레이션
│   │   ├── fred.py              # FRED HTTP 클라이언트
│   │   ├── ecos.py              # ECOS HTTP 클라이언트
│   │   ├── treasury.py          # Treasury 클라이언트
│   │   ├── market.py            # pykrx/yfinance 클라이언트
│   │   └── macro_db.py          # facade (하위 호환)
│   ├── tests/
│   │   └── test_macro_db.py     # 기존 테스트 55개
│   ├── .env                     # API 키 (FRED_API, ECOS_API, KRX_ID, KRX_PW)
│   ├── .venv/                   # Python 3.12 가상환경
│   ├── pyproject.toml
│   └── requirements.txt
├── data/
│   └── macro.db                 # SQLite 데이터베이스
├── .Cowork/
│   └── HANDOFF.md               # 세션 간 작업 인수인계 문서
└── AGENTS.md                    # 이 문서
```

## 환경 설정

- **Python**: 3.12 (uv + venv)
- **의존성**: pandas, requests, python-dotenv, pykrx, yfinance
- **가상환경 활성화**: `cd ~/projects/myquant/src && source .venv/bin/activate`
- **실행**: `python -m myquant.db <command>` 또는 `python -m myquant.macro_db <command>`

## API 키 (.env)

```
FRED_API=...          # FRED API 키
ECOS_API=...          # ECOS API 키
KRX_ID=...            # 한국거래소 로그인 ID
KRX_PW=...            # 한국거래소 로그인 비밀번호
```

⚠️ `.env` 파일은 Git에 포함하지 마세요.

## 데이터 소스

| 소스 | 리전 | 모듈 | 비고 |
|------|------|------|------|
| FRED | 🇺🇸 미국 | `fred.py` | HTTPS, API 키 필수 |
| ECOS | 🇰🇷 한국 | `ecos.py` | HTTP only, URL path에 키 노출 |
| Treasury | 🇺🇸 미국 | `treasury.py` | 인증 불필요 |
| pykrx | 🇰🇷 한국 | `market.py` | KRX 로그인 필요 (1시간 유효) |
| yfinance | 🇺🇸 미국 | `market.py` | 인증 불필요 |

## CLI 명령어

```bash
# 매크로 데이터
python -m myquant.db init              # DB 초기화
python -m myquant.db fetch-all         # 전체 수집
python -m myquant.db fetch-due         # 갱신 필요분만
python -m myquant.db status            # 상태 확인

# 시장 데이터
python -m myquant.db init-market       # 시장 테이블 초기화
python -m myquant.db fetch-market      # 시장 데이터 수집
python -m myquant.db market-status     # 시장 상태 확인
python -m myquant.db market-history <symbol>  # 가격 이력
```

## 작업 마무리 순서 (필수)

AI 에이전트가 코딩 작업을 완료한 후 다음 순서로 마무리하세요:

### 1. 코드 테스트
```bash
cd ~/projects/myquant/src && source .venv/bin/activate
pytest tests/test_macro_db.py -q      # 기존 테스트
python -m myquant.db init-market      # 시장 테이블 확인
python -m myquant.db fetch-market     # 시장 데이터 수집 테스트
python -m myquant.db market-status    # 상태 확인
```

### 2. README.md 업데이트
- 변경된 기능, 명령어, 스키마를 README.md에 반영
- 새로운 CLI 명령어가 있으면 "CLI 레퍼런스" 섹션에 추가
- 새로운 테이블이 있으면 "데이터베이스 스키마" 섹션에 추가
- .env에 새로운 키가 필요하면 "보안" 섹션에 추가

### 3. HANDOFF.md 업데이트
- `.Cowork/HANDOFF.md`를 최신 상태로 갱신
- 완료된 작업, 현재 상태, 남은 작업을 명시
- 주의사항 및 아키텍처 변경사항 포함

## 세션 핸드오프

작업 세션 간 인수인계는 `.Cowork/HANDOFF.md`에 저장합니다.

```markdown
# HANDOFF — myquant

**Created:** YYYY-MM-DD
**Last session:** <작업 요약>

## 현재 상태
- 완료된 것
- 남은 것

## 아키텍처 요약
<변경사항 반영>

## 사용법
<최신 CLI 명령어>

## 주의사항
<발견한 이슈, 팁>
```

## 주의사항

1. **pykrx는 KRX 로그인 필요** — `.env`에 `KRX_ID`, `KRX_PW` 설정 필수
2. **pykrx 로그인 만료** — 1시간 후 만료, 재로그인 필요
3. **ECOS는 HTTP만 지원** — API 키가 URL path에 노출됨
4. **FRED timezone 차이** — `realtime_start`/`realtime_end` 파라미터 사용 금지
5. **테스트 실행** — `pytest tests/test_macro_db.py -q` (55개)
6. **DB 위치** — `~/projects/myquant/data/macro.db`

## 코딩 컨벤션

- Python 3.12+ 사용
- 타입 힌트 사용
- docstring 포함 (Google 스타일)
- 에러 처리: 예외 메시지에서 API 키 마스킹
- 새 모듈: `myquant/db/`에 추가, `__init__.py`에 export
- 새 테이블: `SCHEMA` 문자열에 추가, init 함수에서 생성
