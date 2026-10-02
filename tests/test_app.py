from pathlib import Path
from streamlit.testing.v1 import AppTest


def test_all_pages_and_interactions(monkeypatch):
    monkeypatch.chdir(Path(__file__).parents[1])
    monkeypatch.delenv('APP_PASSWORD',raising=False)
    at=AppTest.from_file(Path(__file__).resolve().parents[1] / 'app.py',default_timeout=60).run()
    assert not at.exception
    for demo in [False,True]:
        at.toggle[0].set_value(demo).run()
        for page in at.sidebar.radio[0].options:
            at.sidebar.radio[0].set_value(page).run()
            assert not at.exception, (demo,page)
    at.sidebar.radio[0].set_value('관심종목 · 투자 노트').run()
    at.text_area[0].set_value('검증 메모')
    next(b for b in at.button if b.label=='노트 반영').click().run()
    assert not at.exception
    assert at.session_state.demo_data['notes'].thesis.iloc[0]=='검증 메모'
    at.sidebar.radio[0].set_value('시나리오 · 전략 검증').run()
    next(b for b in at.button if b.label=='검증 실행').click().run()
    assert not at.exception
    at.sidebar.radio[0].set_value('모의투자 계좌').run()
    next(b for b in at.button if b.label=='잔고 새로고침').click().run()
    assert not at.exception and at.error


def test_password_gate(monkeypatch):
    monkeypatch.chdir(Path(__file__).parents[1])
    monkeypatch.setenv('APP_PASSWORD','test-only-private-password')
    at=AppTest.from_file(Path(__file__).resolve().parents[1] / 'app.py',default_timeout=60).run()
    assert not at.sidebar.radio
    at.text_input[0].set_value('test-only-private-password')
    at.button[0].click().run()
    assert at.sidebar.radio and not at.exception
