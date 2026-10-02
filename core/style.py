import pandas as pd
import streamlit as st

LABELS={'quote_status':'조회 상태','stage':'공정 구분','process':'세부 공정','category':'소부장·서비스','group':'유사 제품 비교군','business':'주력사업·제품','products':'적용 제품','code':'종목코드','name':'기업','market':'시장','price':'가격(원)','change_pct':'전일 대비 등락률(%)','volume':'거래량(주)','turnover':'거래대금(원)','market_cap':'시가총액(원)','shares':'상장주식수','source':'출처','asof':'자료 기준','fetched':'수집시각','per':'PER(배)','pbr':'PBR(배)','eps':'EPS(원)','bps':'BPS(원)','foreign_pct':'외국인 소진율(%)','high_52':'52주 최고가(원)','low_52':'52주 최저가(원)','quantity':'보유수량','avg_price':'평균매입가(원)','cost':'매입금액(원)','value':'평가금액(원)','pnl':'평가손익(원)','pnl_pct':'평가손익률(%)','weight':'주식 내 비중(%)','date':'날짜','open':'시가','high':'고가','low':'저가','close':'종가'}

def setup():
    st.markdown('''<style>
    .stApp{background:#F7F6F3;color:#38485D}
    [data-testid="stSidebar"]{background:#EEEBF3;border-right:1px solid #E0DDE8}
    .block-container{max-width:1450px;padding-top:2.4rem}
    h1,h2,h3{color:#38485D;letter-spacing:-.035em}
    h1{font-size:2rem!important} h2{font-size:1.4rem!important}
    [data-testid="stMetric"]{background:#FFFEFC;border:1px solid #E7E3EC;border-radius:16px;padding:18px}
    [data-testid="stMetricValue"]{color:#495C70;font-variant-numeric:tabular-nums}
    [data-testid="stMetricLabel"]{color:#677488}
    .eyebrow{color:#827193;letter-spacing:2px;font-size:11px;font-weight:600}
    </style>''',unsafe_allow_html=True)

def heading(title,subtitle):
    st.markdown('<div class="eyebrow">LEE JONG WAN · SEMICONDUCTOR RESEARCH</div>',unsafe_allow_html=True)
    st.title(title);st.caption(subtitle)

def fmt(value,unit='',div=1):
    if value is None or pd.isna(value):return '미제공'
    return f'{value/div:,.2f}{unit}'

def cards(items):
    for c,(label,value) in zip(st.columns(len(items)),items):c.metric(label,value)

def table(frame):
    frame=frame.rename(columns=LABELS)
    st.dataframe(frame,hide_index=True,width='stretch',column_config={c:st.column_config.NumberColumn(format='localized') for c in frame.select_dtypes('number').columns})

def plot(fig):
    fig.update_layout(paper_bgcolor='#FFFEFC',plot_bgcolor='#FFFEFC',font=dict(color='#495C70'),colorway=['#8E7DAB','#8AAE9F','#9CB3CB'],margin=dict(l=10,r=10,t=35,b=10),hovermode='x unified')
    fig.update_xaxes(gridcolor='#EDEAF1');fig.update_yaxes(gridcolor='#EDEAF1')
    st.plotly_chart(fig,width='stretch',config={'displaylogo':False})
