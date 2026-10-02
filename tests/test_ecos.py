import pandas as pd
import pytest
import requests
from core.ecos import ECOS,SERIES,parse_series
from core.api import APIError,KIS,KRX
from core.settings import read_settings
from core.macro_ui import previous_value
from test_system import app,login


def row(name,period,value):
    s=SERIES[name]
    return dict(STAT_CODE=s.table,ITEM_CODE1=s.item,UNIT_NAME=s.unit,TIME=period,DATA_VALUE=str(value))


def test_separate_ecos_key():
    s=read_settings({'krx':{'api_key':'krx'},'ecos':{'api_key':'ecos'}})
    assert s.ecos=='ecos' and s.krx=='krx'
    assert not read_settings({'api_key':'krx'}).ecos
    assert read_settings({'ECOS_API_KEY':'ecos'}).ecos=='ecos'
    assert read_settings({}, {'BOK_API_KEY':'ecos'}).ecos=='ecos'


def test_inflation_uses_calendar_not_row_offsets():
    rows=[row('cpi','202301',100),row('cpi','202401',103),row('cpi','202403',104),row('cpi','202503',106.08)]
    df=parse_series(rows,SERIES['cpi'])
    assert df.iloc[1]['값']==pytest.approx(3)
    assert pd.isna(df.iloc[2]['값'])
    assert df.iloc[3]['값']==pytest.approx(2)
    assert pd.isna(previous_value(df,SERIES['cpi']))


def test_gdp_rates_are_not_recalculated_and_delta_is_points():
    df=parse_series([row('gdp_qoq','2026Q1',-.2),row('gdp_qoq','2026Q2',.6)],SERIES['gdp_qoq'])
    assert df.iloc[-1]['값']==.6
    assert df.iloc[-1]['값']-previous_value(df,SERIES['gdp_qoq'])==pytest.approx(.8)


@pytest.mark.parametrize('change',[{'TIME':'202613'},{'UNIT_NAME':'원'},{'ITEM_CODE1':'other'},{'DATA_VALUE':'broken'}])
def test_wrong_series_rejected(change):
    r=row('cpi','202601',100);r.update(change)
    with pytest.raises(APIError):parse_series([r],SERIES['cpi'])


def test_http_and_error_messages_hide_key(monkeypatch):
    client=ECOS('private-key')
    def fail(*a,**k):raise requests.ConnectionError('https://private-key')
    monkeypatch.setattr(requests,'get',fail)
    with pytest.raises(APIError) as e:client.series('usd')
    assert 'private-key' not in str(e.value)
    r=requests.Response();r.status_code=200;r._content=b'{"RESULT":{"CODE":"INFO-100","MESSAGE":"private-key"}}'
    monkeypatch.setattr(requests,'get',lambda *a,**k:r)
    with pytest.raises(APIError) as e:client.series('usd')
    assert 'INFO-100' in str(e.value) and 'private-key' not in str(e.value)


def test_pagination_and_partial_response(monkeypatch):
    rows=[row('usd',d.strftime('%Y%m%d'),1000+i) for i,d in enumerate(pd.date_range('20220101',periods=1001))]
    client=ECOS('test');calls=[]
    def page(spec,start,end,first,last):calls.append(first);return rows[first-1:last],len(rows)
    monkeypatch.setattr(client,'_page',page)
    assert len(client.series('usd'))==1001 and calls==[1,1001]
    def partial(spec,start,end,first,last):return rows[:5],1001
    monkeypatch.setattr(client,'_page',partial)
    with pytest.raises(APIError):client.series('usd')


def test_macro_ui_all_series_and_failure_isolation(monkeypatch):
    def unavailable(*a):raise APIError('test unavailable')
    monkeypatch.setattr(KRX,'latest',unavailable);monkeypatch.setattr(KIS,'quote',unavailable)
    calls=[]
    def series(self,name):
        assert self.key=='ecos-test';calls.append(name)
        if name=='eur':raise APIError('test euro failure')
        if name=='cpi':return parse_series([row(name,'202508',100),row(name,'202608',102)],SERIES[name])
        if name.startswith('gdp'):return parse_series([row(name,'2026Q1',1),row(name,'2026Q2',2)],SERIES[name])
        return parse_series([row(name,'20261001',1000),row(name,'20261002',1010)],SERIES[name])
    monkeypatch.setattr(ECOS,'series',series)
    at=app(monkeypatch);at.secrets['ecos']={'api_key':'ecos-test'}
    login(at);assert not calls
    at.sidebar.radio[0].set_value('거시경제 · 시장환경').run()
    assert not at.exception and len(calls)==6
    assert any(m.value=='2.00%' for m in at.metric)
    assert any('euro failure' in w.value for w in at.warning)
    for name in ('cpi','usd','gdp_qoq'):
        at.selectbox(key='macro_indicator').set_value(name).run()
        assert not at.exception
    assert len(calls)==6
    at.sidebar.radio[0].set_value('연결 진단').run()
    assert not at.exception
    frame=at.dataframe[0].value
    assert '한국은행 ECOS 인증키' in frame['항목'].tolist()
