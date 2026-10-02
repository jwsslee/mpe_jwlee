"""이종완의 반도체 소부장 주식투자 분석 대시보드."""
from datetime import date, datetime, timedelta, timezone
from html import escape
from io import BytesIO
from pathlib import Path
import hashlib
import hmac
import os
import time
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
from mpe.loading import load_prices
from mpe.config import resolve
from mpe.data import companies,empty,demo_data,validate,merge,SCHEMAS,export_bundle,import_bundle
from mpe.analytics import snapshot,ratio,momentum_backtest
from mpe.connectors import KISDemo,KRX,PublicData,APIError,number
from mpe.ui import style,heading,cards,fmt,table,plot,provenance,COLORS,LABELS

st.set_page_config(page_title='이종완 · 반도체 소부장',page_icon='◈',layout='wide')
style()

def secret_info(section,key,env=''):
    try:
        return resolve(st.secrets,section,key,os.environ,env)
    except FileNotFoundError:
        return resolve({},section,key,os.environ,env)


def secret(section,key,env=''):
    return secret_info(section,key,env)[0]

def auth():
    password=secret('','APP_PASSWORD','APP_PASSWORD')
    if not password:return False
    if st.session_state.get('authenticated'):return True
    heading('투자연구실 로그인','개인용 데이터와 모의투자 계좌를 보호합니다.')
    with st.form('login'):
        value=st.text_input('접속 비밀번호',type='password')
        submit=st.form_submit_button('입장',type='primary')
    if submit:
        if time.time()<st.session_state.get('retry_after',0):st.error('잠시 후 다시 시도하세요.')
        elif hmac.compare_digest(value.encode(),password.encode()):
            st.session_state.authenticated=True;st.rerun()
        else:
            st.session_state.retry_after=time.time()+3;st.error('비밀번호를 확인하세요.')
    st.stop()

trusted=auth()
master=companies()
if 'real_data' not in st.session_state:st.session_state.real_data=empty()
if 'demo_data' not in st.session_state:st.session_state.demo_data=None
with st.sidebar:
    st.markdown('### ◈ 종완의 투자연구실')
    st.caption('SEMICONDUCTOR RESEARCH')
    pages=['종합 현황','공정별 탐색','기업 분석','동종 기업 비교','수급 · 주가','산업 · 사업 지표','공시 · 위험 점검','관심종목 · 투자 노트','시나리오 · 전략 검증','모의투자 계좌','데이터 관리']
    page=st.radio('WORKSPACE',pages,label_visibility='collapsed')
    st.divider()
    demo=st.toggle('가상 예시 데이터 보기',value=False)
    if demo:
        if st.session_state.demo_data is None:st.session_state.demo_data=demo_data(master)
        st.caption('일부 12개 기업 · 실제 시세 아님')
    asof=st.date_input('분석 기준일',value=date.today())
    basis=st.selectbox('재무 기준',['CFS','OFS'],format_func=lambda x:'연결' if x=='CFS' else '별도')
    st.caption('KRX · 공공데이터 · 한국투자증권\n\nOpenDART 직접 접속 없음')
    if trusted and st.button('로그아웃'):
        st.session_state.clear();st.rerun()
D=st.session_state.demo_data if demo else st.session_state.real_data
if demo:st.warning('가상 예시 모드 — 가격·재무·수급 수치는 전부 시연용입니다. 실제 API 데이터와 분리됩니다.')
if not trusted:st.caption('공개 미리보기 · 서버에 저장된 API 키는 사용하지 않습니다. 개인 배포는 APP_PASSWORD를 설정하세요.')
S=snapshot(master,D,asof,basis)


def pick(key='company'):
    return st.selectbox('기업 선택',master.code.tolist(),format_func=lambda c:f"{master.set_index('code').loc[c,'name']} · {c}",key=key)

def source_api(section,key,env):
    own=st.session_state.get('credentials',{}).get(section,{}).get(key,'')
    return own or (secret(section,key,env) if trusted else '')

def connection_diagnostics(only_kis=False):
    fields=[('kis','app_key','KIS_APP_KEY','모의투자 KEY'),
            ('kis','app_secret','KIS_APP_SECRET','모의투자 SECRET'),
            ('kis','cano','KIS_CANO','계좌 앞 8자리'),
            ('kis','acnt_prdt_cd','KIS_ACNT_PRDT_CD','계좌 상품코드'),
            ('krx','api_key','KRX_API_KEY','KRX 인증키'),
            ('public_data','service_key','PUBLIC_DATA_KEY','공공데이터 인증키')]
    rows=[]
    for section,key,env,label in fields:
        if only_kis and section!='kis':continue
        own=st.session_state.get('credentials',{}).get(section,{}).get(key,'')
        value,where=(own,'현재 세션') if own else secret_info(section,key,env)
        state='인식됨' if value else '미설정'
        if value and not own and not trusted:state='로그인 필요'
        if not value and key=='acnt_prdt_cd':state='기본값 01';where='기본값'
        rows.append({'항목':label,'설정 상태':state,'읽은 위치':where or '—'})
    table(pd.DataFrame(rows))
    st.caption('설정 이름의 인식 결과입니다. 키의 유효성·서비스 승인은 실제 조회에서 확인합니다. 값은 표시하지 않습니다.')


def kis_client():
    config=[source_api('kis','app_key','KIS_APP_KEY'),source_api('kis','app_secret','KIS_APP_SECRET'),source_api('kis','cano','KIS_CANO'),source_api('kis','acnt_prdt_cd','KIS_ACNT_PRDT_CD') or '01']
    digest=hashlib.sha256('|'.join(config).encode()).hexdigest()
    if st.session_state.get('kis_config')!=digest:
        st.session_state.kis_client=KISDemo(*config);st.session_state.kis_config=digest
        st.session_state.pop('portfolio',None)
    return st.session_state.kis_client

def save_data(kind,frame):
    if frame.empty:st.info('조회 결과가 없습니다. 휴장일·조회 기간·권한을 확인하세요.');return
    st.session_state.real_data[kind]=merge(st.session_state.real_data[kind],frame,kind)
    st.success(f'{len(frame):,}행을 실제 데이터에 반영했습니다.')

def attempt(func):
    try:return func()
    except (APIError,ValueError,KeyError) as e:
        st.error(str(e) if isinstance(e,(APIError,ValueError)) else 'API 응답 필드가 예상과 다릅니다.');return None

def price_chart(code):
    p=D['prices'];p=p[(p.code==code)&(p.date<=str(asof))].sort_values('date').copy()
    if p.empty:st.info('주가 자료를 먼저 수집해 주세요.');return
    adj=p.adjusted_close.notna().all()
    y='adjusted_close' if adj else 'close'
    st.caption('수정주가 · 배당 재투자 미포함' if adj else '원주가: 기업행사 미조정. 수익률·백테스트에는 사용하지 않습니다.')
    for n in [20,60,120]:p[f'MA{n}']=p[y].rolling(n).mean()
    plot(px.line(p,x='date',y=[y,'MA20','MA60','MA120'],labels={'date':'날짜','value':'원','variable':'가격'}))
    provenance(p)

def price_loader(code=None):
    global S
    if demo:return
    krx=source_api('krx','api_key','KRX_API_KEY')
    public=source_api('public_data','service_key','PUBLIC_DATA_KEY')
    # A changed key permits a fresh attempt without storing credentials in the marker.
    identity=hashlib.sha256((krx+'|'+public).encode()).hexdigest()
    marker=(str(asof),code,identity)
    attempts=st.session_state.setdefault('price_load_attempts',{})
    selected=D['prices'] if code is None else D['prices'][D['prices'].code==code]
    eligible=bool(krx or (public and code))
    retry=st.button('시세 불러오기 · 새로고침',key='load_'+str(code),type='primary')
    if retry or (selected.empty and eligible and marker not in attempts):
        with st.spinner('실제 시세 조회 중… 휴장일에는 최근 거래일을 확인합니다.'):
            frame,messages=load_prices(D['prices'],master,asof,krx,public,code)
            D['prices']=frame
            attempts[marker]=messages
        S=snapshot(master,D,asof,basis)
    if marker in attempts:
        for message in attempts[marker]:
            if '반영' in message:st.success(message)
            else:st.warning(message)
    elif selected.empty:
        st.info('시세가 아직 없습니다. 설정된 KRX 키로 조회하거나 기업을 한 개 선택해 공공데이터 주가를 불러오세요.')
    st.caption('실제 API 자료만 반영합니다. 재무·수급은 별도 수집 항목이며, 시세 조회만으로 채워지지 않습니다.')


def overview():
    heading('이종완의 반도체 소부장\n주식투자 분석 대시보드','산업의 흐름에서 기업의 가치를 발견하다.')
    a,b,c=st.columns([1,1,2])
    product=a.selectbox('제품',['전체','DRAM','3D NAND','HBM','기타'])
    group=b.selectbox('비교군',['전체']+sorted(master.group.unique()))
    query=c.text_input('기업명 / 종목코드 검색')
    f=S.copy()
    if product!='전체':f=f[f.products.str.split('|').apply(lambda xs:product in xs)]
    if group!='전체':f=f[f.group==group]
    if query:f=f[f.name.str.contains(query,regex=False)|f.code.str.contains(query,regex=False)]
    price_loader(f.code.iloc[0] if len(f)==1 else None)
    f=S[S.code.isin(f.code)].copy()
    cards([('분석 대상',f'{len(f)}개'),('시세 확보',f'{f.close.notna().sum()}개'),('영업이익률 중앙값',fmt(f.margin.median(),'%')),('재무 확보',f'{f.financial_date.notna().sum()}개')])
    left,right=st.columns([1.4,1])
    with left,st.container(border=True):
        st.subheader('비교군 영업이익률')
        g=f.dropna(subset=['margin']).groupby(['group','financial_date','period'],dropna=False).margin.median().reset_index()
        if len(g):plot(px.bar(g,x='margin',y='group',color='financial_date',orientation='h',labels={'margin':'영업이익률 %','group':'비교군','financial_date':'기준일'}))
        else:st.info('재무 데이터를 연결하면 표시됩니다.')
    with right,st.container(border=True):
        st.subheader('데이터 완성도')
        for label,col in [('주가','close'),('재무','margin'),('외국인 수급','foreign_net_20')]:
            count=f[col].notna().sum();st.write(f'{label}  {count} / {len(f)}');st.progress(float(count/max(len(f),1)))
    st.subheader('기업 탐색')
    table(f,['name','group','close','revenue_yoy','margin','per','pbr','foreign_net_20','financial_date','price_date'])
    st.caption('비교군·제품 태그는 공정 용도 기준의 초기 분류입니다. 특정 고객·세대 양산 공급의 증거가 아닙니다. 재무 기간이 다른 기업은 별도 확인하세요.')

def process_page():
    heading('공정별 탐색','제품 → 제조 단계 → 소부장 → 동종 기업')
    flows={'DRAM':['웨이퍼 준비','트랜지스터·커패시터 형성','금속 배선·공정 검사','웨이퍼 테스트','박형화·절단·패키징','최종 검사'], '3D NAND':['웨이퍼 준비','주변회로·다층 박막','채널 홀·저장 셀 형성','배선·검사 / 구조별 웨이퍼 본딩','박형화·절단·패키징','최종 검사 / 이후 SSD 조립'], 'HBM':['HBM용 DRAM·베이스 다이','TSV·배선 형성','웨이퍼 검사·양품 선별','박형화·TSV 노출·절단','적층·접합·충전','HBM 스택 검사']}
    for col,(product,stages) in zip(st.columns(3),flows.items()):
        with col:
            st.subheader(product)
            for i,s in enumerate(stages):st.markdown(f'<div class="mpe-step"><small>STEP {i+1:02d}</small><p>{s}</p></div>',unsafe_allow_html=True)
    st.caption('HBM은 DRAM 기반입니다. 실제 제조에서 증착·노광·식각·세정은 반복되며 TSV와 본딩의 위치는 구조·세대별로 다릅니다. 빈 웨이퍼 제조사는 이 소부장 목록에 별도 포함하지 않았습니다.')
    a,b=st.columns(2);p=a.selectbox('제품 분류',list(flows));proc=b.selectbox('공정 검색',['전체']+sorted(master.process.unique()))
    f=master[master.products.str.split('|').apply(lambda xs:p in xs)]
    if proc!='전체':f=f[f.process==proc]
    table(f)
    with st.expander('공급 확인·고객·매출 비중 근거'):table(D['exposure'])

def company_page():
    heading('기업 분석','사업 구조부터 재무·현금흐름·가치평가까지')
    code=pick()
    price_loader(code)
    c=master.set_index('code').loc[code];m=S.set_index('code').loc[code]
    st.subheader(c['name']);st.write(c.business)
    st.markdown(' '.join(f'<span class="mpe-tag">{escape(v)}</span>' for v in [c['group'],c.process,c.category]),unsafe_allow_html=True)
    cards([('매출 YoY',fmt(m.get('revenue_yoy'),'%')),('영업이익률',fmt(m.get('margin'),'%')),('PER',fmt(m.get('per'),'배')),('FCF',fmt(m.get('fcf'),'억',1e8))])
    tabs=st.tabs(['주가','재무제표','재무·가치 지표','사업·공급 근거'])
    with tabs[0]:price_chart(code)
    with tabs[1]:
        f=D['financials'];f=f[(f.code==code)&(f.basis==basis)&(f.published_at<=str(asof))]
        if not f.empty:
            f=f.sort_values('published_at').drop_duplicates(['period_end','period_type','basis'],keep='last')
            kind=st.radio('표시 기간',['Q','FY'],horizontal=True,format_func=lambda x:'단독 분기' if x=='Q' else '연간');f=f[f.period_type==kind].sort_values('period_end')
            if len(f):
                chart=f.copy();chart[['revenue','operating_profit']]=chart[['revenue','operating_profit']]/1e8
                plot(px.bar(chart,x='period_end',y=['revenue','operating_profit'],barmode='group',labels={'value':'억원','period_end':'기간 말','variable':'계정'}))
        table(f);provenance(f)
    with tabs[2]:
        keys=['period','financial_date','price_date','roe','gross_margin','debt_ratio','current_ratio','net_debt','fcf','fcf_yield','cash_conversion','interest_cover','inventory_days','receivable_days','rd_ratio','ev','ev_ebitda','dividend_yield','high_252','low_252','from_high','turnover_20','volatility','mdd']
        table(pd.DataFrame([{'항목':LABELS.get(k,k),'값':str(m.get(k,'자료 없음'))} for k in keys]))
        st.caption('ROE는 지배주주 순이익/평균 지배주주 지분. TTM은 연속 4분기만 계산합니다. 적자·비양수 분모의 PER은 표시하지 않습니다. FCF = 영업현금흐름 − 유형·무형자산 취득 현금지출.')
    with tabs[3]:
        table(D['exposure'][D['exposure'].code==code]);table(D['operating'][D['operating'].code==code])
        st.caption('고객·매출 비중·수주·가동률은 데이터 관리에서 근거와 함께 등록합니다.')

def compare_page():
    heading('동종 기업 비교','같은 제품과 같은 회계기간을 맞추어 비교합니다.')
    group=st.selectbox('비교군',sorted(master.group.unique()))
    base=S[S.group==group]
    chosen=st.multiselect('비교 기업',base.code.tolist(),default=base.code.tolist()[:5],format_func=lambda c:master.set_index('code').loc[c,'name'])
    f=base[base.code.isin(chosen)]
    table(f,['name','revenue_yoy','margin','roe','per','pbr','fcf_yield','foreign_strength','return_60','financial_date','period','price_date'])
    dates=f.financial_date.dropna().unique()
    if len(dates)>1:st.warning('재무 기준일이 서로 다릅니다. 동일 기준일을 선택해 비교하세요.')
    if len(dates):
        d=st.selectbox('차트 재무 기준일',sorted(dates,reverse=True));f=f[f.financial_date==d]
    valid=f.dropna(subset=['revenue_yoy','margin'])
    if len(valid):plot(px.scatter(valid,x='revenue_yoy',y='margin',text='name',labels={'revenue_yoy':'매출 YoY %','margin':'영업이익률 %'}))
    estimates=D['estimates'];st.subheader('예상실적 · 평가 근거');table(estimates[estimates.code.isin(chosen)])
    st.caption('종합 매수 점수는 부여하지 않습니다. 낮은 PER은 이익 정점의 결과일 수도 있습니다.')

def flow_page():
    heading('수급 · 주가','외국인·기관 흐름과 가격을 함께 확인합니다.')
    code=pick('flow_company');price_chart(code)
    f=D['flows'];f=f[(f.code==code)&(f.date<=str(asof))].sort_values('date')
    n=st.select_slider('관측 거래일',options=[5,20,60,120],value=20)
    f=f.tail(n)
    if len(f):
        available=[c for c in ['foreign_net','institution_net','retail_net','pension_net'] if f[c].notna().any()]
        if available:
            g=f[['date']+available].copy();g[available]=g[available].cumsum()/1e8
            plot(px.line(g,x='date',y=available,labels={'value':'누적 순매수 · 억원','date':'날짜','variable':'주체'}))
        st.caption(f'요청 {n}거래일 / 확보 {len(f)}거래일. 연기금은 기관 합계의 부분집합이므로 합산하지 않습니다.')
    table(f);provenance(f)
    st.caption('대차 잔고와 공매도 잔고는 다릅니다. 제공되지 않는 모의 API 수급 항목은 CSV로 보완합니다.')

def industry_page():
    heading('산업 · 사업 지표','수주·가동률·고객 투자·메모리 가격의 근거를 축적합니다.')
    d=D['operating']
    if len(d):
        metric=st.selectbox('지표',d.metric.unique());f=d[d.metric==metric]
        unit=st.selectbox('단위',f.unit.unique());f=f[f.unit==unit].sort_values('date')
        plot(px.line(f,x='date',y='value',color='code',markers=True,labels={'value':unit,'date':'기준일','code':'종목'}));table(f)
    else:st.info('데이터 관리 → operating CSV에 수주잔고·가동률·생산능력·메모리 가격 등을 입력하세요. 산업 공통 지표의 코드는 000000을 사용합니다.')
    table(pd.DataFrame({'유형':['장비','소재','소모성 부품','패키지 기판','테스트 부품','후공정 서비스'],'우선 확인':['신규수주·잔고·검수 시점','출하량·가격·고객 가동률','교체 주기·고객 가동률','가동률·수율·증설','신규 칩·양산·개발용 비중','가동률·고객 물량·감가상각']}))

def events_page():
    heading('공시 · 위험 점검','사건과 숫자를 연결하고 확인할 조건을 기록합니다.')
    e=D['events'];table(e.sort_values('date',ascending=False))
    alerts=[]
    for _,r in S.iterrows():
        if pd.notna(r.get('fcf')) and r.fcf<0:alerts.append({'기업':r['name'],'확인 항목':'FCF 음수','설명':'증설·운전자본·영업현금흐름 확인'})
        if pd.notna(r.get('debt_ratio')) and r.debt_ratio>150:alerts.append({'기업':r['name'],'확인 항목':'부채비율 150% 초과','설명':'업종 특성·차입 만기 확인'})
        if pd.notna(r.get('price_date')) and (asof-pd.Timestamp(r.price_date).date()).days>7:alerts.append({'기업':r['name'],'확인 항목':'시세 7일 이상 경과','설명':'휴장·수집 누락·거래 정지 확인'})
    st.subheader('확인 필요 항목')
    if alerts:table(pd.DataFrame(alerts))
    else:st.info('현재 자료에서 설정된 확인 조건에 해당하는 항목이 없습니다. 자료가 없다는 것이 위험이 없다는 뜻은 아닙니다.')
    st.caption('위 조건은 검토용 기본값이며 투자 판단이나 문제 확정이 아닙니다. 공시 일정·사건은 events CSV로 관리합니다.')

def notes_page():
    heading('관심종목 · 투자 노트','매수 논리와 그 논리가 바뀌는 조건을 남깁니다.')
    st.caption('메모는 현재 세션에서 유지됩니다. 데이터 관리의 ZIP 내보내기로 백업·복원하세요.')
    code=pick('note_company');old=D['notes'];old=old[old.code==code]
    r=old.iloc[-1].to_dict() if len(old) else {}
    with st.form('note_'+code):
        watch=st.checkbox('관심종목',value=r.get('watch')=='True')
        thesis=st.text_area('투자 논리',value=r.get('thesis',''))
        risk=st.text_area('위험 · 논리를 바꿀 조건',value=r.get('risk',''))
        review=st.date_input('다음 확인일',value=pd.Timestamp(r['review_date']).date() if r.get('review_date') else asof+timedelta(days=30))
        if st.form_submit_button('노트 반영',type='primary'):
            row=validate('notes',pd.DataFrame([dict(code=code,date=str(asof),thesis=thesis,risk=risk,review_date=str(review),watch=str(watch),source='직접 작성',status='user')]))
            D['notes']=merge(D['notes'],row,'notes');st.success('반영했습니다. 세션 종료 전 백업하세요.')
    table(D['notes'])

def scenario_page():
    heading('시나리오 · 전략 검증','가정을 직접 바꾸고 계산 근거를 확인합니다.')
    a,b=st.tabs(['이익·평가배수 시나리오','가격 모멘텀 검증'])
    with a:
        code=pick('scenario_company');r=S.set_index('code').loc[code]
        c1,c2,c3=st.columns(3)
        revenue=c1.number_input('예상 매출 · 억원',min_value=0.,value=float(r.get('revenue',0)/1e8) if pd.notna(r.get('revenue',np.nan)) else 1000.)
        margin=c2.slider('지배주주 순이익률 가정 %',0.,50.,15.)
        shares=c3.number_input('주식 수 · 만주',min_value=0.01,value=float(r.get('shares',20000000)/10000) if pd.notna(r.get('shares',np.nan)) else 2000.)
        per=st.slider('PER 가정 범위',1,80,(15,30))
        earnings=revenue*1e8*margin/100;eps=earnings/(shares*10000)
        out=pd.DataFrame({'PER':range(per[0],per[1]+1)});out['가정 주가']=out.PER*eps
        cards([('가정 순이익',fmt(earnings,'억',1e8)),('가정 EPS',fmt(eps,'원')),('가정 주가 범위',f'{eps*per[0]:,.0f} ~ {eps*per[1]:,.0f}원')])
        plot(px.line(out,x='PER',y='가정 주가'));st.caption('사용자 가정에 따른 단순 민감도입니다. 컨센서스·목표주가·매수 추천이 아닙니다.')
    with b:
        options=D['prices'].code.unique().tolist()
        codes=st.multiselect('검증 대상',options,default=options[:5])
        lookback=st.selectbox('모멘텀 관측 거래일',[20,60,120],index=1)
        topn=st.number_input('편입 종목 수',min_value=1,max_value=20,value=3)
        cost=st.number_input('거래금액당 비용 · bp',min_value=0.,max_value=200.,value=15.)
        st.caption('월초 신호 → 다음 거래일 종가 체결 → 이후 수익 반영. 수정주가가 있는 공통 날짜만 사용. 비교선은 일별 동일가중·비용 미차감. 현재 선택한 기업만 검증하므로 생존편향이 있으며 배당 재투자는 포함하지 않습니다.')
        if st.button('검증 실행'):
            result=attempt(lambda:momentum_backtest(D['prices'][D['prices'].date<=str(asof)],codes,lookback,int(topn),cost))
            if result is not None:plot(px.line(result,x='date',y=['strategy','equal_weight'],labels={'value':'시작값 100','date':'날짜','variable':'전략'}));table(result.tail())

def portfolio_page():
    heading('모의투자 계좌','한국투자증권 모의계좌 · 국내주식 보유 현황')
    st.info('Streamlit Secrets의 모의투자 키와 계좌를 읽습니다. 아래 설정 상태를 확인한 뒤 잔고 새로고침을 누르세요.')
    connection_diagnostics(only_kis=True)
    if not source_api('kis','app_key','KIS_APP_KEY') or not source_api('kis','app_secret','KIS_APP_SECRET'):
        st.warning('Secrets에서 모의투자 키를 찾지 못했습니다. 데이터 관리 → 연결 설정의 예시와 항목 이름을 확인하세요. Secrets 저장 후 앱을 Reboot 해주세요.')
    if demo:st.caption('계좌 화면은 가상 예시를 사용하지 않습니다. 아래는 연결한 모의계좌의 실제 응답만 표시합니다.')
    col1,col2=st.columns([1,4])
    if col1.button('잔고 새로고침',type='primary'):
        if time.time()-st.session_state.get('last_balance_attempt',0)<10:st.warning('조회 후 10초 간격으로 새로고침할 수 있습니다.')
        else:
            st.session_state.last_balance_attempt=time.time()
            with st.spinner('모든 보유종목을 조회하고 있습니다…'):
                result=attempt(lambda:kis_client().balance())
                if result is not None:st.session_state.portfolio=result
    if col2.button('계좌 결과 지우기'):st.session_state.pop('portfolio',None)
    if 'portfolio' not in st.session_state:
        st.caption('계좌 데이터는 브라우저 세션에만 보관하며 공용 캐시·GitHub·내보내기 ZIP에 포함하지 않습니다.');return
    holdings,sm,stamp=st.session_state.portfolio
    st.caption('조회 시각: '+pd.Timestamp(stamp).tz_convert('Asia/Seoul').strftime('%Y-%m-%d %H:%M:%S KST')+' · 이후 새로고침 실패 시 이 시점의 결과가 유지됩니다.')
    pnl_pct=ratio(sm['evlu_pfls_smtl_amt'],sm['pchs_amt_smtl_amt'],100)
    cards([('총평가금액',fmt(sm['tot_evlu_amt'],'원')),('주식 평가금액',fmt(sm['evlu_amt_smtl_amt'],'원')),('평가손익',fmt(sm['evlu_pfls_smtl_amt'],'원')),('주식 평가손익률',fmt(pnl_pct,'%'))])
    st.write(f"예수금 {fmt(sm['dnca_tot_amt'],'원')}  ·  익일정산 {fmt(sm['nxdy_excc_amt'],'원')}  ·  가수도정산 {fmt(sm['prvs_rcdl_excc_amt'],'원')}")
    st.caption('예수금·정산금은 각각 다른 결제 기준입니다. 합산하거나 주문가능금액으로 해석하지 않습니다. 평가손익률은 누적 실현수익률이 아닙니다.')
    if holdings.empty:st.success('현재 보유수량이 있는 국내주식이 없습니다.');return
    h=holdings.merge(master[['code','group','category']],on='code',how='left').fillna({'group':'분류 외 종목','category':'기타'})
    total=h.value.sum(min_count=1);h['weight']=h.value/total*100 if total>0 else np.nan
    a,b=st.columns(2)
    with a:plot(px.pie(h,names='name',values='value',hole=.65,title='종목별 주식 평가액'))
    with b:plot(px.bar(h.sort_values('pnl'),x='pnl',y='name',orientation='h',title='종목별 평가손익',labels={'pnl':'원','name':'종목'}))
    table(h,['name','code','quantity','avg_price','price','cost','value','pnl','pnl_pct','weight','group'])
    st.subheader('비교군별 보유 비중');table(h.groupby('group',as_index=False)[['value','weight']].sum())
    if h.weight.max()>30:st.warning('한 종목의 주식 평가액 비중이 30%를 넘습니다. 집중도를 확인하세요. (검토용 기준)')

def settings_page():
    heading('데이터 관리','API 연결 · 자료 검증 · 백업과 복원')
    t1,t2,t3,t4=st.tabs(['연결 설정','API 수집','CSV · 백업','데이터 사전'])
    with t1:
        st.caption('Streamlit Secrets 또는 아래의 세션 입력을 사용합니다. 입력값은 파일·로그에 저장하지 않습니다.')
        if not trusted:st.warning('서버 Secrets를 사용하려면 APP_PASSWORD를 먼저 설정하세요. 아래 직접 입력한 키는 본인 세션에서만 사용됩니다.')
        with st.form('credentials_form',clear_on_submit=True):
            a,b=st.columns(2)
            key=a.text_input('모의투자 APP KEY',type='password');sec=b.text_input('모의투자 APP SECRET',type='password')
            cano=a.text_input('모의계좌 앞 8자리',type='password');prod=b.text_input('계좌 상품코드 2자리',value='01')
            krx=a.text_input('KRX 인증키',type='password');pub=b.text_input('공공데이터포털 인증키',type='password')
            if st.form_submit_button('세션 연결 설정 반영'):
                # Empty fields preserve earlier values; explicit disconnect below clears all.
                conf=st.session_state.get('credentials',{})
                for s,values in {'kis':{'app_key':key,'app_secret':sec,'cano':cano,'acnt_prdt_cd':prod},'krx':{'api_key':krx},'public_data':{'service_key':pub}}.items():
                    conf.setdefault(s,{})
                    for k,v in values.items():
                        if v.strip():conf[s][k]=v.strip()
                st.session_state.credentials=conf
                for k in ['kis_client','kis_config','portfolio']:st.session_state.pop(k,None)
                st.success('현재 세션에 반영했습니다.')
        if st.button('세션 키 · 계좌 결과 삭제'):
            for k in ['credentials','kis_client','kis_config','portfolio']:st.session_state.pop(k,None)
            st.success('세션 입력을 지웠습니다. 서버 Secrets는 변경되지 않습니다.')
        connection_diagnostics()
        st.info('중첩 형식 [kis] app_key 또는 최상위 KIS_APP_KEY 형식을 지원합니다. Secrets를 수정한 후 앱을 Reboot 하세요. 시세·재무는 API 수집 탭에서 조회해야 화면에 반영됩니다.')
        st.download_button('Secrets 설정 예시 다운로드',Path('secrets.example.toml').read_text(),file_name='secrets.example.toml')
    with t2:
        st.caption('수집은 실제 데이터에만 반영됩니다. 가상 예시 모드를 끄면 확인할 수 있습니다. 키 설정만으로 서비스별 이용 승인이 보장되지는 않습니다.')
        service=st.selectbox('수집 서비스',['KRX 일별 시세','공공데이터 기간 시세','공공데이터 요약 재무','KIS 투자자 수급'])
        if service=='KRX 일별 시세':
            d=st.date_input('거래일',value=asof);market=st.selectbox('시장',['KOSPI','KOSDAQ'])
            if st.button('선택일 시세 수집'):
                with st.spinner('시세 조회 중…'):
                    frame=attempt(lambda:KRX(source_api('krx','api_key','KRX_API_KEY')).daily(d,market,master.code.tolist()))
                if frame is not None:save_data('prices',frame)
        elif service=='공공데이터 기간 시세':
            with st.expander('HTTP 403 · 인증 거부 해결 안내'):
                st.markdown('1. [금융위원회_주식시세정보](https://www.data.go.kr/data/15094808/openapi.do)의 활용신청이 승인되어 있는지 확인하세요. 다른 API의 승인만으로는 충분하지 않습니다.\n2. 해당 활용신청 상세의 **일반 인증키(Decoding)**를 Secrets의 `[public_data]` 아래 `service_key`에 입력하세요.\n3. 일시 오류일 수 있으므로 약 20분 뒤 재시도하세요. 계속되면 **마이페이지 → 데이터 활용 → OPEN API → 활용신청 현황 → 해당 API → 변경신청** 후 약 1시간 뒤 재시도하세요.\n4. 이후에도 지속되면 공공데이터포털에 문의하세요.\n\n[금융위원회 공식 403 안내](https://www.fsc.go.kr/in060501)')
                st.caption('앱은 Encoding 키도 한 번 디코딩한 뒤 요청을 인코딩합니다. 키 값·인증된 요청 URL은 화면과 로그에 출력하지 않습니다.')
            code=pick('fetch_price');a,b=st.columns(2)
            start=a.date_input('시작일',value=asof-timedelta(days=365));end=b.date_input('종료일',value=asof)
            if st.button('기간 시세 수집'):
                if start>end:st.error('시작일이 종료일보다 늦습니다.')
                else:
                    with st.spinner('시세 페이지를 수집하고 있습니다…'):
                        frame=attempt(lambda:PublicData(source_api('public_data','service_key','PUBLIC_DATA_KEY')).prices(code,start,end))
                    if frame is not None:save_data('prices',frame)
            st.caption('금융위원회 주식시세정보 서비스 승인 필요. 원주가만 제공되면 수정주가 기반 성과 지표는 비워 둡니다.')
        elif service=='KIS 투자자 수급':
            code=pick('fetch_flow')
            st.info('모의투자 서버에서 지원되지 않을 수 있습니다. 이 경우 실제처럼 보이는 값으로 대체하지 않으며 flows CSV 업로드를 사용합니다.')
            if st.button('투자자 수급 조회'):
                frame=attempt(lambda:kis_client().investor(code))
                if frame is not None:save_data('flows',frame)
        else:
            code=pick('fetch_finance');a,b=st.columns(2)
            crno=a.text_input('법인등록번호 13자리');year=b.number_input('사업연도',min_value=2000,max_value=asof.year,value=asof.year-1)
            if st.button('요약 재무 원자료 조회'):
                raw=attempt(lambda:PublicData(source_api('public_data','service_key','PUBLIC_DATA_KEY')).financial_raw(crno,int(year)))
                if raw is not None:st.session_state.raw_finance=(code,int(year),raw)
            st.caption('서비스가 제공하는 회계기간·연결 구분·금액 단위를 원자료에서 확인한 후 표준 데이터로 반영합니다. 현금흐름은 이 서비스만으로 확보되지 않을 수 있습니다.')
            if 'raw_finance' in st.session_state:
                rc,ry,raw=st.session_state.raw_finance
                table(raw)
                if not raw.empty:
                    st.download_button('재무 원자료 CSV',raw.to_csv(index=False).encode('utf-8-sig'),'financial_raw.csv')
                    st.subheader('선택한 원자료 표준화')
                    idx=st.selectbox('원자료 행',list(range(len(raw))))
                    a,b,c=st.columns(3)
                    pend=a.date_input('회계기간 종료일 확인',value=date(ry,12,31))
                    pub=b.date_input('실제 발표일 확인',value=asof)
                    bs=c.selectbox('재무제표 구분 확인',['CFS','OFS'])
                    a,b,c=st.columns(3)
                    typ=a.selectbox('실적 기간 확인',['FY','Q'])
                    multiplier=b.selectbox('원자료 금액 단위',['원','천원','백만원','억원'])
                    st.caption('발표일을 모르면 확인일로 저장하면 됩니다. 과거 시점에는 사용되지 않습니다. 순이익과 지배주주 순이익을 혼동하지 마세요.')
                    fields=['revenue','operating_profit','net_income','parent_net_income','assets','liabilities','equity','parent_equity']
                    defaults={'revenue':'enpSaleAmt','operating_profit':'enpBzopPft','net_income':'enpCrtmNpf','assets':'enpTastAmt','liabilities':'enpTdbtAmt','equity':'enpTcptAmt'}
                    mappings={};cols=st.columns(2);choices=['선택 안 함']+raw.columns.tolist()
                    for i,f in enumerate(fields):
                        default=defaults.get(f,'선택 안 함');mappings[f]=cols[i%2].selectbox(LABELS.get(f,f)+' 원자료 열',choices,index=choices.index(default) if default in choices else 0,key='map_'+f)
                    confirmed=st.checkbox('종목·기간·연결 구분·단위와 계정 대응을 확인했습니다.')
                    if st.button('검증 후 재무 반영',disabled=not confirmed):
                        factor={'원':1,'천원':1000,'백만원':1e6,'억원':1e8}[multiplier]
                        row=dict(code=rc,period_end=str(pend),period_type=typ,basis=bs,published_at=str(pub),source='공공데이터 요약재무 / 사용자 확인',retrieved_at=datetime.now(timezone.utc).isoformat(),status='reviewed')
                        row.update({f:number(raw.iloc[idx][key])*factor for f,key in mappings.items() if key!='선택 안 함'})
                        parsed=attempt(lambda:validate('financials',pd.DataFrame([row])))
                        if parsed is not None:save_data('financials',parsed)
    with t3:
        st.info('세션 종료·서버 재시작 시 업로드와 메모가 사라질 수 있습니다. ZIP 백업을 내려받고 다음 접속 때 복원하세요. API 키·계좌 잔고는 백업에서 제외됩니다.')
        st.download_button('현재 분석 데이터 ZIP 백업',export_bundle(D),file_name=('demo' if demo else 'mpe')+'_research_backup.zip',mime='application/zip')
        backup=st.file_uploader('백업 복원',type=['zip'])
        if backup and st.button('백업 검증 후 병합'):
            try:
                imported=import_bundle(backup.getvalue())
                synthetic=any('synthetic' in x.status.values for x in imported.values() if len(x))
                if synthetic and not demo:raise ValueError('가상 예시 백업은 실제 데이터에 병합할 수 없습니다. 가상 모드에서 복원하세요.')
                for k,v in imported.items():D[k]=merge(D[k],v,k)
                st.success('병합했습니다. 다른 메뉴에서 확인하세요.')
            except Exception as e:st.error(str(e) if isinstance(e,ValueError) else '백업 형식을 확인하세요.')
        kind=st.selectbox('업로드할 데이터 종류',list(SCHEMAS))
        st.download_button('빈 CSV 양식',pd.DataFrame(columns=SCHEMAS[kind]).to_csv(index=False).encode('utf-8-sig'),file_name=kind+'_template.csv')
        upload=st.file_uploader('UTF-8 CSV 업로드',type=['csv'])
        if upload:
            try:
                incoming=validate(kind,pd.read_csv(upload,dtype=str))
                if not demo and incoming.status.eq('synthetic').any():raise ValueError('가상 데이터를 실제 모드에 업로드할 수 없습니다.')
                table(incoming.head(20))
                if st.button('검증된 자료 병합'):
                    D[kind]=merge(D[kind],incoming,kind);st.success(f'{len(incoming)}행을 반영했습니다.')
            except (ValueError,pd.errors.ParserError) as e:st.error(str(e))
        st.subheader('수집 상태')
        table(pd.DataFrame([{'종류':k,'행 수':len(v),'출처':', '.join(v.source.unique()) if len(v) else '미수집'} for k,v in D.items()]))
    with t4:
        st.markdown(Path('DATA_DICTIONARY.md').read_text())

routes={'종합 현황':overview,'공정별 탐색':process_page,'기업 분석':company_page,'동종 기업 비교':compare_page,'수급 · 주가':flow_page,'산업 · 사업 지표':industry_page,'공시 · 위험 점검':events_page,'관심종목 · 투자 노트':notes_page,'시나리오 · 전략 검증':scenario_page,'모의투자 계좌':portfolio_page,'데이터 관리':settings_page}
routes[page]()
st.divider()
st.caption('MPE RESEARCH · jwsslee/mpe_jwlee | 모든 금액은 별도 표시가 없으면 원(KRW) | 자료 없음 ≠ 0 | 기준일과 실제 공급 근거를 확인하세요.')
