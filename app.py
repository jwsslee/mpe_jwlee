"""KRX + KIS only, automatically collected, read-only personal dashboard."""
from pathlib import Path
from datetime import datetime
import hmac,os,time
import pandas as pd
import plotly.express as px
import streamlit as st
from core.api import KRX,KIS,APIError,now
from core.settings import read_settings
from core.finance import KISFinancials
from core.state import collect
from core.universe import COMPANIES,DEFAULT_CODES
from core.catalog import catalog,filter_catalog
from core.glossary import MEANINGS,glossary_table
from core.style import setup,heading,fmt,cards,table,plot

st.set_page_config(page_title='이종완 · 반도체 소부장',page_icon='◈',layout='wide')
setup()
try:
    try:settings=read_settings(st.secrets,os.environ)
    except FileNotFoundError:settings=read_settings({},os.environ)
except Exception:
    st.error('Streamlit Secrets의 TOML 형식을 확인하세요. 항목 이름은 secrets.example.toml을 참고하세요.');st.stop()

if not settings.password:
    heading('접속 비밀번호 설정','서버에 보관된 모의계좌 정보를 보호하기 위한 개인용 로그인입니다.')
    st.error('Secrets의 최상위에 APP_PASSWORD를 설정한 후 Reboot 하세요.')
    st.code('APP_PASSWORD = "직접 정한 접속 비밀번호"\n\n[kis]\napp_key = "모의투자 KEY"\napp_secret = "모의투자 SECRET"\ncano = "계좌 앞 8자리"\nacnt_prdt_cd = "01"\n\n[krx]\napi_key = "KRX 인증키"',language='toml')
    st.stop()

# Recheck the authenticated password fingerprint on Secrets changes.
import hashlib
password_id=hashlib.sha256(settings.password.encode()).hexdigest()
if st.session_state.get('auth')!=password_id:
    heading('이종완의 투자연구실','KRX · 한국투자증권 모의투자 | 자동 데이터 조회')
    with st.form('login',clear_on_submit=True):
        entered=st.text_input('접속 비밀번호',type='password')
        submit=st.form_submit_button('로그인',type='primary')
    if submit:
        if time.monotonic()<st.session_state.get('login_wait',0):st.error('잠시 후 다시 시도하세요.')
        elif hmac.compare_digest(entered.encode(),settings.password.encode()):st.session_state.auth=password_id;st.rerun()
        else:st.session_state.login_wait=time.monotonic()+3;st.error('비밀번호를 확인하세요.')
    st.stop()

if st.session_state.get('config_id')!=settings.fingerprint:
    st.session_state.config_id=settings.fingerprint
    st.session_state.cache={}
    st.session_state.kis=KIS(settings.key,settings.secret,settings.account,settings.product)
cache=st.session_state.cache;kis=st.session_state.kis
if st.session_state.get('finance_config_id')!=settings.finance_fingerprint:
    st.session_state.finance_config_id=settings.finance_fingerprint
    st.session_state.finance=KISFinancials(settings.real_key,settings.real_secret)
    for key in list(cache):
        if key.startswith('KIS 실전 실적 '):del cache[key]
finance=st.session_state.finance
with st.sidebar:
    st.markdown('### ◈ 이종완의 투자연구실')
    st.caption('KRX × KIS · 새 버전 2.2')
    page=st.radio('화면',['시장 · 관심기업','기업 정보표','기업 상세','모의투자 계좌','연결 진단'],label_visibility='collapsed')
    st.divider()
    auto=st.toggle('화면 자동 갱신',value=True)
    st.caption('처음 열 때 자동 수집 · 이후 60초마다 확인\n\nKRX 종가 15분 / KIS 시세·계좌 60초 / 주가 이력 1시간 / 재무 실적 6시간 캐시')
    st.caption('한국 시간 '+now().strftime('%Y-%m-%d %H:%M'))
    if st.button('로그아웃'):
        st.session_state.clear();st.rerun()


def load(key,fn,ttl=300,force=False):return collect(cache,key,fn,ttl,force)

def report(entry,label):
    if entry.get('error'):
        st.warning(label+' — '+entry['error'])
        if 'data' in entry:st.caption('이전 성공 결과를 유지합니다. 수집시각 '+entry['success_at'])
    elif 'data' in entry:st.caption(label+' · 수집시각 '+entry['success_at'])

def refresh(key):
    clicked=st.button('지금 새로고침',key='refresh_'+key)
    if clicked:
        last=st.session_state.get('refresh_time',-1e9)
        if time.monotonic()-last<10:
            st.info('연속 요청을 줄이기 위해 10초 후 다시 시도하세요.');return False
        st.session_state.refresh_time=time.monotonic()
    return clicked


def current_quote(code,force=False):
    # Both screens use the exact same provider, query and session cache key.
    return load('KIS 현재가 '+code,lambda:kis.quote(code),60,force)


def market_page():
    heading('반도체 소부장 · 시장 현황','기업 상세와 동일한 KIS 현재가·전일 대비 등락률을 사용합니다.')
    selected=st.multiselect('관심기업',list(COMPANIES),default=[c for c in DEFAULT_CODES if c in COMPANIES],format_func=lambda c:f'{COMPANIES[c]} · {c}')
    force=refresh('market')
    if not selected:st.info('관심기업을 선택하세요.');return
    frames=[];entries=[]
    if settings.krx:
        for market in ('KOSPI','KOSDAQ'):
            with st.spinner(f'KRX {market} 조회 중…'):
                e=load('KRX '+market,lambda m=market:KRX(settings.krx).latest(m),900,force)
            entries.append((market,e))
            if 'data' in e:frames.append(e['data'])
    else:st.caption('KRX 일별 참고자료는 키 미설정으로 조회하지 않습니다.')
    krx=pd.concat(frames,ignore_index=True) if frames else pd.DataFrame(columns=['code'])
    rows=[];failures=[];skip_kis=False
    bar=st.progress(0.,text='관심기업 확인 중')
    for i,code in enumerate(selected):
        deferred=skip_kis
        e=cache.get('KIS 현재가 '+code,{}) if deferred else current_quote(code,force)
        if 'data' in e:
            state='이전 성공 자료 · 이번 조회 보류' if deferred else '이전 성공 자료 · 갱신 실패' if e.get('error') else '정상'
            rows.append(dict(e['data'],name=COMPANIES[code],quote_status=state))
        if not deferred and e.get('error'):
            failures.append((code,e['error']))
            skip_kis=True
        bar.progress((i+1)/len(selected),text=f'관심기업 {i+1}/{len(selected)} 확인')
    bar.empty()
    for label,e in entries:report(e,'KRX '+label)
    for code,error in failures:st.warning(COMPANIES[code]+' — '+error+' 연속 오류를 피하기 위해 나머지 KIS 일괄 조회는 중단했습니다.')
    reference=krx[krx.code.isin(selected)]
    if not reference.empty:
        with st.expander('KRX 일별 참고자료 · KIS 현재가와 별도 기준'):
            st.caption('표시된 자료 기준일의 종가와 직전 거래일 대비 등락률입니다. 아래 KIS 현재가와 기준일·조회 시각이 다를 수 있습니다.')
            table(reference.reindex(columns=['name','code','price','change_pct','source','asof','fetched']))
    if not rows:
        st.error('KIS 현재가를 가져오지 못했습니다. 다른 기준의 KRX 값으로 대체하지 않습니다. 연결 진단을 확인하세요.');return
    df=pd.DataFrame(rows)
    cards([('시세 수집',f'{len(df)} / {len(selected)}'),('상승',str(int((df.change_pct>0).sum()))+'개'),('하락',str(int((df.change_pct<0).sum()))+'개'),('거래대금 합계',fmt(df.turnover.sum(min_count=1),'억',1e8))])
    if len(df)<len(selected):st.warning('일부 종목 미수집: '+', '.join(COMPANIES[c] for c in selected if c not in df.code.values))
    st.caption('등락률은 KIS 제공 전일 대비 값입니다. 기업 상세와 동일한 종목별 캐시를 사용합니다. 갱신 전후에는 값이 달라질 수 있으므로 수집시각을 함께 확인하세요.')
    plot(px.bar(df.sort_values('change_pct'),x='name',y='change_pct',labels={'name':'기업','change_pct':'전일 대비 등락률(%)'}))
    columns=['name','code','price','change_pct','volume','turnover','market_cap','source','asof','fetched','quote_status']
    table(df.reindex(columns=columns))


def catalog_page():
    heading('기업별 주력사업 · 제품 정보표','이전 버전의 72개 기업 분류를 복원한 참고 정보입니다.')
    reference=catalog()
    st.caption('이 표는 조사 기반 참고 분류이며 KRX·KIS 자동 수집값이 아닙니다. 최신 상장상태·실제 고객 공급관계는 별도 확인이 필요합니다.')
    query=st.text_input('기업명 · 종목코드 · 주력제품 검색',key='catalog_query',placeholder='예: 대덕전자, 본더, 전구체')
    a,b,c=st.columns(3)
    stage=a.selectbox('공정 구분',['전체']+sorted(reference.stage.unique()),key='catalog_stage')
    category=b.selectbox('소부장 · 서비스 구분',['전체']+sorted({v for x in reference.category for v in x.split('·')}),key='catalog_category')
    product=c.selectbox('적용 제품',['전체','DRAM','3D NAND','HBM','기타'],key='catalog_product')
    group=st.selectbox('유사 제품 비교군',['전체']+sorted(reference.group.unique()),key='catalog_group')
    if group!='전체' and group in MEANINGS:
        st.info(group+' — '+MEANINGS[group])
    result=filter_catalog(reference,query,stage,category,product,group)
    st.caption(f'전체 {len(reference)}개 중 {len(result)}개 기업 표시')
    if result.empty:st.info('조건에 해당하는 기업이 없습니다. 검색어나 필터를 변경하세요.')
    else:table(result.assign(products=result.products.str.replace('|',' · ',regex=False)))
    st.caption('공정 구분은 탐색 편의를 위한 대표 분류입니다. 검사·테스트는 웨이퍼·패키지 단계에 걸칠 수 있으며 적용 제품 태그는 해당 세대의 양산 공급을 확정하는 뜻이 아닙니다.')

    st.subheader('유사 제품 비교군 · 쉬운 용어 해설')
    st.caption('비교군은 비슷한 제품·역할의 기업을 묶은 분류입니다. 일부 이름은 한 기업의 여러 사업을 함께 표시합니다.')
    glossary_query=st.text_input('용어 · 뜻 · 기업 예시 검색',key='glossary_query',placeholder='예: 증착, 막, 본딩, 원익IPS')
    terms=glossary_table(reference,glossary_query)
    if terms.empty:st.info('검색 조건에 맞는 용어가 없습니다.')
    else:
        st.dataframe(terms,hide_index=True,width='stretch',height=460,column_config={
            '비교군 용어':st.column_config.TextColumn(width='small'),
            '쉬운 뜻':st.column_config.TextColumn(width='large'),
            '기업 예시(기존 분류)':st.column_config.TextColumn(width='medium')})
    st.caption('기업 예시는 기존 기업정보표의 분류에서 최대 3개를 표시합니다. 용어 설명은 입문용 요약입니다.')
    with st.expander('용어 참고 자료'):
        st.markdown('- [Applied Materials · 반도체 기술 용어집](https://www.appliedmaterials.com/il/en/glossary.html)\n- [ASE · 패키징 기술](https://asekh.aseglobal.com/products-services/package.html)\n- [Advantest · 테스트 핸들러](https://www.advantest.com/en/products/component-test-system/test-handler/)')


def financial_section(code,force=False):
    st.subheader('기업 실적 · 수익성')
    mode=st.radio('실적 기준',['연간','분기 누적'],horizontal=True,key='finance_period')
    st.caption('분기 누적은 해당 연도 시작부터 결산년월까지의 합계이며, 해당 분기만의 실적이 아닙니다.')
    if not settings.real_key or not settings.real_secret:
        st.info('실적 자동 조회를 위해 Streamlit Secrets에 [kis_real]의 app_key와 app_secret을 추가하세요. 실전용 키를 사용합니다.')
        st.code('[kis_real]\napp_key = "실전용 KEY"\napp_secret = "실전용 SECRET"',language='toml')
        return
    division='0' if mode=='연간' else '1'
    with st.spinner('KIS 실전 재무정보 조회 중…'):
        e=load('KIS 실전 실적 '+code+' '+division,lambda:finance.income(code,division),21600,force)
    report(e,'KIS 손익계산서 · '+mode)
    if 'data' not in e:return
    df=e['data'];latest=df.iloc[-1]
    st.caption('최근 제공 결산기간 '+latest['결산년월']+' · '+mode+' · KIS 응답에 포함된 기간만 표시')
    st.info('금액은 KIS 제공값을 환산 없이 표시합니다. API 명세에 금액 단위와 연결·별도 기준이 명시되지 않아 원·억원 또는 연결 실적으로 단정하지 않습니다.')
    cards([('매출액 · 제공값',fmt(latest['매출액'])),('영업이익 · 제공값',fmt(latest['영업이익'])),('영업이익률',fmt(latest['영업이익률(%)'],'%')),('당기순이익 · 제공값',fmt(latest['당기순이익']))])
    st.caption('영업이익률 = 같은 기간 영업이익 ÷ 매출액 × 100. 매출액이 0 이하이거나 수치가 없으면 미제공으로 표시합니다.')
    plot(px.bar(df,x='결산년월',y=['매출액','영업이익'],barmode='group',labels={'value':'금액 · KIS 제공값','variable':'항목'}))
    plot(px.line(df,x='결산년월',y='영업이익률(%)',markers=True))
    table(df.sort_values('결산년월',ascending=False))


def company_page():
    heading('기업 상세','KIS 모의 API · 현재가와 제공 가치지표 · 최근 1년 수정주가')
    options=list(COMPANIES)
    code=st.selectbox('기업',options,index=options.index('353200') if '353200' in options else 0,format_func=lambda c:f'{COMPANIES[c]} · {c}')
    info=catalog()
    info=info[info.code==code]
    if not info.empty:
        st.subheader('주력사업 · 공정 분류')
        table(info.assign(products=info.products.str.replace('|',' · ',regex=False)))
        st.caption('이전 조사 기반 참고 정보 · API 시세와 별도 관리')
    force=refresh('company')
    with st.spinner('KIS 현재가 조회 중…'):q=current_quote(code,force)
    report(q,'현재가')
    if 'data' in q:
        d=q['data']
        cards([('현재가',fmt(d['price'],'원')),('전일 대비 등락률',fmt(d['change_pct'],'%')),('시가총액',fmt(d['market_cap'],'억',1e8)),('거래대금',fmt(d['turnover'],'억',1e8))])
        st.caption('시장·관심기업과 동일한 KIS 조회 결과입니다. 시세 수집시각: '+str(d.get('fetched',q.get('success_at','—'))))
        st.subheader('API 제공 지표')
        table(pd.DataFrame([d]).reindex(columns=['per','pbr','eps','bps','foreign_pct','high_52','low_52']))
        st.caption('PER·PBR·EPS·BPS는 KIS 응답값입니다. 재무 기준기간·연결 여부가 이 응답에 없어 별도 실적 분석으로 해석하지 않습니다. 0 이하 PER·PBR은 미제공으로 처리합니다.')
    financial_section(code,force)
    st.subheader('일별 수정주가')
    with st.spinner('KIS 일별 주가 조회 중…'):h=load('KIS 일별주가 '+code,lambda:kis.history(code),3600,force)
    report(h,'일별 수정주가')
    if 'data' in h:
        df=h['data'].copy()
        st.caption(f'관측 기간 {df.date.min()} ~ {df.date.max()} · {len(df)}개 거래일 · 배당 재투자 미포함')
        for n in (20,60):df[f'MA{n}']=df.close.rolling(n).mean()
        plot(px.line(df,x='date',y=['close','MA20','MA60'],labels={'date':'거래일','value':'수정주가(원)','variable':'구분'}))
        plot(px.bar(df,x='date',y='volume',labels={'date':'거래일','volume':'거래량(주)'}))
        if len(df)>1:
            change=(df.close.iloc[-1]/df.close.iloc[0]-1)*100
            drawdown=(df.close/df.close.cummax()-1).min()*100
            cards([('관측 기간 주가수익률',fmt(change,'%')),('관측 기간 최대낙폭',fmt(drawdown,'%'))])
        with st.expander('일별 데이터'):table(df)

    st.subheader('투자자 수급 · 순매수 수량')
    with st.spinner('KIS 투자자 수급 조회 중…'):flow=load('KIS 투자자 '+code,lambda:kis.investors(code),900,force)
    report(flow,'투자자 수급')
    if 'data' in flow:
        data=flow['data']
        plot(px.bar(data,x='date',y=['외국인 순매수(주)','기관 순매수(주)','개인 순매수(주)'],barmode='group',labels={'date':'거래일','value':'주','variable':'투자자'}))
        st.caption('KIS가 반환한 기간만 표시합니다. 순매수 금액이 아닌 수량(주)이며, 당일 자료는 장 종료 후 제공됩니다.')
        with st.expander('수급 원자료'):table(data)


def portfolio_page():
    heading('모의투자 계좌','KIS 모의계좌 · 화면 진입 시 전체 잔고 자동 조회')
    force=refresh('balance')
    with st.spinner('보유종목과 계좌 합계 조회 중…'):e=load('KIS 모의계좌',kis.balance,60,force)
    report(e,'모의계좌')
    if 'data' not in e:return
    holdings,summary=e['data'];cost=summary['pchs_amt_smtl_amt'];pnl=summary['evlu_pfls_smtl_amt']
    cards([('총평가금액',fmt(summary['tot_evlu_amt'],'원')),('주식 평가액',fmt(summary['evlu_amt_smtl_amt'],'원')),('평가손익',fmt(pnl,'원')),('평가손익률',fmt(pnl/cost*100 if cost>0 else None,'%'))])
    st.metric('예수금',fmt(summary['dnca_tot_amt'],'원'))
    st.caption('예수금은 주문가능금액과 다를 수 있습니다. 평가손익률은 현재 보유주식 매입금액 기준이며 누적 실현수익률이 아닙니다.')
    if holdings.empty:st.info('현재 보유수량이 있는 국내주식이 없습니다.');return
    df=holdings.copy();total=df.value.sum(min_count=1)
    df['weight']=df.value/total*100 if total>0 else float('nan')
    left,right=st.columns(2)
    with left:
        if total>0:plot(px.pie(df,names='name',values='value',hole=.65,title='주식 평가액 비중'))
    with right:plot(px.bar(df,x='name',y='pnl',title='종목별 평가손익',labels={'name':'종목','pnl':'원'}))
    table(df)
    st.caption('잔고와 토큰은 로그인 세션 메모리에만 보관하며 GitHub·파일에 저장하지 않습니다.')


def diagnostics_page():
    heading('연결 진단','설정 인식과 실제 API 조회 결과를 구분합니다. 키·계좌번호 값은 표시하지 않습니다.')
    labels={'krx':'KRX 인증키','key':'KIS 모의 KEY','secret':'KIS 모의 SECRET','real_key':'KIS 실전 재무 KEY','real_secret':'KIS 실전 재무 SECRET','account':'모의 계좌번호','product':'상품코드'}
    table(pd.DataFrame([{'항목':label,'설정':'인식됨' if getattr(settings,k) else '미설정','읽은 위치':settings.locations.get(k) or ('기본값 01' if k=='product' else '—')} for k,label in labels.items()]))
    rows=[]
    for key,e in cache.items():rows.append({'조회':key,'상태':'실패 · 이전 결과 유지' if e.get('error') and 'data' in e else '실패' if e.get('error') else '성공','최근 시도':e.get('attempted_at'),'최근 성공':e.get('success_at','—'),'안내':e.get('error','')})
    if rows:table(pd.DataFrame(rows))
    else:st.info('다른 화면에 들어가면 API를 자동 조회하고 결과가 여기에 기록됩니다.')
    st.markdown('**KRX**: 인증키 승인 외에 **유가증권 일별매매정보·코스닥 일별매매정보**를 각각 이용 신청해야 합니다.\n\n**KIS**: 모의투자용 KEY·SECRET을 사용합니다. 시세 조회에는 계좌번호가 필요 없고, 잔고 조회에는 계좌 8자리와 상품코드 2자리가 필요합니다.')
    st.info('기업 실적은 [kis_real]의 실전용 KEY·SECRET으로 조회합니다. 실전 계좌번호는 필요 없으며 주문 기능은 없습니다.')
    st.download_button('Secrets 설정 예시',Path('secrets.example.toml').read_text(),file_name='secrets.example.toml')
    st.caption('공공데이터포털·OpenDART·스크래핑·CSV 업로드·가상 숫자는 사용하지 않습니다. 손익계산서는 KIS 실전 API로 조회합니다. 컨센서스는 제공하지 않습니다.')

@st.fragment(run_every=60 if auto else None)
def render():
    {'시장 · 관심기업':market_page,'기업 정보표':catalog_page,'기업 상세':company_page,'모의투자 계좌':portfolio_page,'연결 진단':diagnostics_page}[page]()
render()
st.divider();st.caption('MPE 2.2 · KRX / KIS · 모의 시세·계좌 / 실전 재무정보 조회 전용')
