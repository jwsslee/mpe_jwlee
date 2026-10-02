import json
import time
import requests
import pytest
from core.api import KIS,APIError,RateLimitError,request
from core.rate_limit import RequestGate,gate_for
from core.token_cache import state_for

class Clock:
    def __init__(self):self.value=10.;self.sleeps=[]
    def now(self):return self.value
    def sleep(self,n):self.sleeps.append(n);self.value+=n


def client():
    clock=Clock();c=KIS('rate-test-key','s')
    state=state_for(c.BASE,c.key,c.secret)
    state.token='token';state.expires=time.time()+3600
    c._gate=RequestGate(clock=clock.now,sleep=clock.sleep)
    return c,clock


def test_gate_shared_across_sessions_and_spacing():
    assert KIS('same-app-key','s')._gate is KIS('same-app-key','s')._gate
    assert gate_for('other-key') is not gate_for('same-app-key')
    clock=Clock();g=RequestGate(clock=clock.now,sleep=clock.sleep)
    g.wait();g.wait();g.defer(4);g.wait()
    assert clock.sleeps==[1.25,4.]


@pytest.mark.parametrize('status',[500,429])
def test_http_rate_limit_is_not_reported_as_key_error(monkeypatch,status):
    r=requests.Response();r.status_code=status;r._content=json.dumps({'msg_cd':'EGW00201'}).encode()
    monkeypatch.setattr(requests,'request',lambda *a,**kw:r)
    with pytest.raises(RateLimitError) as e:request('KIS','GET',KIS.BASE)
    assert '초당 요청' in str(e.value) and 'KEY·SECRET' not in str(e.value)


@pytest.mark.parametrize('http_error',[True,False])
def test_failed_read_retried_after_delay(monkeypatch,http_error):
    c,clock=client();calls=[]
    def response(*a,**kw):
        calls.append(kw['params'].copy())
        if len(calls)==1:
            if http_error:raise RateLimitError()
            return {'rt_cd':'1','msg_cd':'EGW00201'},{}
        return {'rt_cd':'0','output2':[]},{}
    monkeypatch.setattr('core.api.request',response)
    result,_=c.get('/path','TR',{'date':'20261001'})
    assert result['rt_cd']=='0' and len(calls)==2 and calls[0]==calls[1]
    assert clock.sleeps==[2.]


def test_retries_bounded_and_token_errors_not_retried(monkeypatch):
    c,clock=client();calls=[]
    def reject(*a,**kw):calls.append(1);raise RateLimitError()
    monkeypatch.setattr('core.api.request',reject)
    with pytest.raises(RateLimitError):c.get('/p','TR',{})
    assert len(calls)==4 and clock.sleeps==[2.,4.,8.]
    assert c._token=='token'
    calls.clear()
    def auth(*a,**kw):calls.append(1);raise APIError('auth failure')
    monkeypatch.setattr('core.api.request',auth)
    with pytest.raises(APIError):c.get('/p','TR',{})
    assert len(calls)==1
