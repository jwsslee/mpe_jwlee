import pandas as pd
import pytest
from core.api import KIS,KRX,APIError
from core.finance import KISFinancials,parse_income,PATH,TR
from core.settings import read_settings
from test_system import app,login


def test_credentials_are_separate():
    s=read_settings({'app_key':'mock','app_secret':'mock-secret'})
    assert s.key=='mock' and s.real_key==s.real_secret==''
    s=read_settings({'kis':{'app_key':'mock','app_secret':'ms'},'kis_real':{'app_key':'real','app_secret':'rs'}})
    assert (s.key,s.secret,s.real_key,s.real_secret)==('mock','ms','real','rs')
    t=read_settings({'kis':{'app_key':'mock','app_secret':'ms'}},{'KIS_REAL_APP_KEY':'real','KIS_REAL_APP_SECRET':'rs'})
    assert s.fingerprint==t.fingerprint and s.finance_fingerprint==t.finance_fingerprint
    assert read_settings({}, {'app_key':'mock'}).real_key==''


def test_values_and_margins():
    df=parse_income([{}, {'stac_yymm':'202512','sale_account':'1,000','bsop_prti':'-25','thtr_ntin':''},
                     {'stac_yymm':'202412','sale_account':'0','bsop_prti':'10'}])
    assert df['결산년월'].tolist()==['2024-12','2025-12']
    assert df.iloc[-1]['영업이익률(%)']==-2.5 and df.iloc[-1]['매출액']==1000
    assert pd.isna(df.iloc[0]['영업이익률(%)']) and pd.isna(df.iloc[-1]['당기순이익'])


@pytest.mark.parametrize('rows',[{},[],[{'stac_yymm':'202513'}],[{'stac_yymm':'202512'}],
    [{'stac_yymm':'202512','sale_account':'1'},{'stac_yymm':'202512','sale_account':'2'}]])
def test_bad_response(rows):
    with pytest.raises(APIError):parse_income(rows)


def test_real_route_and_only_allowed_endpoint(monkeypatch):
    calls=[]
    def request(provider,method,url,**kw):
        calls.append((provider,method,url,kw))
        if method=='POST':return {'access_token':'token','expires_in':86400},{}
        return {'rt_cd':'0','output':[{'stac_yymm':'202509','sale_account':'100','bsop_prti':'20'}]}, {'tr_cont':'M'}
    monkeypatch.setattr('core.api.request',request)
    client=KISFinancials('real-key','real-secret')
    monkeypatch.setattr(client._gate,'wait',lambda:None)
    for mode in ('0','1'):assert client.income('000660',mode).iloc[0]['영업이익률(%)']==20
    assert len(calls)==3
    assert all(c[2].startswith(KISFinancials.BASE+'/') for c in calls)
    assert calls[-1][3]['headers']['tr_id']==TR
    assert calls[-1][3]['params']['FID_DIV_CLS_CODE']=='1'
    assert calls[0][3]['json']['appkey']=='real-key'
    with pytest.raises(APIError):client.quote('000660')
    assert len(calls)==3


def test_finance_screen_and_independent_cache(monkeypatch):
    def unavailable(*args):raise APIError('미제공')
    for method in ('quote','history','investors'):monkeypatch.setattr(KIS,method,unavailable)
    monkeypatch.setattr(KRX,'latest',unavailable)
    calls=[]
    def income(self,code,division):
        assert self.key=='real-key'
        calls.append(division)
        return parse_income([{'stac_yymm':'202512','sale_account':'100','bsop_prti':'15','thtr_ntin':'10'}])
    monkeypatch.setattr(KISFinancials,'income',income)
    at=app(monkeypatch)
    at.secrets['kis_real']={'app_key':'real-key','app_secret':'real-secret'}
    login(at)
    at.sidebar.radio[0].set_value('기업 상세').run()
    assert not at.exception
    assert next(m.value for m in at.metric if m.label=='영업이익률')=='15.00%'
    assert calls==['0']
    at.run();assert calls==['0']
    at.radio(key='finance_period').set_value('분기 누적').run()
    assert not at.exception and calls==['0','1']
    assert at.session_state['kis'].key=='test-key'
