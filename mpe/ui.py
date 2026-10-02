from html import escape
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

COLORS=['#8B7AAC','#84A294','#87A3C4','#C6919A','#BEA774','#A8A3BD']
LABELS={'name':'기업','code':'종목코드','group':'비교군','market':'시장','process':'공정','category':'소부장','products':'제품 분류','business':'주력 사업','close':'종가(원)','market_cap':'시가총액(원)','revenue_yoy':'매출 YoY(%)','margin':'영업이익률(%)','roe':'ROE(%)','per':'PER(배)','pbr':'PBR(배)','fcf':'FCF(원)','fcf_yield':'FCF 수익률(%)','net_debt':'순차입금(원)','return_60':'60거래일 수익률(%)','foreign_net_20':'외국인 20일(원)','institution_net_20':'기관 20일(원)','foreign_strength':'외국인 수급 강도(%)','financial_date':'재무 기준일','price_date':'시세 기준일','period':'재무 기간','date':'기준일','source':'출처','published_at':'발표일','retrieved_at':'수집 시각','status':'상태','basis':'연결/별도','period_end':'회계기간 말','revenue':'매출액','operating_profit':'영업이익','parent_net_income':'지배주주 순이익','cfo':'영업현금흐름','capex':'설비·무형 투자','inventory':'재고','receivables':'매출채권','quantity':'보유수량','avg_price':'평균매입가','price':'현재가','cost':'매입금액','value':'평가금액','pnl':'평가손익','pnl_pct':'평가손익률(%)','weight':'주식 내 비중(%)','debt_ratio':'부채비율(%)','current_ratio':'유동비율(%)','inventory_days':'재고회전일수','receivable_days':'채권회전일수','interest_cover':'이자보상배율','volatility':'연환산 변동성(%)','mdd':'관측 최대낙폭(%)','ev':'기업가치 EV(원)','ev_ebitda':'EV/EBITDA(배)','dividend_yield':'과거 배당수익률(%)','high_252':'252거래일 최고 수정주가','low_252':'252거래일 최저 수정주가','from_high':'고점 대비(%)','turnover_20':'20일 평균 거래대금(원)'}

def style():
    st.markdown('''<style>
    .stApp{background:#F6F5F2;color:#354456}
    [data-testid="stSidebar"]{background:#EFEDF4;border-right:1px solid #E4E1EB}
    .block-container{padding-top:2rem;padding-bottom:2rem;max-width:1480px}
    h1,h2,h3{color:#354456;letter-spacing:-.035em!important}
    h1{font-size:2rem!important} h2{font-size:1.45rem!important} h3{font-size:1.1rem!important}
    [data-testid="stMetric"]{background:#FFFEFD;border:1px solid #E6E5E9;border-radius:14px;padding:18px}
    [data-testid="stMetricValue"]{color:#465266;font-variant-numeric:tabular-nums}
    [data-testid="stMetricLabel"]{color:#657084}
    [data-testid="stVerticalBlockBorderWrapper"]>div{border-radius:14px!important}
    .mpe-eyebrow{font-size:11px;letter-spacing:2px;color:#75658F;font-weight:600;margin-bottom:7px}
    .mpe-sub{color:#657084;font-size:14px;margin-bottom:20px}
    .mpe-tag{display:inline-block;padding:4px 10px;background:#E5EEE8;color:#426A59;border-radius:6px;font-size:12px;margin:3px}
    .mpe-step{background:#FFFEFD;border:1px solid #E6E5E9;border-radius:12px;padding:16px;margin:10px 0}
    .mpe-step small{color:#75658F;letter-spacing:1px}
    .mpe-step p{color:#657084;font-size:13px;margin:5px 0 0}
    button[kind="primary"]{background:#75658F;border-color:#75658F;color:white}
    div[data-testid="stAlert"]{border-radius:10px}
    </style>''',unsafe_allow_html=True)

def heading(title,sub=''):
    st.markdown('<div class="mpe-eyebrow">LEE JONG WAN · SEMICONDUCTOR RESEARCH</div>',unsafe_allow_html=True)
    st.title(title)
    if sub:st.markdown(f'<div class="mpe-sub">{escape(sub)}</div>',unsafe_allow_html=True)

def fmt(v,unit='',scale=1):
    if v is None or pd.isna(v):return '자료 없음'
    return f'{v/scale:,.1f}{unit}'

def cards(items):
    for col,(label,value) in zip(st.columns(len(items)),items):
        with col:st.metric(label,value)

def table(df,cols=None):
    if df.empty:st.info('아직 수집된 자료가 없습니다. 데이터 관리에서 API 조회 또는 CSV 업로드를 해주세요.');return
    if cols:df=df[[x for x in cols if x in df]].copy()
    configs={LABELS.get(c,c):st.column_config.NumberColumn(format='%.2f') for c in df.select_dtypes(include='number').columns}
    st.dataframe(df.rename(columns=LABELS),hide_index=True,width='stretch',column_config=configs)

def plot(fig):
    fig.update_layout(paper_bgcolor='#FFFEFD',plot_bgcolor='#FFFEFD',font=dict(color='#465266',family='Arial, sans-serif'),colorway=COLORS,margin=dict(l=15,r=15,t=35,b=15),legend=dict(orientation='h',y=1.15),hovermode='x unified')
    fig.update_xaxes(gridcolor='#F0EDF2');fig.update_yaxes(gridcolor='#F0EDF2')
    st.plotly_chart(fig,width='stretch',config={'displaylogo':False})

def provenance(df):
    if not df.empty:
        fields=[x for x in ['code','date','period_end','period_type','basis','source','published_at','retrieved_at','status'] if x in df]
        with st.expander('기준일 · 출처 · 데이터 상태'):table(df[fields].tail(100))
