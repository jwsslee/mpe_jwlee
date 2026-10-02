"""Validated, session-local data. No synthetic fallback for API failures."""
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import numpy as np
import pandas as pd

META = ['source', 'published_at', 'retrieved_at', 'status']
SCHEMAS = {
 'prices': ['code','date','open','high','low','close','adjusted_close','volume','turnover','market_cap','shares','per','pbr'] + META,
 'financials': ['code','period_end','period_type','basis','revenue','gross_profit','operating_profit','net_income','parent_net_income','equity','parent_equity','assets','liabilities','current_assets','current_liabilities','debt','cash','interest_expense','cfo','capex','inventory','receivables','cogs','rd','dividend','shares','ebitda','noncontrolling_interest','preferred_value'] + META,
 'flows': ['code','date','foreign_net','institution_net','retail_net','pension_net','foreign_ownership','short_balance','credit_balance','loan_balance'] + META,
 'operating': ['code','date','metric','value','unit','note'] + META,
 'events': ['code','date','category','title','url','note'] + META,
 'estimates': ['code','period_end','metric','value','unit','provider'] + META,
 'notes': ['code','date','thesis','risk','review_date','watch'] + META,
 'exposure': ['code','product','process','item','customer','revenue_pct','supply_status','evidence_url','verified_at'] + META,
}
TEXT = set(['code','date','period_end','period_type','basis','metric','unit','note','category','title','url','provider','thesis','risk','review_date','watch','product','process','item','customer','supply_status','evidence_url','verified_at'] + META)
KEYS = {'prices':['code','date'], 'flows':['code','date'], 'financials':['code','period_end','period_type','basis','published_at'], 'operating':['code','date','metric','source'], 'events':['code','date','title'], 'estimates':['code','period_end','metric','provider','published_at'], 'notes':['code'], 'exposure':['code','product','process','item','customer']}

def companies():
    return pd.read_csv(Path(__file__).parents[1]/'data/companies.csv', dtype=str).fillna('')

def empty():
    return {k:pd.DataFrame(columns=v) for k,v in SCHEMAS.items()}

def validate(kind, frame):
    if kind not in SCHEMAS: raise ValueError('지원하지 않는 데이터 종류입니다.')
    df=frame.copy()
    required=['code','source'] + (['period_end','period_type','basis','published_at'] if kind=='financials' else ['date'] if 'date' in SCHEMAS[kind] else [])
    missing=set(required)-set(df.columns)
    if missing: raise ValueError('필수 열 누락: '+', '.join(sorted(missing)))
    for c in SCHEMAS[kind]:
        if c not in df: df[c]=np.nan if c not in TEXT else ''
    df=df[SCHEMAS[kind]]
    df['code']=df['code'].astype(str).str.strip().str.removeprefix('A').str.zfill(6)
    if not df['code'].str.fullmatch(r'\d{6}').all(): raise ValueError('종목코드는 6자리 숫자여야 합니다.')
    for c in required:
        if df[c].fillna('').astype(str).str.strip().eq('').any(): raise ValueError(f'{c}: 빈 필수값이 있습니다.')
    for c in df:
        if c not in TEXT:
            raw=df[c].replace('',np.nan)
            numeric=pd.to_numeric(raw.astype(str).str.replace(',','',regex=False),errors='coerce')
            if (raw.notna() & numeric.isna()).any(): raise ValueError(f'{c}: 숫자가 아닌 값이 있습니다.')
            if np.isinf(numeric).any(): raise ValueError(f'{c}: 무한값은 허용하지 않습니다.')
            df[c]=numeric
        else:
            df[c]=df[c].fillna('').astype(str)
    for c in ['date','period_end','published_at','review_date','verified_at']:
        if c in df:
            active=df[c].ne('')
            parsed=pd.to_datetime(df.loc[active,c],errors='coerce',utc=True)
            if parsed.isna().any(): raise ValueError(f'{c}: YYYY-MM-DD 날짜 형식을 확인하세요.')
            df.loc[active,c]=parsed.dt.strftime('%Y-%m-%d')
    if kind=='financials':
        if (df.capex.dropna()<0).any(): raise ValueError('capex는 취득 현금지출의 양수 금액이어야 합니다.')
        if not df.period_type.isin(['Q','FY']).all(): raise ValueError('period_type은 Q(단독 분기), FY(연간)만 허용합니다. 누적 실적은 변환 후 업로드하세요.')
        if not df.basis.isin(['CFS','OFS']).all(): raise ValueError('basis는 CFS(연결), OFS(별도)입니다.')
        if (df.published_at < df.period_end).any(): raise ValueError('공시일이 회계기간 종료일보다 빠릅니다.')
    if kind=='prices':
        if ((df.close<=0) | df.close.isna()).any(): raise ValueError('종가는 양수여야 합니다.')
        if (df.adjusted_close.dropna()<=0).any(): raise ValueError('수정주가는 양수여야 합니다.')
    if kind=='exposure' and ((df.revenue_pct.dropna()<0)|(df.revenue_pct.dropna()>100)).any(): raise ValueError('매출 비중 범위는 0~100입니다.')
    if df.duplicated(KEYS[kind]).any(): raise ValueError('중복 키가 있습니다. 같은 기준의 중복 행을 제거하세요.')
    return df

def merge(old,new,kind):
    return pd.concat([old,new],ignore_index=True).drop_duplicates(KEYS[kind],keep='last').reset_index(drop=True)

def export_bundle(data):
    output=BytesIO()
    with ZipFile(output,'w',ZIP_DEFLATED) as z:
        for k,v in data.items():
            if k in SCHEMAS: z.writestr(k+'.csv',v.to_csv(index=False))
    return output.getvalue()

def import_bundle(content):
    data=empty()
    with ZipFile(BytesIO(content)) as z:
        if sum(i.file_size for i in z.infolist())>50_000_000: raise ValueError('압축 해제 크기는 50MB 이하여야 합니다.')
        for k in SCHEMAS:
            if k+'.csv' in z.namelist():
                df=pd.read_csv(z.open(k+'.csv'),dtype=str)
                if len(df): data[k]=validate(k,df)
    return data

def demo_data(master):
    """Deterministic fictional data, explicitly opt-in and isolated from real data."""
    rng=np.random.default_rng(42); data=empty(); ps=[]; fs=[]; flows=[]
    dates=pd.bdate_range('2025-01-02','2026-09-30')
    for i,row in master.head(12).iterrows():
        price=25000+i*5000
        for d in dates:
            prev=price; price=max(1000,price*(1+rng.normal(.0008,.017)))
            ps.append(dict(code=row.code,date=str(d.date()),open=prev,high=max(prev,price)*1.008,low=min(prev,price)*.992,close=round(price),adjusted_close=round(price),volume=100000+i*7000,turnover=price*(100000+i*7000),market_cap=price*20000000,shares=20000000,source='가상 예시',status='synthetic'))
            flows.append(dict(code=row.code,date=str(d.date()),foreign_net=rng.normal(2e8,7e8),institution_net=rng.normal(1e8,4e8),source='가상 예시',status='synthetic'))
        for j,d in enumerate(pd.date_range('2023-03-31','2026-06-30',freq='QE')):
            rev=(800+i*80)*1e8*(1+j*.035); op=rev*(.11+i*.006)
            fs.append(dict(code=row.code,period_end=str(d.date()),period_type='Q',basis='CFS',revenue=rev,gross_profit=rev*.32,operating_profit=op,net_income=op*.8,parent_net_income=op*.75,equity=4000e8+j*50e8,parent_equity=3800e8+j*45e8,assets=6000e8,liabilities=2000e8,current_assets=2200e8,current_liabilities=1200e8,debt=900e8,cash=700e8,cfo=op*.9,capex=op*.4,inventory=500e8,receivables=400e8,cogs=rev*.68,rd=rev*.08,interest_expense=5e8,shares=20000000,published_at=str((d+pd.Timedelta(days=45)).date()),source='가상 예시',status='synthetic'))
    for kind,rows in [('prices',ps),('financials',fs),('flows',flows)]:data[kind]=validate(kind,pd.DataFrame(rows))
    return data
