"""Read-only adapters. Never log request URLs, headers, tokens or accounts."""
from datetime import datetime, timezone
import re
import time
from urllib.parse import unquote
import requests
import pandas as pd
from .data import validate

class APIError(Exception): pass

def number(value):
    if value is None or str(value).strip() in ('','-'): return float('nan')
    try:return float(str(value).replace(',',''))
    except (TypeError,ValueError): return float('nan')

def json_request(method,url,**kwargs):
    try:
        response=requests.request(method,url,timeout=(8,30),**kwargs)
        if response.status_code!=200:raise APIError(f'API HTTP {response.status_code}: 권한·서비스 상태를 확인하세요.')
        data=response.json()
        if not isinstance(data,dict): raise APIError('API 응답 형식이 예상과 다릅니다.')
        return data,response.headers
    except APIError:raise
    except (requests.RequestException,ValueError):raise APIError('API에 연결할 수 없거나 JSON 응답이 아닙니다. 네트워크·키·서비스 승인을 확인하세요.') from None

class KISDemo:
    BASE='https://openapivts.koreainvestment.com:29443'
    def __init__(self,key,secret,cano='',product='01'):
        if not key or not secret:raise APIError('모의투자 APP KEY와 APP SECRET을 설정하세요.')
        self.key=key;self.secret=secret;self.cano=cano;self.product=product
        self._token='';self._expires=0;self._last_auth=0
    def token(self):
        if self._token and time.time()<self._expires:return self._token
        if time.time()-self._last_auth<65:raise APIError('토큰 재요청 간격을 위해 약 1분 후 다시 시도하세요.')
        self._last_auth=time.time()
        body,_=json_request('POST',self.BASE+'/oauth2/tokenP',json={'grant_type':'client_credentials','appkey':self.key,'appsecret':self.secret})
        if not body.get('access_token'):raise APIError('모의투자 인증 실패. 모의용 키·SECRET과 API 신청 상태를 확인하세요.')
        self._token=body['access_token'];self._expires=time.time()+max(0,int(body.get('expires_in',3600))-120)
        return self._token
    def get(self,path,tr,params,cont=''):
        data,headers=json_request('GET',self.BASE+path,headers={'authorization':'Bearer '+self.token(),'appkey':self.key,'appsecret':self.secret,'tr_id':tr,'tr_cont':cont,'custtype':'P'},params=params)
        if data.get('rt_cd')!='0':
            code=re.sub(r'[^A-Za-z0-9_-]','',str(data.get('msg_cd','unknown')))[:30]
            raise APIError(f'한국투자증권 응답 오류 ({code}). 모의투자 지원 여부·조회 시간·계좌 설정을 확인하세요.')
        return data,headers
    def balance(self):
        if not re.fullmatch(r'\d{8}',self.cano) or not re.fullmatch(r'\d{2}',self.product):raise APIError('계좌 앞 8자리와 상품코드 2자리를 확인하세요.')
        rows=[];summary=None;fk=nk=cont='';seen=set()
        for page in range(100):
            data,headers=self.get('/uapi/domestic-stock/v1/trading/inquire-balance','VTTC8434R',{'CANO':self.cano,'ACNT_PRDT_CD':self.product,'AFHR_FLPR_YN':'N','OFL_YN':'','INQR_DVSN':'02','UNPR_DVSN':'01','FUND_STTL_ICLD_YN':'N','FNCG_AMT_AUTO_RDPT_YN':'N','PRCS_DVSN':'00','CTX_AREA_FK100':fk,'CTX_AREA_NK100':nk},cont)
            if not isinstance(data.get('output1'),list):raise APIError('잔고 목록 형식 오류. 이전 결과를 유지합니다.')
            rows.extend(data['output1'])
            if summary is None:
                s=data.get('output2',[])
                summary=s[0] if isinstance(s,list) and s else s if isinstance(s,dict) else None
                if summary is None:raise APIError('계좌 요약이 누락되었습니다.')
            if headers.get('tr_cont','') not in ('M','F'):break
            fk=data.get('ctx_area_fk100','').strip();nk=data.get('ctx_area_nk100','').strip()
            if not (fk or nk) or (fk,nk) in seen:raise APIError('연속조회가 완료되지 않았습니다. 일부 잔고를 전체 잔고로 표시하지 않습니다.')
            seen.add((fk,nk));cont='N';time.sleep(.65)
        else:raise APIError('연속조회 한도 초과. 잔고 전체를 확인할 수 없습니다.')
        mapping={'pdno':'code','prdt_name':'name','hldg_qty':'quantity','pchs_avg_pric':'avg_price','pchs_amt':'cost','prpr':'price','evlu_amt':'value','evlu_pfls_amt':'pnl','evlu_pfls_rt':'pnl_pct'}
        df=pd.DataFrame(rows)
        if df.empty:df=pd.DataFrame(columns=mapping.values())
        else:
            df=df.rename(columns=mapping).reindex(columns=mapping.values())
            df['code']=df.code.astype(str).str.zfill(6)
            for c in set(mapping.values())-{'code','name'}:df[c]=df[c].map(number)
            df=df[df.quantity>0].copy()
            # Product-level query should be unique; refuse ambiguous duplicate pages.
            if df.code.duplicated().any():raise APIError('중복 종목 잔고가 반환되었습니다. 전체 잔고를 다시 조회하세요.')
        sm={k:number(summary.get(k)) for k in ['dnca_tot_amt','nxdy_excc_amt','prvs_rcdl_excc_amt','tot_evlu_amt','nass_amt','pchs_amt_smtl_amt','evlu_amt_smtl_amt','evlu_pfls_smtl_amt']}
        return df,sm,datetime.now(timezone.utc).isoformat()
    def investor(self,code):
        data,_=self.get('/uapi/domestic-stock/v1/quotations/inquire-investor','FHKST01010900',{'FID_COND_MRKT_DIV_CODE':'J','FID_INPUT_ISCD':code})
        rows=[]
        for r in data.get('output',[]):
            # KIS investor API net purchase amounts are in millions of KRW.
            rows.append(dict(code=code,date=r['stck_bsop_date'],foreign_net=number(r.get('frgn_ntby_tr_pbmn'))*1e6,institution_net=number(r.get('orgn_ntby_tr_pbmn'))*1e6,retail_net=number(r.get('prsn_ntby_tr_pbmn'))*1e6,source='KIS 투자자',retrieved_at=datetime.now(timezone.utc).isoformat(),status='reported'))
        return validate('flows',pd.DataFrame(rows)) if rows else pd.DataFrame()

class KRX:
    def __init__(self,key):self.key=key
    def daily(self,date,market,codes):
        if not self.key:raise APIError('KRX 인증키가 필요합니다.')
        endpoint={'KOSPI':'stk_bydd_trd','KOSDAQ':'ksq_bydd_trd'}[market]
        data,_=json_request('GET','https://data-dbg.krx.co.kr/svc/apis/sto/'+endpoint,headers={'AUTH_KEY':self.key},params={'basDd':date.strftime('%Y%m%d')})
        if 'OutBlock_1' not in data:raise APIError('KRX 응답에 시세가 없습니다. 해당 시장의 일별매매정보 승인을 확인하세요.')
        rows=[]
        for r in data['OutBlock_1']:
            code=str(r.get('ISU_CD','')).removeprefix('A')
            if len(code)==12 and code.startswith('KR7'):code=code[3:9]
            if code not in codes:continue
            d=dict(code=code,date=r.get('BAS_DD',date.strftime('%Y%m%d')),source='KRX '+market,retrieved_at=datetime.now(timezone.utc).isoformat(),status='reported')
            for c,field in {'open':'TDD_OPNPRC','high':'TDD_HGPRC','low':'TDD_LWPRC','close':'TDD_CLSPRC','volume':'ACC_TRDVOL','turnover':'ACC_TRDVAL','market_cap':'MKTCAP','shares':'LIST_SHRS'}.items():d[c]=number(r.get(field))
            if d['close']>0:rows.append(d)
        return validate('prices',pd.DataFrame(rows)) if rows else pd.DataFrame()

class PublicData:
    BASE='https://apis.data.go.kr/1160100/service/'
    def __init__(self,key):self.key=unquote(key)
    def items(self,service,operation,params):
        if not self.key:raise APIError('공공데이터포털 인증키가 필요합니다.')
        rows=[]
        for page in range(1,101):
            d,_=json_request('GET',self.BASE+service+'/'+operation,params={'serviceKey':self.key,'resultType':'json','numOfRows':100,'pageNo':page,**params})
            response=d.get('response',{});header=response.get('header',{})
            if str(header.get('resultCode')) not in ('00','0'):raise APIError('공공데이터 응답 오류. 해당 서비스의 활용신청·인증키를 확인하세요.')
            b=response.get('body',{});items=(b.get('items') or {}).get('item',[])
            if isinstance(items,dict):items=[items]
            rows.extend(items)
            if len(rows)>=int(b.get('totalCount',len(rows))):return pd.DataFrame(rows)
            if not items:raise APIError('페이지가 누락되어 수집을 완료하지 못했습니다.')
            time.sleep(.15)
        raise APIError('조회 한도를 넘었습니다. 기간을 줄여 주세요.')
    def prices(self,code,start,end):
        raw=self.items('GetStockSecuritiesInfoService','getStockPriceInfo',{'likeSrtnCd':code,'beginBasDt':start.strftime('%Y%m%d'),'endBasDt':end.strftime('%Y%m%d')})
        rows=[]
        for _,r in raw.iterrows():
            if str(r.get('srtnCd','')).removeprefix('A').zfill(6)!=code:continue
            d=dict(code=code,date=r['basDt'],source='공공데이터 주식시세',retrieved_at=datetime.now(timezone.utc).isoformat(),status='reported')
            for c,k in {'open':'mkp','high':'hipr','low':'lopr','close':'clpr','volume':'trqu','turnover':'trPrc','market_cap':'mrktTotAmt','shares':'lstgStCnt'}.items():d[c]=number(r.get(k))
            if d['close']>0:rows.append(d)
        return validate('prices',pd.DataFrame(rows)) if rows else pd.DataFrame()
    def financial_raw(self,crno,year):
        if not re.fullmatch(r'\d{13}',crno):raise APIError('법인등록번호 13자리가 필요합니다. 종목코드·사업자번호와 다릅니다.')
        return self.items('GetFinaStatInfoService_V2','getSummFinaStat_V2',{'crno':crno,'bizYear':str(year)})
