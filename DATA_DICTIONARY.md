### 입력 규칙

- `code`: 6자리 종목코드(문자열). 산업 공통 지표는 `000000`.
- `date`, `period_end`, `published_at`: `YYYY-MM-DD`. 발표일은 투자자가 알 수 있었던 날짜. 모르면 확인일 사용.
- `source`: 출처 이름 필수. `retrieved_at`: ISO 수집 시각. `status`: `reported`, `reviewed`, `user`, `synthetic` 등.
- 금액은 원(KRW), 주식 수는 주, 비율은 % 포인트(15%는 15). 결측은 빈칸. 금액을 0으로 채우지 않음.
- 같은 키 자료는 나중에 병합한 자료로 갱신. 재무는 공시일이 다르면 버전 보존.

### 데이터 종류

| 종류 | 주요 필드 | 목적 |
|---|---|---|
| prices | date, open, high, low, close, adjusted_close, volume, turnover, market_cap, shares | 일별 가격. adjusted_close는 기업행사가 반영된 수정주가가 확보된 경우만 입력 |
| financials | period_end, period_type, basis, revenue, operating_profit, parent_net_income, parent_equity, cfo, capex 등 | 단독 분기 Q 또는 연간 FY. 연결 CFS / 별도 OFS |
| flows | foreign_net, institution_net, retail_net, pension_net, foreign_ownership, short_balance, credit_balance, loan_balance | 순매수는 원, 보유비율은 %, 각 잔고는 주. 기관과 연기금은 합산 금지 |
| operating | date, metric, value, unit, note | 수주·가동률·고객 투자·메모리 가격. 단위가 다르면 별도 차트 |
| exposure | product, process, item, customer, revenue_pct, supply_status, evidence_url, verified_at | 개발/평가/양산 등 실제 공급 근거. 공정 용도 태그와 구분 |
| estimates | period_end, metric, value, unit, provider, published_at | 예상실적. 자체 가정과 컨센서스 구분 |
| events | date, category, title, url, note | 실적 발표, 계약, 정정, 증자, 전환사채, 소송, 자사주 등 |
| notes | date, thesis, risk, review_date, watch | 개인 투자 논리. watch는 True/False |

### 재무 계정

`revenue`: 매출, `gross_profit`: 매출총이익, `operating_profit`: 영업이익,
`net_income`: 전체 순이익, `parent_net_income`: 지배주주 순이익,
`equity`: 전체 자본, `parent_equity`: 지배주주 지분, `assets`: 자산,
`liabilities`: 부채, `current_assets`: 유동자산, `current_liabilities`: 유동부채,
`debt`: 이자부 차입금(리스부채 포함 여부를 source에 기록), `cash`: 현금및현금성자산,
`interest_expense`: 이자비용, `cfo`: 영업현금흐름,
`capex`: 유형·무형자산 취득 **현금지출의 양수 합계**,
`inventory`: 재고, `receivables`: 매출채권, `cogs`: 매출원가,
`rd`: 연구개발비, `dividend`: 현금배당총액, `shares`: 발행주식 수.

누적 현금흐름은 차감해 단독 분기로 변환 후 입력합니다. 재무상태표 잔액은 차감하지 않습니다.
12월 결산 기준 캘린더 분기 TTM을 지원합니다. 비12월 결산은 FY 자료를 사용하세요.
TTM은 연속 4분기, ROE는 1년 전·현재 지배주주 지분 평균이 있어야 계산됩니다.
PER은 시가총액 / 지배주주 순이익, PBR은 시가총액 / 지배주주 지분입니다.
우선주 등 복수 종류주식으로 분모·시가총액 범위가 다를 수 있는 기업은 별도 조정이 필요합니다.
`ebitda`: 검증된 EBITDA, `noncontrolling_interest`: 비지배지분, `preferred_value`: 보통주 시가총액에 미포함된 우선주 가치. EV = 시가총액 + 순차입금 + 비지배지분 + 우선주 가치. 해당 항목이 없음을 확인한 경우만 0을 입력하세요. 원자료가 없으면 EV/EBITDA는 비웁니다. ROIC·컨센서스 자동 수집은 제공하지 않습니다.

### 데이터 품질

모의 API는 시장 분석 일부 항목을 지원하지 않을 수 있습니다. 실패는 결측으로 유지합니다.
공공데이터와 KRX 일별 시세의 원주가를 수정주가로 간주하지 않습니다.
수정주가 미확보 시 기술적 수익률·백테스트는 비활성화되지만 원주가 차트는 표시합니다.
백테스트는 현재 선택 기업·공통 거래일만 사용하므로 생존편향과 거래정지 누락 가능성이 있습니다.

### 저장과 개인정보

분석 데이터는 브라우저 세션에서 유지됩니다. ZIP 내보내기/가져오기로 보존합니다.
계좌 잔고·API 키·토큰은 ZIP과 GitHub에 포함하지 않습니다. 전역 Streamlit 캐시에 보관하지 않습니다.
