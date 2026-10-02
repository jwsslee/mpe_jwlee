"""Session-scoped cache: retain last good data, display failed refreshes."""
import time
from .api import APIError,now


def collect(cache,key,fn,ttl=300,force=False):
    previous=cache.get(key,{})
    wait=120 if previous.get('error') else ttl
    if previous and not force and time.monotonic()-previous['attempt']<wait:return previous
    entry=dict(previous,attempt=time.monotonic(),attempted_at=now().isoformat(),error='')
    try:
        entry['data']=fn();entry['success_at']=now().isoformat()
    except APIError as error:entry['error']=str(error)
    except Exception:
        # Unexpected provider schema changes must not expose request/credential reprs.
        entry['error']='응답 처리 오류. 연결 진단에서 조회 항목을 확인하세요.'
    cache[key]=entry
    return entry
