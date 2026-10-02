"""Resolve known credential names without displaying their values."""
from collections.abc import Mapping

ALIASES = {
    ('kis','app_key'): ('KIS_APP_KEY','KIS_APPKEY','APP_KEY','APPKEY'),
    ('kis','app_secret'): ('KIS_APP_SECRET','KIS_APPSECRET','APP_SECRET','APPSECRET'),
    ('kis','cano'): ('KIS_CANO','CANO','KIS_ACCOUNT_NO','ACCOUNT_NO'),
    ('kis','acnt_prdt_cd'): ('KIS_ACNT_PRDT_CD','ACNT_PRDT_CD'),
    ('krx','api_key'): ('KRX_API_KEY','KRX_KEY','KRX_AUTH_KEY','AUTH_KEY'),
    ('public_data','service_key'): ('PUBLIC_DATA_KEY','PUBLIC_DATA_API_KEY','DATA_GO_KR_KEY','SERVICE_KEY','SERVICEKEY'),
}
SECTIONS={'kis':('kis','korea_investment'),'krx':('krx',),'public_data':('public_data','data_go_kr','public')}


def resolve(settings, section, key, env=None, env_name=''):
    """Return (value, source label); never search unrelated credential sections."""
    env=env or {}
    def find(mapping,names,prefix):
        if not isinstance(mapping,Mapping):return '', ''
        lookup={str(k).casefold():k for k in mapping}
        for name in names:
            actual=lookup.get(name.casefold())
            if actual is not None:
                value=mapping[actual]
                if isinstance(value,(str,int)) and not isinstance(value,bool) and str(value).strip():
                    return str(value).strip(),prefix+str(actual)
        return '', ''
    names=ALIASES.get((section,key),(key,))
    value,where=find(env,([env_name] if env_name else [])+list(names),'환경변수 ')
    if value:return value,where
    if section:
        lookup={str(k).casefold():k for k in settings}
        for name in SECTIONS.get(section,(section,)):
            actual=lookup.get(name.casefold())
            if actual is not None:
                value,where=find(settings[actual],(key,)+names,f'[{actual}].')
                if value:return value,where
    return find(settings,names if section else (key,),'Secrets ')
