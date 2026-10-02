"""Official ECOS series. No scraping, sample fallback, or credential logging."""
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import quote
import math,re
import pandas as pd
import requests
from .api import APIError,now,number

@dataclass(frozen=True)
class Series:
    name:str
    table:str
    item:str
    cycle:str
    unit:str
    note:str

SERIES={
 'gdp_yoy':Series('경제성장률 · 전년 동기 대비','200Y102','10211','Q','%','실질 GDP 원계열 · 전년 같은 분기 대비 · ECOS 제공 성장률'),
 'gdp_qoq':Series('경제성장률 · 전분기 대비','200Y102','10111','Q','%','실질 GDP 계절조정 · 직전 분기 대비 · 연율 환산하지 않음'),
 'cpi':Series('소비자물가상승률 · 전년 동월 대비','901Y009','0','M','2020=100','소비자물가 총지수로 계산 · (당월 지수 / 전년 같은 달 지수 − 1) × 100'),
 'usd':Series('원/달러','731Y001','0000001','D','원','1달러당 원화 · 매매기준율 · 일별 통계, 실시간 호가 아님'),
 'jpy':Series('원/엔 · 100엔','731Y001','0000002','D','원','100엔당 원화 · 일별 통계, 실시간 호가 아님'),
 'eur':Series('원/유로','731Y001','0000003','D','원','1유로당 원화 · 일별 통계, 실시간 호가 아님'),
}

def period_label(value,cycle):
    if cycle=='Q':
        if not re.fullmatch(r'\d{4}Q[1-4]',value):raise ValueError()
        return value[:4]+'년 '+value[-1]+'분기'
    fmt='%Y%m' if cycle=='M' else '%Y%m%d'
    if not re.fullmatch(r'\d{6}' if cycle=='M' else r'\d{8}',value):raise ValueError()
    dt=datetime.strptime(value,fmt)
    return dt.strftime('%Y-%m' if cycle=='M' else '%Y-%m-%d')

def parse_series(rows,spec):
    parsed=[]
    for r in rows:
        if not isinstance(r,dict):raise APIError('ECOS: 통계 행 형식 오류.')
        if r.get('STAT_CODE')!=spec.table or r.get('ITEM_CODE1')!=spec.item:
            raise APIError('ECOS: 요청한 통계와 다른 항목이 반환되었습니다.')
        if any(r.get('ITEM_CODE'+str(i)) for i in (2,3,4)):
            raise APIError('ECOS: 예상하지 않은 세부 통계항목이 반환되었습니다.')
        if str(r.get('UNIT_NAME','')).strip()!=spec.unit:
            raise APIError('ECOS: 통계 단위가 변경되었습니다. 통계항목 확인이 필요합니다.')
        period=str(r.get('TIME',''))
        try:label=period_label(period,spec.cycle)
        except ValueError:raise APIError('ECOS: 통계 기준기간 형식 오류.') from None
        v=number(r.get('DATA_VALUE'))
        if not math.isfinite(v) and str(r.get('DATA_VALUE') or '').strip() not in ('','-','..','...'):
            raise APIError('ECOS: 통계 수치 형식 오류.')
        parsed.append({'period':period,'기준기간':label,'원자료':v})
    if not parsed:raise APIError('ECOS: 제공된 통계가 없습니다.')
    df=pd.DataFrame(parsed).drop_duplicates()
    if df.period.duplicated().any():raise APIError('ECOS: 같은 기간에 서로 다른 통계값이 반환되었습니다.')
    df=df.sort_values('period').reset_index(drop=True)
    if not df['원자료'].notna().any():raise APIError('ECOS: 유효한 통계 수치가 없습니다.')
    df['값']=df['원자료']
    if spec.cycle=='M':
        # Calendar lookup, not row shift: missing months must not shift the baseline.
        values=dict(zip(df.period,df['원자료']))
        df['값']=[(v/values.get(str(int(p[:4])-1)+p[4:],float('nan'))-1)*100
                   if values.get(str(int(p[:4])-1)+p[4:],0)>0 else float('nan')
                   for p,v in zip(df.period,df['원자료'])]
    return df

class ECOS:
    BASE='https://ecos.bok.or.kr/api/StatisticSearch/'
    def __init__(self,key):self.key=key

    def _page(self,spec,start,end,first,last):
        if not self.key:raise APIError('ECOS: Secrets의 [ecos] api_key를 설정하세요.')
        url=self.BASE+'/'.join([quote(self.key,safe=''),'json','kr',str(first),str(last),spec.table,spec.cycle,start,end,spec.item])
        try:r=requests.get(url,timeout=(6,20))
        except requests.Timeout:raise APIError('ECOS: 응답 시간 초과. 잠시 후 다시 조회하세요.') from None
        except requests.RequestException:raise APIError('ECOS: 네트워크 연결 실패. 배포 서버에서 ECOS 접근이 가능한지 확인하세요.') from None
        if r.status_code!=200:raise APIError(f'ECOS: HTTP {r.status_code}. 서비스 상태와 호출 한도를 확인하세요.')
        try:body=r.json()
        except ValueError:raise APIError('ECOS: JSON이 아닌 응답을 받았습니다.') from None
        if not isinstance(body,dict):raise APIError('ECOS: 응답 형식 오류.')
        if isinstance(body.get('RESULT'),dict):
            code=str(body['RESULT'].get('CODE',''))
            safe=code if re.fullmatch(r'(INFO|ERROR)-\d{3}',code) else '코드 미제공'
            messages={'INFO-100':'인증키가 유효하지 않습니다. [ecos] api_key를 확인하세요.',
                      'INFO-200':'해당 기간의 통계가 없습니다.',
                      'ERROR-301':'요청 건수 한도를 초과했습니다. 정식 인증키인지 확인하세요.'}
            raise APIError('ECOS: '+safe+' · '+messages.get(code,'인증키 승인·호출 한도·서비스 상태를 확인하세요.'))
        block=body.get('StatisticSearch')
        if not isinstance(block,dict) or not isinstance(block.get('row'),list):raise APIError('ECOS: 통계 목록이 없습니다.')
        try:total=int(block['list_total_count'])
        except (KeyError,ValueError,TypeError):raise APIError('ECOS: 통계 건수 형식 오류.') from None
        if total<=0:raise APIError('ECOS: 제공된 통계가 없습니다.')
        return block['row'],total

    def series(self,name):
        spec=SERIES[name];today=now().date();year=today.year-6
        start=f'{year}Q1' if spec.cycle=='Q' else f'{year}01' if spec.cycle=='M' else f'{today.year-5}0101'
        end=f'{today.year}Q{(today.month-1)//3+1}' if spec.cycle=='Q' else today.strftime('%Y%m' if spec.cycle=='M' else '%Y%m%d')
        rows=[];expected=None
        for first in range(1,5001,1000):
            batch,total=self._page(spec,start,end,first,first+999)
            if total>5000 or (expected is not None and total!=expected):raise APIError('ECOS: 조회 중 통계 건수가 변경되었거나 조회 범위를 초과했습니다. 다시 조회하세요.')
            expected=total
            if len(batch)!=min(1000,total-first+1):raise APIError('ECOS: 일부 통계만 반환되어 표시를 중단했습니다.')
            rows.extend(batch)
            if len(rows)==total:break
        else:raise APIError('ECOS: 통계 연속조회 한도 초과.')
        df=parse_series(rows,spec)
        if df.period.duplicated().any() or len(df)!=expected:raise APIError('ECOS: 통계 중복 또는 누락이 있습니다.')
        return df
