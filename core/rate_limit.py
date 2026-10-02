"""Per-app-key pacing shared by sessions in this server process; no credentials stored."""
import hashlib
import threading
import time

class RequestGate:
    def __init__(self,interval=1.25,clock=None,sleep=None):
        self.interval=interval
        self.clock=clock or time.monotonic
        self.sleep=sleep or time.sleep
        self.ready=0.
        self.lock=threading.Lock()
    def wait(self):
        with self.lock:
            delay=max(0.,self.ready-self.clock())
            if delay:self.sleep(delay)
            self.ready=self.clock()+self.interval
    def defer(self,seconds):
        with self.lock:self.ready=max(self.ready,self.clock()+seconds)

_registry={}
_registry_lock=threading.Lock()

def gate_for(key):
    identity=hashlib.sha256(key.encode()).hexdigest()
    with _registry_lock:
        if identity not in _registry:_registry[identity]=RequestGate()
        return _registry[identity]
