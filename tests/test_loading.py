from datetime import date
import pandas as pd
from mpe.loading import load_prices
from mpe.data import empty,validate
from mpe.connectors import KRX,PublicData,APIError
from streamlit.testing.v1 import AppTest
from pathlib import Path


def fixture_price(code='353200'):
    return validate('prices',pd.DataFrame([dict(code=code,date='2026-10-01',close=100,market_cap=1000,source='test fixture',retrieved_at='2026-10-02',status='reported')]))


def test_market_failure_does_not_discard_success(monkeypatch):
    def daily(self,day,market,codes):
        if market=='KOSDAQ':raise APIError('서비스 승인 확인')
        return fixture_price()
    monkeypatch.setattr(KRX,'daily',daily)
    master=pd.DataFrame([{'code':'353200','market':'KOSPI'},{'code':'000001','market':'KOSDAQ'}])
    result,logs=load_prices(empty()['prices'],master,date(2026,10,2),'test')
    assert len(result)==1 and any('승인' in m for m in logs)


def test_public_history_without_krx(monkeypatch):
    monkeypatch.setattr(PublicData,'prices',lambda *args:fixture_price())
    result,logs=load_prices(empty()['prices'],pd.DataFrame(),date(2026,10,2),public_key='test',code='353200')
    assert len(result)==1 and any('반영' in m for m in logs)


def test_overview_auto_load_and_no_repeated_calls(monkeypatch):
    monkeypatch.chdir(Path(__file__).resolve().parents[1]);monkeypatch.delenv('APP_PASSWORD',raising=False)
    calls=[]
    def daily(self,day,market,codes):
        calls.append(market)
        return fixture_price()
    monkeypatch.setattr(KRX,'daily',daily)
    at=AppTest.from_file(Path(__file__).resolve().parents[1]/'app.py',default_timeout=60)
    at.secrets={'APP_PASSWORD':'test-password','KRX_API_KEY':'test-key'}
    at.run();at.text_input[0].set_value('test-password');at.button[0].click().run()
    assert not at.exception
    assert at.metric[1].value=='1개'
    assert len(calls)==2
    at.run()
    assert len(calls)==2
    assert not at.exception
