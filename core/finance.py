"""Read-only real KIS income statements, isolated from demo account access."""
from datetime import datetime
import re
import pandas as pd
from .api import KIS,APIError,number

PATH='/uapi/domestic-stock/v1/finance/income-statement'
TR='FHKST66430200'

def parse_income(raw):
    if not isinstance(raw,list):raise APIError('KIS 실전 재무: 손익계산서 목록 형식 오류.')
    rows=[]
    for r in raw:
        if r in (None,'',{}):continue
        if not isinstance(r,dict):raise APIError('KIS 실전 재무: 손익계산서 행 형식 오류.')
        period=str(r.get('stac_yymm') or '').strip()
        if not period and all(not str(v or '').strip() for v in r.values()):continue
        if not re.fullmatch(r'\d{6}',period):raise APIError('KIS 실전 재무: 결산년월 형식 오류.')
        try:datetime.strptime(period,'%Y%m')
        except ValueError:raise APIError('KIS 실전 재무: 유효하지 않은 결산년월.') from None
        sales=number(r.get('sale_account'));profit=number(r.get('bsop_prti'))
        rows.append({'결산년월':period[:4]+'-'+period[4:],'매출액':sales,'영업이익':profit,
                     '영업이익률(%)':profit/sales*100 if sales>0 else float('nan'),
                     '당기순이익':number(r.get('thtr_ntin'))})
    if not rows:raise APIError('KIS 실전 재무: 제공된 손익계산서가 없습니다.')
    df=pd.DataFrame(rows).drop_duplicates()
    if df['결산년월'].duplicated().any():raise APIError('KIS 실전 재무: 같은 결산년월에 서로 다른 값이 반환되었습니다.')
    if df[['매출액','영업이익','당기순이익']].isna().all().all():raise APIError('KIS 실전 재무: 제공된 실적 수치가 없습니다.')
    return df.sort_values('결산년월').reset_index(drop=True)

class KISFinancials(KIS):
    BASE='https://openapi.koreainvestment.com:9443'
    PROVIDER='KIS 실전 재무'
    ENV_LABEL='실전투자'

    def get(self,path,tr,params,cont=''):
        # Allow only this financial-data GET, never account or trading endpoints.
        if path!=PATH or tr!=TR or cont:raise APIError('KIS 실전 재무: 허용되지 않은 조회입니다.')
        return super().get(path,tr,params)

    def income(self,code,division='0'):
        if not re.fullmatch(r'\d{6}',code) or division not in ('0','1'):
            raise APIError('KIS 실전 재무: 종목 또는 결산 구분 오류.')
        body,_=self.get(PATH,TR,{'FID_DIV_CLS_CODE':division,'fid_cond_mrkt_div_code':'J','fid_input_iscd':code})
        # Official specification: no tr_cont pagination for this endpoint.
        return parse_income(body.get('output'))
