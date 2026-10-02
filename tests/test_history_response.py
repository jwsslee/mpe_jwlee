from datetime import date
import pytest
from core.api import parse_history_rows,APIError,KIS
from core.state import collect

START=date(2026,10,1)
END=date(2026,10,2)


def test_empty_padding_and_trimmed_numeric_dates():
    rows=parse_history_rows([None,'',{}, {'stck_bsop_date':'  ','stck_clpr':''},
        {'stck_bsop_date':' 20261001 ','stck_clpr':'1,000'},
        {'stck_bsop_date':20261002,'stck_clpr':'1100'}],START,END)
    assert [r['close'] for r in rows]==[1000,1100]
    assert [r['date'] for r in rows]==['2026-10-01','2026-10-02']


@pytest.mark.parametrize('raw,stage',[
    ([{'stck_bsop_date':'NaT','stck_clpr':'100'}],'history.date'),
    ([{'stck_bsop_date':'20260230','stck_clpr':'100'}],'history.date'),
    ([{'stck_clpr':'100'}],'history.date'),
    ([['invalid']],'history.row'),
    ({},'history.rows'),
    ([{'stck_bsop_date':'20261001','stck_clpr':'invalid'}],'history.close'),
])
def test_bad_rows_have_safe_specific_errors(raw,stage):
    with pytest.raises(APIError,match=stage):parse_history_rows(raw,START,END)


def test_old_result_retained_and_unexpected_message_redacted():
    cache={};collect(cache,'history',lambda:42)
    def failure():raise TypeError('secret-account-and-key-must-not-display')
    entry=collect(cache,'history',failure,force=True)
    assert entry['data']==42 and 'TypeError' in entry['error']
    assert 'secret-account' not in entry['error']


def test_history_reports_date_window(monkeypatch):
    monkeypatch.setattr(KIS,'get',lambda *a:({'output2':[{'stck_bsop_date':'NaT','stck_clpr':'100'}]},{}))
    with pytest.raises(APIError,match='조회 구간'):KIS('k','s').history('353200')
