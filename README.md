# 이종완의 반도체 소부장 투자 대시보드 · 2.0

KRX와 한국투자증권(KIS) 모의투자 API만 사용하는 개인용 Streamlit 앱입니다. 화면을 열면 실제 API를 자동 조회합니다. 공공데이터포털, OpenDART, 스크래핑, CSV 업로드, 합성 데이터는 사용하지 않습니다.

## 배포

- 저장소: `jwsslee/mpe_jwlee`, 브랜치: `main`, 실행 파일: `app.py`
- Python **3.12**. requirements.txt는 검증 환경 버전으로 고정했습니다.
- Streamlit Secrets에 `secrets.example.toml` 구조로 실제 값을 입력합니다. 기존 `[kis]`, `[krx]` 설정 및 최상위 `KIS_APP_KEY`, `KIS_APP_SECRET`, `KIS_CANO`, `KIS_ACNT_PRDT_CD`, `KRX_API_KEY`도 읽습니다.
- `APP_PASSWORD`는 첫 `[섹션]`보다 위에 설정합니다. 앱 로그인에 필요합니다.
- 모의계좌 앞 8자리·뒤 2자리 모두 문자열로 입력합니다. `12345678-01` 형태의 전체 계좌번호도 분리해 읽습니다.
- 기존 공공데이터 관련 Secrets는 읽지 않습니다. 삭제해도 됩니다.
- 코드 교체 후 Reboot하고 로그인하면 자동 수집합니다. 앱 사이드바의 **새 버전 2.0** 표시로 확인합니다.

```bash
pip install -r requirements.txt
streamlit run app.py
```

## 화면과 데이터

| 화면 | 자동 조회 | 표시 내용 |
|---|---|---|
| 시장·관심기업 | KIS 현재가 (기업 상세와 캐시 공유) | 가격·전일 대비 등락률·거래량·거래대금·시가총액 |
| 시장·관심기업 참고표 | KRX KOSPI/KOSDAQ 최근 일별매매정보 | KIS와 별도 표로 기준일·종가·일별 등락률 표시 |
| 기업 상세 | KIS 현재가·일별주가·투자자 | PER/PBR/EPS/BPS, 외국인 소진율, 최근 1년 수정주가, 순매수 수량 |
| 모의투자 계좌 | KIS 전체 잔고 연속조회 | 총평가금액·평가손익·예수금·종목별 비중 |
| 연결 진단 | 세션에 기록된 조회 결과 | 설정 항목 인식 위치·성공 시각·실패 이유 |

관심목록의 이름·종목코드는 선택을 위한 초기 설정이며 API 수집 데이터는 아닙니다. 목록은 상장 상태나 반도체 공급관계를 보증하지 않습니다. 기본 12개이며 선택 항목을 늘릴 수 있습니다. KIS는 관심종목별로 순차 조회하므로 많은 종목은 시간이 걸립니다. 첫 실패에서 일괄 KIS 요청을 중단하고 그 사유를 표시합니다.

재무제표, 수주, 고객 비중, 컨센서스, 재무 기반 백테스트는 이 버전에 없습니다. KIS 응답의 가치지표만 표시하며 재무 기준기간·연결 여부를 임의로 추정하지 않습니다. 공란을 가상 값이나 0으로 채우지 않습니다.

## 자동 갱신과 장애 처리

- 화면 진입 즉시 조회합니다. 자동 갱신을 켜면 열린 화면을 60초마다 확인합니다.
- KRX 15분, KIS 현재가·잔고 60초, 일별주가 1시간, 투자자 수급 15분 캐시입니다. 실패는 2분간 반복 요청하지 않습니다.
- KRX 인증키 승인과 **유가증권 일별매매정보 / 코스닥 일별매매정보 각각의 이용 승인**이 필요합니다. 두 시장을 독립적으로 조회합니다.
- KRX 최근 12일을 거슬러 최신 제공 자료를 확인합니다. 401/403 같은 인증 실패에는 날짜를 바꿔 반복하지 않습니다.
- KIS는 모의 호스트 `openapivts.koreainvestment.com:29443`로 고정됩니다. 실전 주문·모의 주문 기능은 없습니다.
- KIS 일별주가는 요청당 100건 제한에 맞춰 90일 이하의 달력 구간으로 나누어 조회합니다. 한 구간 실패 시 불완전한 이력으로 교체하지 않습니다.
- 잔고는 연속조회가 끝난 경우만 표시합니다. 요약 합계는 페이지별로 합산하지 않습니다.
- 실패 시 이전 성공 결과를 유지하고 실패 사실과 원래 수집시각을 표시합니다. 재접속·서버 재시작 시 세션 캐시가 지워지며 다시 수집합니다.
- 실시간 스트리밍이 아니라 REST 조회 시점 자료입니다. KRX 종가와 KIS 현재가는 기준이 다를 수 있습니다.
- 모의계좌 응답·토큰·키는 세션 메모리에만 저장합니다. 공유 캐시와 파일에는 저장하지 않습니다. 같은 키의 여러 세션에서 동시 로그인하면 토큰 발급 제한이 발생할 수 있습니다.

## 확인한 공식 명세

- [KRX 유가증권 일별매매정보](https://openapi.krx.co.kr/contents/OPP/USES/service/OPPUSES002_S2.cmd?BO_ID=JvJFzlAENzZlPBDNGAWC)
- [KRX 이용 승인 절차](https://openapi.krx.co.kr/contents/OPP/INFO/OPPINFO003.jsp)
- [KIS 현재가](https://github.com/koreainvestment/open-trading-api/tree/main/examples_llm/domestic_stock/inquire_price)
- [KIS 일별주가](https://github.com/koreainvestment/open-trading-api/tree/main/examples_llm/domestic_stock/inquire_daily_itemchartprice)
- [KIS 투자자 수급](https://github.com/koreainvestment/open-trading-api/tree/main/examples_llm/domestic_stock/inquire_investor)
- [KIS 잔고](https://github.com/koreainvestment/open-trading-api/tree/main/examples_llm/domestic_stock/inquire_balance)

## 검증

```bash
pip install pytest
python -m pytest -q
```

설정 해석, 인증 전 API 차단, 최초 화면 자동 수집, 캐시 재사용, KRX 실패 시 KIS 표시, 가격 단위, 토큰 재사용, 주가 이력 분할, 투자자 수량, 잔고 연속조회·부분 실패, 오류 정보 비노출과 전체 화면 동작을 테스트합니다. **테스트 응답 기반 검증이며 실제 사용자 키의 인증 성공을 보장하지 않습니다.** 개발 환경에서는 Streamlit Cloud Secrets를 읽을 수 없어 실제 키 연결은 배포 환경에서 확인해야 합니다.

2026-10-02 재구축 검증: Python 3.12.14 및 requirements.txt 버전에서 **16개 테스트 통과**. 테스트 중 외부 실제 API는 호출하지 않았습니다. 실제 계정 연결이 성공한 것으로 기록하지 않습니다.


## 2.1 기업 정보표

이전 버전의 72개 기업 참고 목록을 `data/companies.csv`로 복원했습니다. 사이드바 **기업 정보표**에서 기업명·종목코드·주력제품 검색 및 공정·소부장·적용제품·유사제품 비교군 필터를 사용할 수 있습니다. 기업 상세에도 해당 기업의 분류표가 표시됩니다.

이 표는 이전 조사 자료이며 KRX/KIS API에서 자동 생성한 자료가 아닙니다. 최신 상장상태와 공급관계 검증을 대신하지 않습니다. 전·후공정은 탐색용 대표 분류로, 여러 단계에 적용되는 장비·부품은 실제 용도에 따라 달라질 수 있습니다. 시세·주가·계좌 자동 수집은 계속 KRX와 KIS만 사용합니다.

## EGW00201 요청 제한 처리

KIS 공식 오류코드 `EGW00201`은 **초당 거래건수 초과**입니다. HTTP 500으로 반환되어도 키·SECRET 오류로 안내하지 않습니다. 같은 앱 서버 프로세스 내에서는 앱 키의 해시별로 요청 간격(최소 1.25초)을 공유합니다. 토큰·계좌 데이터는 이 공유 객체에 저장하지 않습니다.

조회 중 이 오류 또는 HTTP 429가 발생하면 해당 읽기 요청만 2초·4초·8초 대기 후 최대 3회 재시도합니다. 이미 성공한 주가 구간부터 다시 조회하지 않습니다. 다른 오류는 무조건 재시도하지 않습니다. 다른 서버나 별도 프로그램에서 동일 키를 사용하는 요청까지 제어할 수는 없습니다.

공식 근거: https://apiportal.koreainvestment.com/faq-error-code


## 두 화면의 등락률 기준 통일

시장·관심기업과 기업 상세의 대표 가격·등락률은 모두 KIS 현재가 응답(`prdy_ctrt`)과 동일한 종목별 세션 캐시를 사용합니다. KRX 최근 일별자료는 기준일을 명시한 별도 참고표에 표시하며 KIS 실패 시 대표 값으로 대체하지 않습니다. 현재가의 전일 대비 등락률과 1년 차트의 관측 기간 수익률은 다른 지표입니다.

동일한 조회 결과를 보는 동안 두 화면의 값은 같습니다. 60초 캐시 만료 또는 수동 새로고침 뒤에는 시세가 바뀔 수 있으므로 수집시각을 비교하세요. KIS 실패 시 이전 성공 자료의 유지 여부를 표에 표시합니다.


## 기업 실적 (2.2)
기존 `[kis]` 모의투자 설정을 유지하고 Secrets 맨 아래에 별도 섹션을 추가합니다.
```toml
[kis_real]
app_key = "실전용 KEY"
app_secret = "실전용 SECRET"
```
저장 후 앱을 재시작하고 기업 상세 → 기업 실적을 엽니다. 실전 계좌번호는 필요 없습니다.
최상위 환경변수/Secrets 별칭은 `KIS_REAL_APP_KEY`, `KIS_REAL_APP_SECRET`입니다.
실전 키를 모의 키로 대체하지 않으며, 실전 클라이언트는 손익계산서 GET만 허용합니다.
매출액·영업이익·당기순이익과 `영업이익 / 매출액 × 100`을 표시합니다.
연간/분기 누적을 선택하며, 분기 누적은 연단위 누적합산입니다. 단독 분기나 TTM으로 표시하지 않습니다.
금액은 환산하지 않은 KIS 제공값입니다. 확인한 API 명세에 금액 단위와 연결/별도 기준이 없어 원/억원 또는 연결 실적으로 단정하지 않습니다.
반환된 기간만 표시하며 연속조회는 지원하지 않습니다. 6시간 캐시, 실패 시 이전 성공값과 오류를 표시합니다.
공식 명세: https://apiportal.koreainvestment.com/api/apis/public/detail?accessUrl=%2Fuapi%2Fdomestic-stock%2Fv1%2Ffinance%2Fincome-statement
공식 예제: https://github.com/koreainvestment/open-trading-api/tree/main/examples_llm/domestic_stock/finance_income_statement
실제 계정 인증은 사용자 Secrets 설정 후 확인해야 합니다. 테스트에서는 가짜 응답으로 계산/라우팅/설정 분리를 검증합니다.
