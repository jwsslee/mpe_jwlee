import numpy as np
import pandas as pd


def ratio(a,b,scale=1):
    if pd.isna(a) or pd.isna(b) or b<=0: return np.nan
    return a/b*scale


def financial_metrics(df, code, asof, basis='CFS'):
    f=df[(df.code==code)&(df.basis==basis)&(df.published_at<=str(asof))&(df.period_end<=str(asof))].copy()
    if f.empty: return {}
    f=f.sort_values('published_at').drop_duplicates(['period_end','period_type'],keep='last')
    q=f[f.period_type=='Q'].sort_values('period_end')
    annual=f[f.period_type=='FY'].sort_values('period_end')
    if len(q)>=4:
        latest=q.tail(4)
        periods=pd.PeriodIndex(latest.period_end,freq='Q')
        continuous=all(periods[i].ordinal-periods[i-1].ordinal==1 for i in range(1,4))
    else: continuous=False
    if continuous and (annual.empty or q.iloc[-1].period_end>=annual.iloc[-1].period_end):
        latest=q.tail(4); r=latest.iloc[-1]; label='TTM'; balance_prev=q[q.period_end==str((pd.Period(r.period_end,freq='Q')-4).end_time.date())]
    elif not annual.empty:
        latest=annual.tail(1); r=latest.iloc[-1]; label='FY'; balance_prev=annual[annual.period_end==str((pd.Timestamp(r.period_end)-pd.DateOffset(years=1)).date())]
    else:
        return {'financial_date':q.iloc[-1].period_end if len(q) else '', 'period':'분기 자료 부족'}
    m={c:latest[c].sum(min_count=len(latest)) for c in ['revenue','gross_profit','operating_profit','net_income','parent_net_income','cfo','capex','interest_expense','cogs','rd','dividend','ebitda']}
    m.update({c:r[c] for c in ['equity','parent_equity','assets','liabilities','current_assets','current_liabilities','debt','cash','inventory','receivables','noncontrolling_interest','preferred_value']})
    m.update(financial_date=r.period_end,period=label,financial_source=r.source)
    m['margin']=ratio(m['operating_profit'],m['revenue'],100)
    m['gross_margin']=ratio(m['gross_profit'],m['revenue'],100)
    m['fcf']=m['cfo']-m['capex'];m['net_debt']=m['debt']-m['cash']
    m['debt_ratio']=ratio(m['liabilities'],m['equity'],100)
    m['current_ratio']=ratio(m['current_assets'],m['current_liabilities'],100)
    m['interest_cover']=ratio(m['operating_profit'],m['interest_expense'])
    m['cash_conversion']=ratio(m['cfo'],m['net_income'])
    m['rd_ratio']=ratio(m['rd'],m['revenue'],100)
    m['roe']=np.nan;m['roa']=np.nan;m['inventory_days']=np.nan;m['receivable_days']=np.nan
    if len(balance_prev):
        p=balance_prev.iloc[-1]
        m['roe']=ratio(m['parent_net_income'],(r.parent_equity+p.parent_equity)/2,100)
        m['roa']=ratio(m['net_income'],(r.assets+p.assets)/2,100)
        m['inventory_days']=ratio((r.inventory+p.inventory)/2,m['cogs'],365)
        m['receivable_days']=ratio((r.receivables+p.receivables)/2,m['revenue'],365)
    old_end=str((pd.Timestamp(r.period_end)-pd.DateOffset(years=1)).date())
    prior=f[(f.period_end==old_end)&(f.period_type==r.period_type)]
    m['revenue_yoy']=ratio(r.revenue-prior.iloc[-1].revenue,prior.iloc[-1].revenue,100) if len(prior) else np.nan
    m['growth_basis']='최근 단독 분기 YoY' if label=='TTM' else '연간 YoY'
    return m


def price_metrics(df,code,asof):
    p=df[(df.code==code)&(df.date<=str(asof))].sort_values('date')
    if p.empty:return {}
    r=p.iloc[-1];m={'close':r.close,'market_cap':r.market_cap,'price_date':r.date,'price_source':r.source,'shares':r.shares}
    adj=p.adjusted_close
    for n in [20,60,120,252]:
        window=adj.tail(n+1)
        m[f'return_{n}']=ratio(window.iloc[-1]-window.iloc[0],window.iloc[0],100) if len(window)==n+1 and window.notna().all() else np.nan
    m['high_252']=adj.tail(252).max() if len(adj)>=252 and adj.tail(252).notna().all() else np.nan
    m['low_252']=adj.tail(252).min() if len(adj)>=252 and adj.tail(252).notna().all() else np.nan
    m['from_high']=ratio(r.adjusted_close-m['high_252'],m['high_252'],100)
    m['turnover_20']=p.turnover.tail(20).mean() if len(p)>=20 else np.nan
    w=adj.tail(252)
    m['volatility']=w.pct_change(fill_method=None).std()*np.sqrt(252)*100 if len(w)>=60 and w.notna().all() else np.nan
    m['mdd']=((w/w.cummax()-1).min()*100) if len(w)>=60 and w.notna().all() else np.nan
    return m


def snapshot(master,data,asof,basis='CFS'):
    rows=[]
    for _,c in master.iterrows():
        m=c.to_dict();m.update(financial_metrics(data['financials'],c.code,asof,basis));m.update(price_metrics(data['prices'],c.code,asof))
        m['per']=ratio(m.get('market_cap',np.nan),m.get('parent_net_income',np.nan))
        m['ev']=m.get('market_cap',np.nan)+m.get('net_debt',np.nan)+m.get('noncontrolling_interest',np.nan)+m.get('preferred_value',np.nan)
        m['ev_ebitda']=ratio(m['ev'],m.get('ebitda',np.nan)) if m['ev']>0 else np.nan
        m['dividend_yield']=ratio(m.get('dividend',np.nan),m.get('market_cap',np.nan),100)
        m['pbr']=ratio(m.get('market_cap',np.nan),m.get('parent_equity',np.nan))
        m['fcf_yield']=ratio(m.get('fcf',np.nan),m.get('market_cap',np.nan),100)
        fl=data['flows'];fl=fl[(fl.code==c.code)&(fl.date<=str(asof))].sort_values('date').tail(20)
        for key in ['foreign_net','institution_net']:
            m[key+'_20']=fl[key].sum(min_count=20) if len(fl)==20 else np.nan
        prices=data['prices']; prices=prices[(prices.code==c.code)&prices.date.isin(fl.date)]
        cap=prices.market_cap.mean() if len(prices)==20 and prices.market_cap.notna().all() else np.nan
        m['foreign_strength']=ratio(m['foreign_net_20'],cap,100)
        rows.append(m)
    out=pd.DataFrame(rows)
    for col in ['margin','roe','revenue_yoy','fcf','net_debt','financial_date','period','price_date','return_60','close','market_cap']:
        if col not in out:out[col]=np.nan
    return out


def momentum_backtest(prices,codes,lookback=60,topn=3,cost_bps=15):
    """End of day t signal, execute at t+1 close; first earned return t+2.
    Strict common observation dates, no implicit forward fill. User-selected universe.
    """
    p=prices[prices.code.isin(codes)].pivot(index='date',columns='code',values='adjusted_close').sort_index()
    p=p.dropna(how='any')
    if len(p)<lookback+5:raise ValueError('공통 날짜의 수정주가가 충분하지 않습니다.')
    ret=p.pct_change(fill_method=None).fillna(0)
    momentum=p/p.shift(lookback)-1
    last=np.zeros(len(p.columns));target=last.copy();nav=1.;bench=1.;result=[]
    for i in range(lookback+2,len(p)):
        # signal t=i-2, execute t=i-1, earn close-to-close return on day i
        signal_idx=i-2
        if signal_idx==lookback or pd.Timestamp(p.index[signal_idx]).month!=pd.Timestamp(p.index[signal_idx-1]).month:
            ranks=momentum.iloc[signal_idx].dropna().nlargest(min(topn,len(codes))).index
            target=np.array([1/len(ranks) if c in ranks else 0 for c in p.columns])
        turnover=np.abs(target-last).sum()
        daily=float(np.dot(target,ret.iloc[i].values))
        nav=nav*(1-turnover*cost_bps/10000)*(1+daily)
        weights=target*(1+ret.iloc[i].values)
        if weights.sum()>0:weights=weights/weights.sum()
        last=weights.copy();target=weights.copy()
        bench*=1+ret.iloc[i].mean()
        result.append({'date':p.index[i],'strategy':nav*100,'equal_weight':bench*100})
    return pd.DataFrame(result)
