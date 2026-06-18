# tests/test_check.py
import json
import importlib.util, pathlib

# check.py는 레포 루트에 있으므로 경로로 로드
_spec = importlib.util.spec_from_file_location(
    "check", str(pathlib.Path(__file__).resolve().parent.parent / "check.py"))
check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check)

def _row(비고="공고 마감", 공고파일=None, 잔여=209):
    return {
        "차종": "전기승용",
        "공고파일": 공고파일 if 공고파일 is not None else ["본공고 1|A"],
        "접수방법": "*일반", "비고": 비고,
        "민간공고대수": {"전체": 1949}, "접수대수": {"전체": 1745},
        "출고대수": {"전체": 1740}, "출고잔여대수": {"전체": 잔여, "일반": 867},
    }

def _sender():
    sent = []
    def send(text): sent.append(text); return True
    return send, sent

def test_do_change_first_run_sends_startup_and_saves(tmp_path):
    sp = str(tmp_path / "s.json")
    send, sent = _sender()
    code = check.do_change(lambda: [_row()], send, state_path=sp, url="u", now_iso="2026-06-18T08:00:00+09:00")
    assert code == "first"
    assert "감시 시작" in sent[0]
    assert json.load(open(sp, encoding="utf-8"))["hash"]

def test_do_change_no_change_is_silent(tmp_path):
    sp = str(tmp_path / "s.json")
    send, sent = _sender()
    check.do_change(lambda: [_row()], send, state_path=sp, url="u", now_iso="t")  # baseline
    code = check.do_change(lambda: [_row(잔여=5)], send, state_path=sp, url="u", now_iso="t")  # 숫자만 변동
    assert code == "nochange"
    assert len(sent) == 1   # 시작 메시지 1개뿐, 추가 알림 없음

def test_do_change_no_change_does_not_rewrite_state(tmp_path):
    # nochange + 실패카운트 0이면 상태 파일을 다시 쓰지 않아야 함(커밋 churn 방지)
    sp = str(tmp_path / "s.json")
    send, _ = _sender()
    check.do_change(lambda: [_row()], send, state_path=sp, url="u", now_iso="t1")   # baseline
    check.do_change(lambda: [_row(잔여=5)], send, state_path=sp, url="u", now_iso="t2")  # nochange
    assert json.load(open(sp, encoding="utf-8"))["fetched_at"] == "t1"   # t2로 갱신되지 않음

def test_do_change_detects_remark_change(tmp_path):
    sp = str(tmp_path / "s.json")
    send, sent = _sender()
    check.do_change(lambda: [_row("공고 마감")], send, state_path=sp, url="u", now_iso="t")
    code = check.do_change(lambda: [_row("추경 공고 접수 시작")], send, state_path=sp, url="u", now_iso="t")
    assert code == "changed"
    assert "변화 감지" in sent[-1]

def test_do_change_failure_increments_and_alerts_at_threshold(tmp_path):
    sp = str(tmp_path / "s.json")
    send, sent = _sender()
    def boom(): raise RuntimeError("blocked")
    for _ in range(3):
        code = check.do_change(boom, send, state_path=sp, url="u", now_iso="t")
    assert code == "fail"
    assert any("체크 실패" in m for m in sent)            # 3회째 알림
    st = json.load(open(sp, encoding="utf-8"))
    assert st["consecutive_failures"] == 3
    assert "hash" not in st or st.get("hash") is None      # 실패는 해시 미설정

def test_do_daily_sends_report_with_delta(tmp_path):
    sp = str(tmp_path / "s.json")
    # 전일 last_report를 미리 저장
    check.state.save_state(sp, {"last_report": [{"차종": "전기승용", "출고잔여대수_전체": 212}]})
    send, sent = _sender()
    code = check.do_daily(lambda: [_row(잔여=209)], send, state_path=sp, url="u", now_str="2026-06-18 08:00")
    assert code == "ok"
    assert "일일 현황" in sent[0]
    assert "-3" in sent[0]   # 212 -> 209
    assert json.load(open(sp, encoding="utf-8"))["last_report"][0]["출고잔여대수_전체"] == 209
