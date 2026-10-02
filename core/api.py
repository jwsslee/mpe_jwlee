"""Only two upstream institutions. Read-only KIS demo; no orders."""
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
import math,re,time
import pandas as pd
import requests
from .rate_limit import gate_for

KST=ZoneInfo('Asia/Seoul')

def now():return datetime.now(KST)
def number(value):
    try:
        n=float(str(value).replace(',','').strip())
        return n if math.isfinite(n) else float('nan')
    except (ValueError,TypeError):return float('nan')

class APIError(Exception):pass

class RateLimitError(APIError):
    def __init__(self):
        super().__init__('KIS: 초당 요청 한도 초과 (EGW00201 또는 HTTP 429). 키 오류가 아닙니다. 다른 탭·프로그램의 동일 키 호출을 줄이고 잠시 후 다시 조회하세요.')

def error_code(body):
    # Do not echo arbitrary response messages, URLs, account numbers or keys.
    value=str(body.get('msg_cd') or body.get('error_code') or '')
    return value if re.fullmatch(r'[A-Z]{2,12}[0-9]{2,8}',value) else '코드 없음'

def request(provider,method,url,**kwargs):
    try:r=requests.request(method,url,timeout=(6,20),**kwargs)
    except requests.Timeout:raise APIError(f'{provider}: 응답 시간 초과. 잠시 후 새로고침하세요.') from None
    except requests.RequestException:raise APIError(f'{provider}: 네트워크 연결 실패. 서버 접근 상태를 확인하세요.') from None
    if r.status_code!=200:
        try:code=error_code(r.json())
        except (ValueError,AttributeError):code='코드 없음'
        if provider=='KIS' and (code=='EGW00201' or r.status_code==429):raise RateLimitError()
        help_text='인증키와 해당 서비스 이용 승인을 확인하세요.' if provider=='KRX' else '모의투자 KEY·SECRET과 모의투자 신청 상태를 확인하세요.'
        if r.status_code==429:help_text='호출 한도에 도달했습니다. 잠시 후 새로고침하세요.'
        raise APIError(f'{provider}: HTTP {r.status_code} / {code}. {help_text}')
    try:body=r.json()
    except ValueError:raise APIError(f'{provider}: JSON 대신 다른 응답을 받았습니다. 서비스 상태를 확인하세요.') from None
    if not isinstance(body,dict):raise APIError(f'{provider}: 응답 형식 오류.')
    return body,r.headers

def parse_history_rows(raw,begin,end):
    """Parse only valid business rows; ignore wholly empty API padding rows."""
    if not isinstance(raw,list):raise APIError('KIS 일별주가: output2 목록 형식 오류 [history.rows]')
    result=[]
    for index,r in enumerate(raw,1):
        if r is None or r=='':continue
        if not isinstance(r,dict):raise APIError(f'KIS 일별주가: {index}행의 자료 형식 오류 [history.row]')
        value=r.get('stck_bsop_date')
        text=str(value).strip() if value is not None else ''
        if not text:
            if any(number(r.get(k))>0 for k in ('stck_clpr','stck_oprc','stck_hgpr','stck_lwpr','acml_vol')):
                raise APIError(f'KIS 일별주가: {index}행의 날짜 누락 [history.date]')
            continue
        if not re.fullmatch(r'\d{8}',text):raise APIError(f'KIS 일별주가: {index}행의 날짜 형식 오류 [history.date]')
        try:day=datetime.strptime(text,'%Y%m%d').date()
        except ValueError:raise APIError(f'KIS 일별주가: {index}행의 유효하지 않은 날짜 [history.date]') from None
        if not begin<=day<=end:continue
        row={'date':day.isoformat()}
        for dst,src in {'open':'stck_oprc','high':'stck_hgpr','low':'stck_lwpr','close':'stck_clpr','volume':'acml_vol'}.items():row[dst]=number(r.get(src))
        if row['close']>0:result.append(row)
        else:raise APIError(f'KIS 일별주가: {index}행의 종가 누락 또는 비정상 값 [history.close]')
    return result

class KRX:
    BASE='https://data-dbg.krx.co.kr/svc/apis/sto/'
    def __init__(self,key):self.key=key
    def daily(self,market,day):
        if not self.key:raise APIError('KRX: Secrets에 KRX_API_KEY를 설정하세요.')
        endpoint={'KOSPI':'stk_bydd_trd','KOSDAQ':'ksq_bydd_trd'}[market]
        body,_=request('KRX','GET',self.BASE+endpoint,headers={'AUTH_KEY':self.key},params={'basDd':day.strftime('%Y%m%d')})
        raw=body.get('OutBlock_1')
        if not isinstance(raw,list):raise APIError(f'KRX {market}: 일별매매정보 응답 없음. 인증키 승인과 이 API의 별도 이용 승인을 확인하세요.')
        rows=[]
        for r in raw:
            code=str(r.get('ISU_CD','')).removeprefix('A')
            if len(code)==12 and code.startswith('KR7'):code=code[3:9]
            if not re.fullmatch(r'\d{6}',code):continue
            row=dict(code=code,name=r.get('ISU_NM',code),market=market,source='KRX',asof=str(pd.to_datetime(r.get('BAS_DD') or day.strftime('%Y%m%d')).date()),fetched=now().isoformat())
            for dst,src in {'price':'TDD_CLSPRC','change_pct':'FLUC_RT','volume':'ACC_TRDVOL','turnover':'ACC_TRDVAL','market_cap':'MKTCAP','shares':'LIST_SHRS'}.items():row[dst]=number(r.get(src))
            if row['price']>0:rows.append(row)
        return pd.DataFrame(rows)
    def latest(self,market):
        # Search backwards through holidays and delayed publication, not auth errors.
        for offset in range(12):
            day=now().date()-timedelta(days=offset)
            if day.weekday()>4:continue
            frame=self.daily(market,day)
            if not frame.empty:return frame
        raise APIError(f'KRX {market}: 최근 12일에 제공된 시세가 없습니다.')

class KIS:
    BASE='https://openapivts.koreainvestment.com:29443'
    def __init__(self,key,secret,account='',product='01'):
        self.key=key;self.secret=secret;self.account=account;self.product=product
        self._token='';self._expires=0.;self._auth_attempt=-1e9
        self._gate=gate_for(key)
    def token(self):
        if not self.key or not self.secret:raise APIError('KIS: 모의투자 KEY·SECRET을 Secrets에 설정하세요.')
        if self._token and time.time()<self._expires:return self._token
        if time.monotonic()-self._auth_attempt<65:raise APIError('KIS: 토큰 재발급 간격입니다. 65초 후 새로고침하세요.')
        self._auth_attempt=time.monotonic()
        self._gate.wait()
        body,_=request('KIS','POST',self.BASE+'/oauth2/tokenP',json={'grant_type':'client_credentials','appkey':self.key,'appsecret':self.secret})
        if not body.get('access_token'):raise APIError(f'KIS: 토큰 인증 실패 / {error_code(body)}. 모의용 키와 신청 상태를 확인하세요.')
        self._token=body['access_token'];self._expires=time.time()+max(0,number(body.get('expires_in',3600))-120)
        return self._token
    def get(self,path,tr,params,cont=''):
        token=self.token()
        for attempt in range(4):
            self._gate.wait()
            try:
                body,headers=request('KIS','GET',self.BASE+path,headers={'content-type':'application/json; charset=utf-8','authorization':'Bearer '+token,'appkey':self.key,'appsecret':self.secret,'tr_id':tr,'tr_cont':cont,'custtype':'P'},params=params)
                if str(body.get('rt_cd'))!='0':
                    code=error_code(body)
                    if code=='EGW00201':raise RateLimitError()
                    if code in ('EGW00123','EGW00121'):self._token=''
                    raise APIError(f'KIS: 조회 거부 / {code}. 모의투자 지원·계좌 설정·호출 한도를 확인하세요.')
                return body,{str(k).lower():v for k,v in headers.items()}
            except RateLimitError:
                # Retry only this read request, not all previously fetched history chunks.
                self._gate.defer(2**(attempt+1))
                if attempt==3:raise
    def quote(self,code):
        body,_=self.get('/uapi/domestic-stock/v1/quotations/inquire-price','FHKST01010100',{'FID_COND_MRKT_DIV_CODE':'J','FID_INPUT_ISCD':code})
        r=body.get('output')
        if not isinstance(r,dict) or not number(r.get('stck_prpr'))>0:raise APIError('KIS: 유효한 현재가가 없습니다.')
        row=dict(code=code,source='KIS 모의 · KRX시장',asof='조회 시점 시세',fetched=now().isoformat())
        for dst,src in {'price':'stck_prpr','change_pct':'prdy_ctrt','volume':'acml_vol','turnover':'acml_tr_pbmn','shares':'lstn_stcn','per':'per','pbr':'pbr','eps':'eps','bps':'bps','foreign_pct':'hts_frgn_ehrt','high_52':'w52_hgpr','low_52':'w52_lwpr'}.items():row[dst]=number(r.get(src))
        row['market_cap']=row['price']*row['shares'] # KRW: avoid provider's different market-cap unit.
        for k in ('per','pbr'):
            if not row[k]>0:row[k]=float('nan')
        return row
    def history(self,code,days=365):
        start=now().date()-timedelta(days=days);end=now().date();rows=[]
        # <=90 calendar days per request => below the API's 100-record maximum.
        while end>=start:
            begin=max(start,end-timedelta(days=89))
            body,_=self.get('/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice','FHKST03010100',{'FID_COND_MRKT_DIV_CODE':'J','FID_INPUT_ISCD':code,'FID_INPUT_DATE_1':begin.strftime('%Y%m%d'),'FID_INPUT_DATE_2':end.strftime('%Y%m%d'),'FID_PERIOD_DIV_CODE':'D','FID_ORG_ADJ_PRC':'0'})
            try:
                if not isinstance(body,dict):raise APIError('KIS 일별주가: 응답 객체 형식 오류 [history.body]')
                rows.extend(parse_history_rows(body.get('output2'),begin,end))
            except APIError as error:
                raise APIError(f'{error} · 조회 구간 {begin} ~ {end}') from None
            end=begin-timedelta(days=1)
        if not rows:raise APIError('KIS: 요청 기간의 일별 주가가 없습니다.')
        return pd.DataFrame(rows).drop_duplicates('date').sort_values('date').reset_index(drop=True)
    def investors(self,code):
        body,_=self.get('/uapi/domestic-stock/v1/quotations/inquire-investor','FHKST01010900',{'FID_COND_MRKT_DIV_CODE':'J','FID_INPUT_ISCD':code})
        raw=body.get('output')
        if not isinstance(raw,list):raise APIError('KIS: 투자자 수급 응답 형식 오류.')
        rows=[]
        for r in raw:
            if not r.get('stck_bsop_date'):continue
            try:day=str(pd.to_datetime(r['stck_bsop_date'],format='%Y%m%d').date())
            except ValueError:raise APIError('KIS: 투자자 수급 날짜 형식 오류.') from None
            rows.append({'date':day,'외국인 순매수(주)':number(r.get('frgn_ntby_qty')),'기관 순매수(주)':number(r.get('orgn_ntby_qty')),'개인 순매수(주)':number(r.get('prsn_ntby_qty'))})
        if not rows:raise APIError('KIS: 제공된 투자자 수급 자료가 없습니다. 당일 수급은 장 종료 후 제공됩니다.')
        return pd.DataFrame(rows).drop_duplicates('date').sort_values('date').reset_index(drop=True)
    def balance(self):
        if not re.fullmatch(r'\d{8}',self.account) or not re.fullmatch(r'\d{2}',self.product):raise APIError('KIS: 모의계좌 앞 8자리와 상품코드 2자리를 Secrets에 설정하세요.')
        rows=[];summary=None;fk=nk=cont='';seen=set()
        for _ in range(100):
            body,headers=self.get('/uapi/domestic-stock/v1/trading/inquire-balance','VTTC8434R',{'CANO':self.account,'ACNT_PRDT_CD':self.product,'AFHR_FLPR_YN':'N','OFL_YN':'','INQR_DVSN':'02','UNPR_DVSN':'01','FUND_STTL_ICLD_YN':'N','FNCG_AMT_AUTO_RDPT_YN':'N','PRCS_DVSN':'00','CTX_AREA_FK100':fk,'CTX_AREA_NK100':nk},cont)
            if not isinstance(body.get('output1'),list):raise APIError('KIS: 잔고 목록 누락. 일부 잔고를 전체로 표시하지 않습니다.')
            rows.extend(body['output1'])
            if summary is None:
                s=body.get('output2');summary=s[0] if isinstance(s,list) and s else s if isinstance(s,dict) else None
                if not summary:raise APIError('KIS: 계좌 합계 누락.')
            if headers.get('tr_cont','') not in ('M','F'):break
            fk=str(body.get('ctx_area_fk100','')).strip();nk=str(body.get('ctx_area_nk100','')).strip()
            if not (fk or nk) or (fk,nk) in seen:raise APIError('KIS: 잔고 연속조회 실패. 일부 결과를 표시하지 않습니다.')
            seen.add((fk,nk));cont='N'
        else:raise APIError('KIS: 잔고 연속조회 한도 초과.')
        mapping={'pdno':'code','prdt_name':'name','hldg_qty':'quantity','pchs_avg_pric':'avg_price','pchs_amt':'cost','prpr':'price','evlu_amt':'value','evlu_pfls_amt':'pnl','evlu_pfls_rt':'pnl_pct'}
        df=pd.DataFrame(rows).rename(columns=mapping).reindex(columns=mapping.values())
        for c in set(mapping.values())-{'code','name'}:df[c]=df[c].map(number)
        df=df[df.quantity>0].copy()
        if df.code.duplicated().any():raise APIError('KIS: 중복 잔고 응답. 전체 결과를 다시 조회하세요.')
        fields=['dnca_tot_amt','tot_evlu_amt','pchs_amt_smtl_amt','evlu_amt_smtl_amt','evlu_pfls_smtl_amt']
        return df,{k:number(summary.get(k)) for k in fields}
