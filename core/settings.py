"""Known credential aliases; never expose values in diagnostics."""
from collections.abc import Mapping
from dataclasses import dataclass,field
import hashlib

FIELDS={
 'password':('',('APP_PASSWORD',)),
 'krx':('krx',('api_key','KRX_API_KEY','KRX_KEY','KRX_AUTH_KEY','AUTH_KEY')),
 'key':('kis',('app_key','KIS_APP_KEY','KIS_APPKEY','APPKEY','KIS_MOCK_APP_KEY')),
 'secret':('kis',('app_secret','KIS_APP_SECRET','KIS_APPSECRET','APPSECRET','KIS_MOCK_APP_SECRET')),
 'account':('kis',('cano','KIS_CANO','KIS_ACCOUNT_NO','ACCOUNT_NO')),
 'product':('kis',('acnt_prdt_cd','KIS_ACNT_PRDT_CD')),
}

def lookup(mapping,names):
    if not isinstance(mapping,Mapping):return '',''
    keys={str(k).lower():k for k in mapping}
    for name in names:
        k=keys.get(name.lower())
        if k is not None and isinstance(mapping[k],(str,int)) and not isinstance(mapping[k],bool):
            v=str(mapping[k]).strip()
            if v:return v,str(k)
    return '',''

@dataclass(repr=False)
class Settings:
    password:str=''
    krx:str=''
    key:str=''
    secret:str=''
    account:str=''
    product:str='01'
    locations:dict=field(default_factory=dict)

    @property
    def fingerprint(self):
        return hashlib.sha256('|'.join([self.krx,self.key,self.secret,self.account,self.product]).encode()).hexdigest()


def read_settings(secrets,env=None):
    values={};locations={};env=env or {}
    sections={str(k).lower():k for k in secrets}
    for field,(section,names) in FIELDS.items():
        value,loc=lookup(env,names)
        if value:loc='환경변수 '+loc
        if not value and section in sections:
            value,loc=lookup(secrets[sections[section]],names)
            if value:loc=f'[{sections[section]}].'+loc
        if not value:
            value,loc=lookup(secrets,names if not section else names[1:]+(names[0],))
            if value:loc='Secrets '+loc
        values[field]=value;locations[field]=loc
    raw=values['account'].replace('-','').replace(' ','')
    if len(raw)==10 and raw.isdigit():
        # Preserve an explicitly configured product rather than silently overriding it.
        values['account']=raw[:8]
        if not values['product']:values['product']=raw[8:]
    values['product']=values['product'] or '01'
    return Settings(**values,locations=locations)
