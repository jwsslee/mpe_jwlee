"""Session-scoped cache: retain last good data, display failed refreshes."""
import time
import traceback
from .api import APIError,now


def collect(cache,key,fn,ttl=300,force=False):
    previous=cache.get(key,{})
    wait=120 if previous.get('error') else ttl
    if previous and not force and time.monotonic()-previous['attempt']<wait:return previous
    entry=dict(previous,attempt=time.monotonic(),attempted_at=now().isoformat(),error='')
    try:
        entry['data']=fn();entry['success_at']=now().isoformat()
    except APIError as error:entry['error']=str(error)
    except Exception as error:
        # Whitelisted internal frame only: never include exception values, locals or response.
        locations=[f for f in traceback.extract_tb(error.__traceback__) if f.filename.replace('\\','/').endswith('/core/api.py')]
        location=f'api.py:{locations[-1].lineno} · {locations[-1].name}' if locations else '조회 처리'
        kind=type(error).__name__
        if kind not in ('TypeError','ValueError','AttributeError','KeyError','IndexError','OverflowError','RuntimeError'):kind='UnexpectedError'
        entry['error']=f'응답 처리 오류 [{kind} · {location}]. 이 진단 문구로 실패 단계를 확인할 수 있습니다.'
    cache[key]=entry
    return entry
