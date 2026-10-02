"""Macro view using independently cached official ECOS series."""
import pandas as pd
import plotly.express as px
import streamlit as st
from .ecos import SERIES,period_label
from .api import now
from .style import heading,fmt,table,plot


def previous_value(df,spec):
    latest=df.iloc[-1]
    if spec.cycle=='D':return df.iloc[-2]['값'] if len(df)>1 else float('nan')
    p=latest.period
    if spec.cycle=='M':previous=(pd.Period(p[:4]+'-'+p[4:],freq='M')-1).strftime('%Y%m')
    else:
        year=int(p[:4]);quarter=int(p[-1])-1
        previous=f'{year if quarter else year-1}Q{quarter or 4}'
    row=df.loc[df.period==previous,'값']
    return row.iloc[0] if len(row) else float('nan')


def macro_page(settings,client,load,report,refresh):
    heading('거시경제 · 시장환경','한국은행 ECOS · 국내 성장률·물가·환율 자동 조회')
    st.caption('월·분기 지표는 발표된 최신 기간을 표시합니다. 수집시각과 통계 기준기간은 서로 다르며, 과거 통계는 수정될 수 있습니다.')
    if not settings.ecos:
        st.info('Streamlit Secrets에 [ecos] api_key를 설정하고 앱을 다시 시작하세요.')
        st.code('[ecos]\napi_key = "발급받은 ECOS 인증키"',language='toml');return
    force=refresh('macro')
    entries={}
    with st.spinner('ECOS 성장률·물가·환율 조회 중…'):
        for name in SERIES:
            entries[name]=load('ECOS '+name,lambda n=name:client.series(n),21600,force)
    st.subheader('최신 발표 지표')
    summary=[]
    columns=st.columns(3)
    for i,(name,spec) in enumerate(SERIES.items()):
        e=entries[name]
        with columns[i%3]:
            if 'data' not in e:
                st.metric(spec.name,'미제공');report(e,spec.name);continue
            df=e['data'];last=df.iloc[-1];v=last['값'];prev=previous_value(df,spec)
            unit='원' if spec.cycle=='D' else '%';delta_unit='원' if spec.cycle=='D' else '%p'
            delta=v-prev
            st.metric(spec.name,fmt(v,unit),delta=fmt(delta,delta_unit) if pd.notna(delta) else None,delta_color='off')
            st.caption('기준 '+last['기준기간']+' · '+('직전 제공일 대비' if spec.cycle=='D' else '직전 분기 대비 변화' if spec.cycle=='Q' else '직전 월 대비 변화'))
            report(e,spec.name)
            summary.append({'지표':spec.name,'기준기간':last['기준기간'],'값':v,'단위':unit,'직전 기간 대비 변화':delta,'변화 단위':delta_unit})
    st.subheader('기간별 추이')
    available=[name for name,e in entries.items() if 'data' in e]
    if not available:return
    name=st.selectbox('비교할 지표',available,format_func=lambda n:SERIES[n].name,key='macro_indicator')
    years=st.radio('조회 기간',[1,3,5],index=2,format_func=lambda n:f'최근 {n}년',horizontal=True,key='macro_years')
    spec=SERIES[name];df=entries[name]['data'].copy()
    cutoff=pd.Timestamp(now().date())-pd.DateOffset(years=years)
    # Use period-end dates only to select the window; labels remain actual months/quarters.
    if spec.cycle=='Q':dates=pd.PeriodIndex(df.period,freq='Q').to_timestamp(how='end')
    elif spec.cycle=='M':dates=pd.to_datetime(df.period,format='%Y%m')+pd.offsets.MonthEnd(0)
    else:dates=pd.to_datetime(df.period,format='%Y%m%d')
    df=df.loc[dates>=cutoff].copy()
    st.caption(spec.note)
    if df.empty:st.info('선택 기간의 통계가 없습니다.')
    else:
        # Reindex monthly/quarterly periods so gaps are not bridged by a line.
        chart=df[['period','값']].copy()
        if spec.cycle in ('M','Q'):
            freq=spec.cycle
            idx=pd.period_range(pd.Period(df.period.iloc[0] if freq=='Q' else df.period.iloc[0][:4]+'-'+df.period.iloc[0][4:],freq=freq),
                                pd.Period(df.period.iloc[-1] if freq=='Q' else df.period.iloc[-1][:4]+'-'+df.period.iloc[-1][4:],freq=freq),freq=freq)
            periods=[str(p) if freq=='Q' else p.strftime('%Y%m') for p in idx]
            chart=chart.set_index('period').reindex(periods).rename_axis('period').reset_index()
        chart['기준기간']=chart.period.map(lambda p:period_label(p,spec.cycle))
        chart=chart.rename(columns={'값':spec.name})
        fig=px.line(chart,x='기준기간',y=spec.name,markers=spec.cycle!='D',labels={spec.name:'원' if spec.cycle=='D' else '%'})
        fig.update_traces(connectgaps=False)
        plot(fig)
        with st.expander('기간별 수치 · 원자료'):
            view=df.drop(columns='period').rename(columns={'값':'환율(원)' if spec.cycle=='D' else '성장률(%)' if spec.cycle=='Q' else '물가상승률(%)','원자료':'ECOS 원자료 ('+spec.unit+')'})
            table(view.iloc[::-1])
            st.download_button('이 지표 CSV 다운로드',view.to_csv(index=False).encode('utf-8-sig'),file_name=f'ecos_{name}.csv',mime='text/csv')
    with st.expander('지표 읽는 방법 · 출처'):
        st.markdown('성장률·물가상승률의 **변화는 %p**로 표시합니다. 예를 들어 2%에서 3%가 되면 +1%p입니다. 전분기 GDP 성장률은 연율이 아닙니다. 물가상승률은 공개 CPI로 계산하므로 반올림에 따라 공표 상승률과 소수점 차이가 날 수 있습니다.')
        st.markdown('환율 상승은 수출대금과 수입 원가에 서로 다른 영향을 줍니다. 특정 기업에 무조건 호재나 악재로 분류하지 않습니다. 이 화면은 국내 경제통계이며 주가지수는 포함하지 않습니다.')
        table(pd.DataFrame([{'지표':s.name,'통계표':s.table,'항목':s.item,'해석':s.note} for s in SERIES.values()]))
        st.markdown('[한국은행 ECOS](https://ecos.bok.or.kr/) · [공식 Open API](https://ecos.bok.or.kr/api/)')
