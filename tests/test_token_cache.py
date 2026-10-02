import json
from concurrent.futures import ThreadPoolExecutor
import pytest
import requests
from core.api import KIS,TokenCooldownError,request
from core.finance import KISFinancials
from core.token_cache import state_for

@pytest.mark.parametrize('status',[403,500])
def test_egw00133_is_not_key_error(monkeypatch,status):
    r=requests.Response();r.status_code=status
    r._content=json.dumps({'error_code':'EGW00133','error_description':'private-key'}).encode()
    monkeypatch.setattr(requests,'request',lambda *a,**k:r)
    with pytest.raises(TokenCooldownError) as e:request('KIS','POST',KIS.BASE+'/oauth2/tokenP')
    assert 'private-key' not in str(e.value) and e.value.retry_after==65


def test_parallel_sessions_issue_one_token(monkeypatch):
    calls=[]
    def response(*a,**k):calls.append(1);return {'access_token':'shared','expires_in':86400},{}
    monkeypatch.setattr('core.api.request',response)
    clients=[KIS('shared-key','secret') for _ in range(5)]
    monkeypatch.setattr(clients[0]._gate,'wait',lambda:None)
    with ThreadPoolExecutor(max_workers=5) as pool:tokens=list(pool.map(lambda c:c.token(),clients))
    assert tokens==['shared']*5 and len(calls)==1
    assert state_for(KIS.BASE,'shared-key','secret') is not state_for(KISFinancials.BASE,'shared-key','secret')
    assert state_for(KIS.BASE,'shared-key','secret') is not state_for(KIS.BASE,'shared-key','changed')


def test_rejection_cooldown_shared_then_recovers(monkeypatch):
    clock=[1000.];calls=[]
    monkeypatch.setattr('core.api.time.monotonic',lambda:clock[0])
    def response(*a,**k):
        calls.append(1)
        if len(calls)==1:raise TokenCooldownError()
        return {'access_token':'recovered','expires_in':86400},{}
    monkeypatch.setattr('core.api.request',response)
    a=KIS('cool-key','s');b=KIS('cool-key','s')
    monkeypatch.setattr(a._gate,'wait',lambda:None)
    with pytest.raises(TokenCooldownError):a.token()
    with pytest.raises(TokenCooldownError):b.token()
    assert len(calls)==1
    clock[0]+=66
    assert b.token()=='recovered' and a.token()=='recovered' and len(calls)==2


def test_invalidated_shared_token_not_restored_by_other_session(monkeypatch):
    monkeypatch.setattr('core.api.request',lambda *a,**k:({'access_token':'invalid-later','expires_in':86400},{}))
    a=KIS('invalid-key','s');b=KIS('invalid-key','s')
    monkeypatch.setattr(a._gate,'wait',lambda:None)
    assert a.token()==b.token()
    a.invalidate_token()
    with pytest.raises(TokenCooldownError):b.token()
