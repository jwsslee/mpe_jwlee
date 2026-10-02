import pandas as pd
from core.api import KIS,KRX,APIError
from test_system import app,login


def test_screens_share_kis_change_and_refresh(monkeypatch):
    calls=[]
    def quote(self,code):
        calls.append(code)
        pct=5.+calls.count(code)-1
        return dict(code=code,price=100,change_pct=pct,turnover=1000,market_cap=10000,volume=10,source='KIS',asof='조회 시점',fetched='2026-10-02T15:00:00+09:00')
    monkeypatch.setattr(KIS,'quote',quote)
    monkeypatch.setattr(KRX,'latest',lambda *a:pd.DataFrame([dict(code='353200',name='대덕전자',price=90,change_pct=1,source='KRX',asof='2026-10-01',fetched='2026-10-02')]))
    def empty(*a):raise APIError('test: unavailable')
    monkeypatch.setattr(KIS,'history',empty);monkeypatch.setattr(KIS,'investors',empty)
    at=login(app(monkeypatch))
    assert not at.exception
    def market_value():
        frame=next(d.value for d in at.dataframe if '조회 상태' in d.value.columns)
        return frame.loc[frame['종목코드']=='353200','전일 대비 등락률(%)'].iloc[0]
    assert market_value()==5
    at.sidebar.radio[0].set_value('기업 상세').run()
    assert next(m.value for m in at.metric if m.label=='전일 대비 등락률')=='5.00%'
    assert calls.count('353200')==1
    at.button(key='refresh_company').click().run()
    assert next(m.value for m in at.metric if m.label=='전일 대비 등락률')=='6.00%'
    at.sidebar.radio[0].set_value('시장 · 관심기업').run()
    assert market_value()==6 and calls.count('353200')==2
    assert not at.exception


def test_kis_failure_never_substitutes_krx_rate(monkeypatch):
    monkeypatch.setattr(KRX,'latest',lambda *a:pd.DataFrame([dict(code='353200',name='대덕전자',price=90,change_pct=1,source='KRX',asof='2026-10-01',fetched='2026-10-02')]))
    def failure(*a):raise APIError('KIS unavailable')
    monkeypatch.setattr(KIS,'quote',failure)
    at=login(app(monkeypatch))
    assert not at.exception and at.error
    assert not any('조회 상태' in d.value.columns for d in at.dataframe)
