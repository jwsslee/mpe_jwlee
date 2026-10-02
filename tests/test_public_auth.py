import pytest
import requests
from mpe.connectors import json_request,PublicData,APIError


def test_public_403_actionable_without_response_secret(monkeypatch):
    response=requests.Response();response.status_code=403
    response._content=b'<html>sensitive-key-should-never-display</html>'
    monkeypatch.setattr(requests,'request',lambda *args,**kwargs:response)
    with pytest.raises(APIError) as err:
        json_request('GET',PublicData.BASE+'GetStockSecuritiesInfoService/getStockPriceInfo')
    assert '변경신청' in str(err.value) and '403' in str(err.value)
    assert 'sensitive-key' not in str(err.value)


def test_service_key_encoding_exactly_once():
    for value in [' abc+/= ', 'abc%2B%2F%3D']:
        key=PublicData(value).key
        req=requests.Request('GET','https://apis.data.go.kr/',params={'serviceKey':key}).prepare()
        assert 'serviceKey=abc%2B%2F%3D' in req.url
        assert '%252B' not in req.url
