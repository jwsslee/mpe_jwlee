"""Bounded price bootstrap; no fabricated fallback and no hidden retries."""
from datetime import timedelta
import pandas as pd
from .connectors import KRX,PublicData,APIError
from .data import merge


def load_prices(existing, master, asof, krx_key='', public_key='', code=None):
    result=existing.copy(); messages=[]
    if krx_key:
        markets=master.market.unique() if code is None else master.loc[master.code==code,'market'].unique()
        for market in markets:
            if market not in ('KOSPI','KOSDAQ'):continue
            found=False
            try:
                for offset in range(7):
                    day=asof-timedelta(days=offset)
                    if day.weekday()>4:continue
                    frame=KRX(krx_key).daily(day,market,master.code.tolist())
                    if not frame.empty:
                        result=merge(result,frame,'prices');found=True
                        messages.append(f'{market}: {day} 시세 {len(frame)}개 기업 반영')
                        break
                if not found:messages.append(f'{market}: 최근 7일 조회 결과 없음 (휴장·갱신 지연·승인 확인)')
            except (APIError,ValueError,KeyError) as e:
                messages.append(f'{market}: '+(str(e) if isinstance(e,APIError) else '응답 데이터 형식 확인 필요'))
    if public_key and code:
        try:
            frame=PublicData(public_key).prices(code,asof-timedelta(days=365),asof)
            if frame.empty:messages.append(f'{code}: 공공데이터 조회 결과 없음 (갱신 지연·서비스 승인 확인)')
            else:
                result=merge(result,frame,'prices')
                messages.append(f'{code}: 주가 이력 {len(frame)}행 반영, 최신 {frame.date.max()}')
        except (APIError,ValueError,KeyError) as e:
            messages.append('공공데이터: '+(str(e) if isinstance(e,APIError) else '응답 데이터 형식 확인 필요'))
    if not krx_key and not (public_key and code):
        messages.append('조회 가능한 설정이 없습니다. KRX 키를 설정하거나 공공데이터 키를 설정한 뒤 기업을 한 개 선택하세요.')
    return result,messages
