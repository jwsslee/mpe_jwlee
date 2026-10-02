"""Process-local authentication cache. No disk storage; credentials hashed for identity."""
import hashlib
import json
import threading
from dataclasses import dataclass,field

@dataclass(repr=False)
class TokenState:
    token:str=''
    expires:float=0.
    next_attempt:float=0.
    lock:object=field(default_factory=threading.Lock)

_states={}
_lock=threading.Lock()

def state_for(base,key,secret):
    identity=hashlib.sha256(json.dumps([base,key,secret]).encode()).hexdigest()
    with _lock:
        if identity not in _states:_states[identity]=TokenState()
        return _states[identity]
