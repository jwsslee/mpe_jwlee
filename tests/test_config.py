from mpe.config import resolve
from pathlib import Path
from streamlit.testing.v1 import AppTest


def test_nested_flat_case_and_empty_fallback():
    assert resolve({'kis':{'app_key':' nested '}},'kis','app_key')[0]=='nested'
    assert resolve({'KIS_APP_KEY':'flat'},'kis','app_key')[0]=='flat'
    assert resolve({'KIS':{'APPKEY':'case'}},'kis','app_key')[0]=='case'
    assert resolve({'kis':{'app_key':''},'KIS_APP_KEY':'fallback'},'kis','app_key')[0]=='fallback'
    assert resolve({'krx':{'api_key':'wrong-provider'}},'kis','app_key')[0]==''
    assert resolve({'SERVICE_KEY':'public'},'public_data','service_key')[0]=='public'
    assert resolve({'KRX_AUTH_KEY':'krx'},'krx','api_key')[0]=='krx'
    assert resolve({'kis':{'cano':'00123456'}},'kis','cano')[0]=='00123456'
    assert resolve({},'kis','app_key',{'KIS_APP_KEY':'env'},'KIS_APP_KEY')[0]=='env'


def test_flat_secrets_reach_account_client_without_exposure(monkeypatch):
    monkeypatch.chdir(Path(__file__).resolve().parents[1])
    monkeypatch.delenv('APP_PASSWORD',raising=False)
    at=AppTest.from_file(Path(__file__).resolve().parents[1]/'app.py',default_timeout=60)
    at.secrets={'APP_PASSWORD':'test-password','KIS_APP_KEY':'test-key-unique',
                'KIS_APP_SECRET':'test-secret-unique','KIS_CANO':'00123456'}
    at.run()
    at.text_input[0].set_value('test-password');at.button[0].click().run()
    at.sidebar.radio[0].set_value('모의투자 계좌').run()
    assert not at.exception
    rows=at.dataframe[0].value
    assert rows.iloc[0]['설정 상태']=='인식됨'
    assert 'test-key-unique' not in rows.to_string()
    from mpe.connectors import KISDemo,APIError
    reached=[]
    def balance(client):
        reached.append((client.key,client.secret,client.cano,client.product))
        raise APIError('테스트 연결 지점')
    monkeypatch.setattr(KISDemo,'balance',balance)
    next(b for b in at.button if b.label=='잔고 새로고침').click().run()
    assert reached==[('test-key-unique','test-secret-unique','00123456','01')]
    assert not at.exception
