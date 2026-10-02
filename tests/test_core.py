import pandas as pd
import numpy as np
import pytest
from mpe.data import companies,empty,validate,merge,demo_data,export_bundle,import_bundle
from mpe.analytics import financial_metrics,snapshot,momentum_backtest
from mpe.connectors import KISDemo,APIError


def test_seed_unique():
    c=companies();assert len(c)==72;assert c.code.is_unique;assert c.code.str.fullmatch(r'\d{6}').all()


def test_validation_keeps_missing_rejects_cumulative():
    f=validate('prices',pd.DataFrame([dict(code='5930',date='2026-01-02',close='10,000',source='test')]))
    assert f.code.iloc[0]=='005930';assert np.isnan(f.adjusted_close.iloc[0]);assert f.close.iloc[0]==10000
    with pytest.raises(ValueError):validate('financials',pd.DataFrame([dict(code='005930',period_end='2025-06-30',period_type='YTD',basis='CFS',published_at='2025-08-15',source='test')]))


def finance():
    rows=[]
    for i,d in enumerate(pd.date_range('2024-03-31','2025-06-30',freq='QE')):
        rows.append(dict(code='005930',period_end=str(d.date()),period_type='Q',basis='CFS',published_at=str((d+pd.Timedelta(days=45)).date()),source='test',revenue=100,operating_profit=10,parent_net_income=8,parent_equity=100,cfo=12,capex=3))
    return validate('financials',pd.DataFrame(rows))


def test_ttm_asof_revisions_and_missing():
    f=finance();m=financial_metrics(f,'005930','2025-06-01')
    assert m['revenue']==400;assert m['fcf']==36;assert m['financial_date']=='2025-03-31';assert m['roe']==32
    assert financial_metrics(f.iloc[[0,2,3,4]],'005930','2025-06-01')['period']=='분기 자료 부족'
    revision=f.iloc[4:5].copy();revision['revenue']=900;revision['published_at']='2025-09-01'
    both=merge(f,revision,'financials')
    assert financial_metrics(both,'005930','2025-06-01')['revenue']==400
    assert financial_metrics(both,'005930','2025-10-01')['revenue']==1200


def test_demo_archive():
    d=demo_data(companies());assert len(d['prices'])>100
    restored=import_bundle(export_bundle(d));assert len(restored['prices'])==len(d['prices'])
    s=snapshot(companies(),restored,'2026-09-30');assert s.margin.notna().sum()==12


def test_kis_pagination_no_double_summary(monkeypatch):
    k=KISDemo('key','secret','12345678','01');calls=[]
    pages=[({'rt_cd':'0','output1':[{'pdno':'005930','hldg_qty':'2','evlu_amt':'1000'}],'output2':[{'tot_evlu_amt':'5000'}],'ctx_area_fk100':'a','ctx_area_nk100':'b'},{'tr_cont':'M'}),({'rt_cd':'0','output1':[{'pdno':'000660','hldg_qty':'1','evlu_amt':'2000'},{'pdno':'000001','hldg_qty':'0'}],'output2':[{'tot_evlu_amt':'5000'}]}, {'tr_cont':'D'})]
    def get(path,tr,params,cont=''):
        calls.append((tr,cont));return pages.pop(0)
    monkeypatch.setattr(k,'get',get);monkeypatch.setattr('mpe.connectors.time.sleep',lambda x:None)
    h,s,_=k.balance();assert len(h)==2;assert s['tot_evlu_amt']==5000;assert calls==[('VTTC8434R',''),('VTTC8434R','N')]
    assert np.isnan(s['dnca_tot_amt'])


def test_partial_balance_refused(monkeypatch):
    k=KISDemo('key','secret','12345678','01')
    monkeypatch.setattr(k,'get',lambda *a:({'output1':[],'output2':[{}]}, {'tr_cont':'M'}))
    with pytest.raises(APIError,match='연속조회'):k.balance()


def test_backtest_uses_prior_signal():
    rows=[];dates=pd.bdate_range('2025-01-01',periods=90)
    for i,d in enumerate(dates):
        for code,value in [('000001',100+i),('000002',100-i*.2)]:rows.append(dict(code=code,date=str(d.date()),close=value,adjusted_close=value,source='test'))
    p=validate('prices',pd.DataFrame(rows));result=momentum_backtest(p,['000001','000002'],20,1,0)
    first=22;assert result.strategy.iloc[0]==pytest.approx(100*(100+first)/(100+first-1))
    changed=p.copy();changed.loc[changed.date>str(dates[50].date()),'adjusted_close']*=2
    result2=momentum_backtest(changed,['000001','000002'],20,1,0)
    pd.testing.assert_frame_equal(result[result.date<=str(dates[50].date())],result2[result2.date<=str(dates[50].date())])
