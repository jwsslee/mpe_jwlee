from datetime import datetime
from pathlib import Path
import pandas as pd
import pytest
import requests
from streamlit.testing.v1 import AppTest
from core.api import KIS,KRX,APIError,request,KST
from core.settings import read_settings
from core.state import collect


def test_settings_formats_and_split_account():
    cfg=read_settings({'APP_PASSWORD':'pw','KIS_APP_KEY':'key','KIS_APP_SECRET':'secret','KIS_ACCOUNT_NO':'00123456-02','KRX_API_KEY':'krx'})
    assert (cfg.key,cfg.secret,cfg.account,cfg.product)==('key','secret','00123456','02')
    assert cfg.krx=='krx' and cfg.password=='pw'
    cfg=read_settings({'KIS':{'APP_KEY':'nested'},'KIS_APP_KEY':'flat','krx':{'api_key':'krx'}})
    assert cfg.key=='nested' and cfg.krx=='krx'
    assert read_settings({'krx':{'api_key':'private'}}).key==''
    assert 'key' not in repr(cfg)


def test_failure_keeps_success_and_does_not_spin():
    cache={};calls=[]
    good=collect(cache,'q',lambda:42)
    def bad():calls.append(1);raise APIError('rejected')
    failed=collect(cache,'q',bad,force=True)
    assert failed['data']==42 and failed['success_at']==good['success_at']
    assert failed['error']=='rejected'
    collect(cache,'q',bad)
    assert len(calls)==1


def test_http_redacts_response_and_no_external_provider(monkeypatch):
    r=requests.Response();r.status_code=403;r._content=b'{"msg_cd":"EGW00123","message":"secret-account-key"}'
    monkeypatch.setattr(requests,'request',lambda *a,**k:r)
    with pytest.raises(APIError) as err:request('KIS','GET',KIS.BASE)
    assert 'EGW00123' in str(err.value) and 'secret-account' not in str(err.value)
    assert KIS.BASE=='https://openapivts.koreainvestment.com:29443'


def test_krx_normalizes_isin_and_unit(monkeypatch):
    calls=[]
    def response(*args,**kwargs):
        calls.append(kwargs)
        return {'OutBlock_1':[{'ISU_CD':'KR7353200009','ISU_NM':'대덕전자','BAS_DD':'20261001','TDD_CLSPRC':'10,000','MKTCAP':'100000000','FLUC_RT':'1.5'}]},{}
    monkeypatch.setattr('core.api.request',response)
    frame=KRX('test').daily('KOSPI',datetime(2026,10,1).date())
    assert frame.code.iloc[0]=='353200' and frame.market_cap.iloc[0]==100000000
    assert calls[0]['headers']=={'AUTH_KEY':'test'}
    assert calls[0]['params']=={'basDd':'20261001'}


def test_krx_auth_failure_no_date_retries(monkeypatch):
    calls=[]
    def denied(*args):calls.append(1);raise APIError('auth')
    monkeypatch.setattr(KRX,'daily',denied)
    with pytest.raises(APIError):KRX('test').latest('KOSDAQ')
    assert len(calls)==1


def test_kis_token_reuse_and_cooldown(monkeypatch):
    calls=[]
    def response(*args,**kwargs):calls.append(kwargs);return {'access_token':'test-token','expires_in':3600},{}
    monkeypatch.setattr('core.api.request',response)
    client=KIS('key','secret')
    assert client.token()==client.token()=='test-token' and len(calls)==1
    client._token=''
    with pytest.raises(APIError):client.token()


def test_quote_units_and_unusable_per(monkeypatch):
    monkeypatch.setattr(KIS,'get',lambda *a:({'output':{'stck_prpr':'100','lstn_stcn':'1000','per':'0','pbr':'1.2'}},{}))
    q=KIS('key','secret').quote('353200')
    assert q['market_cap']==100000 and pd.isna(q['per']) and q['pbr']==1.2


def test_history_chunks_do_not_truncate_100_records(monkeypatch):
    monkeypatch.setattr('core.api.now',lambda:datetime(2026,10,2,tzinfo=KST))
    calls=[]
    def get(self,path,tr,params,cont=''):
        calls.append(params)
        start=pd.Timestamp(params['FID_INPUT_DATE_1']);end=pd.Timestamp(params['FID_INPUT_DATE_2'])
        rows=[{'stck_bsop_date':d.strftime('%Y%m%d'),'stck_clpr':'100'} for d in pd.bdate_range(start,end)]
        assert len(rows)<100
        return {'output2':rows},{}
    monkeypatch.setattr(KIS,'get',get)
    df=KIS('key','secret').history('353200')
    assert len(df)>250 and len(calls)==5
    assert df.date.is_unique and df.date.is_monotonic_increasing
    assert all(p['FID_ORG_ADJ_PRC']=='0' for p in calls)


def test_history_partial_failure_not_returned(monkeypatch):
    calls=[]
    def get(*args):
        calls.append(1)
        if len(calls)>1:raise APIError('failure')
        return {'output2':[]},{}
    monkeypatch.setattr(KIS,'get',get)
    with pytest.raises(APIError):KIS('k','s').history('353200')


def test_balance_pagination_and_totals(monkeypatch):
    calls=[]
    pages=[({'output1':[{'pdno':'353200','prdt_name':'대덕전자','hldg_qty':'2','evlu_amt':'100'}], 'output2':[{'tot_evlu_amt':'500','evlu_pfls_smtl_amt':'20'}],'ctx_area_fk100':'a','ctx_area_nk100':'b'}, {'tr_cont':'M'}),({'output1':[{'pdno':'000660','hldg_qty':'1'},{'pdno':'111111','hldg_qty':'0'}],'output2':[{'tot_evlu_amt':'500'}]}, {})]
    def get(self,path,tr,params,cont=''):calls.append((tr,cont));return pages.pop(0)
    monkeypatch.setattr(KIS,'get',get)
    df,summary=KIS('k','s','00123456').balance()
    assert len(df)==2 and summary['tot_evlu_amt']==500
    assert calls==[('VTTC8434R',''),('VTTC8434R','N')]
    assert pd.isna(summary['dnca_tot_amt'])


def test_partial_balance_rejected(monkeypatch):
    monkeypatch.setattr(KIS,'get',lambda *a:({'output1':[],'output2':[{'tot_evlu_amt':'10'}]}, {'tr_cont':'M'}))
    with pytest.raises(APIError):KIS('k','s','00123456').balance()


def app(monkeypatch,keys=True):
    monkeypatch.chdir(Path(__file__).resolve().parents[1])
    at=AppTest.from_file(Path(__file__).resolve().parents[1]/'app.py',default_timeout=60)
    at.secrets={'APP_PASSWORD':'test-password'}
    if keys:at.secrets.update({'KRX_API_KEY':'test-krx','KIS_APP_KEY':'test-key','KIS_APP_SECRET':'test-secret','KIS_CANO':'00123456'})
    at.run();return at


def login(at):
    at.text_input[0].set_value('test-password');at.button[0].click().run();return at


def test_auto_ui_all_pages_with_realistic_responses(monkeypatch):
    calls=[]
    def latest(self,market):
        calls.append(market)
        return pd.DataFrame([dict(code='353200',name='대덕전자',market=market,price=100,change_pct=1,turnover=1000,volume=10,market_cap=100000,source='KRX',asof='2026-10-01',fetched='2026-10-02')])
    def quote(self,code):
        calls.append('quote')
        return dict(code=code,price=100,change_pct=1,volume=10,turnover=1000,market_cap=100000,source='KIS',asof='조회 시점',fetched='2026-10-02',per=10,pbr=1,eps=10,bps=100,foreign_pct=5,high_52=120,low_52=80)
    def history(self,code):calls.append('history');return pd.DataFrame({'date':['2026-09-30','2026-10-01'],'close':[90,100],'volume':[1,2]})
    def balance(self):
        calls.append('balance')
        return pd.DataFrame([dict(code='353200',name='대덕전자',quantity=1,value=100,pnl=10)]),dict(tot_evlu_amt=200,evlu_amt_smtl_amt=100,pchs_amt_smtl_amt=90,evlu_pfls_smtl_amt=10,dnca_tot_amt=100)
    monkeypatch.setattr(KIS,'investors',lambda *a:pd.DataFrame({'date':['2026-10-01'],'외국인 순매수(주)':[10],'기관 순매수(주)':[-5],'개인 순매수(주)':[-5]}))
    monkeypatch.setattr(KRX,'latest',latest);monkeypatch.setattr(KIS,'quote',quote);monkeypatch.setattr(KIS,'history',history);monkeypatch.setattr(KIS,'balance',balance)
    at=app(monkeypatch)
    assert not calls # Authentication gates all API and account access.
    login(at)
    assert not at.exception
    n=len(calls);at.run();assert len(calls)==n
    for page in ('기업 상세','모의투자 계좌','연결 진단'):
        at.sidebar.radio[0].set_value(page).run();assert not at.exception
    assert 'history' in calls and 'balance' in calls
    assert any(m.label=='총평가금액' for m in at.sidebar.radio[0].set_value('모의투자 계좌').run().metric)


def test_empty_and_failed_services_no_crash(monkeypatch):
    def fail(*args):raise APIError('HTTP 403 / 테스트 거부')
    monkeypatch.setattr(KIS,'investors',fail)
    monkeypatch.setattr(KRX,'latest',fail);monkeypatch.setattr(KIS,'quote',fail);monkeypatch.setattr(KIS,'history',fail);monkeypatch.setattr(KIS,'balance',fail)
    at=login(app(monkeypatch))
    assert at.error and not at.exception
    for page in at.sidebar.radio[0].options:
        at.sidebar.radio[0].set_value(page).run();assert not at.exception
    at2=login(app(monkeypatch,keys=False))
    assert not at2.exception


def test_investor_quantity_signed_and_sorted(monkeypatch):
    monkeypatch.setattr(KIS,'get',lambda *a:({'output':[{'stck_bsop_date':'20261001','frgn_ntby_qty':'-1,234','orgn_ntby_qty':'10','prsn_ntby_qty':'1224'}]},{}))
    df=KIS('k','s').investors('353200')
    assert df['외국인 순매수(주)'].iloc[0]==-1234


def test_krx_failure_kis_still_populates_overview(monkeypatch):
    def denied(*args):raise APIError('KRX denied')
    monkeypatch.setattr(KRX,'latest',denied)
    monkeypatch.setattr(KIS,'quote',lambda self,code:dict(code=code,price=100,change_pct=1,turnover=100,volume=1,market_cap=1000,source='KIS',asof='조회시점',fetched='2026-10-02'))
    at=login(app(monkeypatch))
    assert not at.exception and at.warning
    assert at.metric[0].value=='12 / 12'


def test_transport_uses_demo_routes_and_reuses_token(monkeypatch):
    calls=[]
    def transport(method,url,**kwargs):
        calls.append((method,url,kwargs))
        r=requests.Response();r.status_code=200
        import json
        if url.endswith('/oauth2/tokenP'):
            assert kwargs['json']['appkey']=='key'
            body={'access_token':'token','expires_in':86400}
        else:
            assert url.startswith(KIS.BASE+'/uapi/')
            assert kwargs['headers']['authorization']=='Bearer token'
            assert kwargs['headers']['tr_id']=='FHKST01010100'
            assert kwargs['params']['FID_INPUT_ISCD']=='353200'
            body={'rt_cd':'0','output':{'stck_prpr':'100','lstn_stcn':'20'}}
        r._content=json.dumps(body).encode();return r
    monkeypatch.setattr(requests,'request',transport)
    monkeypatch.setattr('core.api.time.sleep',lambda _:None)
    client=KIS('key','secret')
    assert client.quote('353200')['market_cap']==2000
    client.quote('353200')
    assert len(calls)==3 and calls[0][0]=='POST'
