from ev_watch import state


def _row(비고="공고 마감", 공고파일=None, 차종="전기승용", 잔여=209):
    return {
        "차종": 차종,
        "공고파일": 공고파일 if 공고파일 is not None else ["본공고 1|A", "본공고 2|A02"],
        "접수방법": "*일반: 출고등록순",
        "비고": 비고,
        "출고잔여대수": {"전체": 잔여},
    }


def test_hash_ignores_numbers_and_whitespace():
    a = _row(잔여=209)
    b = _row(잔여=5)            # 숫자만 다름
    b["접수대수"] = {"전체": 1}  # 숫자 컬럼 추가돼도
    assert state.compute_change_hash([a]) == state.compute_change_hash([b])


def test_hash_changes_when_remark_changes():
    a = _row(비고="공고 마감")
    b = _row(비고="추경 공고 접수 시작")
    assert state.compute_change_hash([a]) != state.compute_change_hash([b])


def test_hash_changes_when_files_change():
    a = _row(공고파일=["본공고 1|A"])
    b = _row(공고파일=["본공고 1|A", "추경공고|B"])
    assert state.compute_change_hash([a]) != state.compute_change_hash([b])


def test_hash_order_independent_for_files():
    a = _row(공고파일=["본공고 1|A", "본공고 2|A02"])
    b = _row(공고파일=["본공고 2|A02", "본공고 1|A"])
    assert state.compute_change_hash([a]) == state.compute_change_hash([b])


def test_load_missing_returns_none(tmp_path):
    assert state.load_state(str(tmp_path / "none.json")) is None


def test_save_then_load_roundtrip(tmp_path):
    p = str(tmp_path / "s.json")
    state.save_state(p, {"hash": "abc", "비고": "추경"})
    assert state.load_state(p) == {"hash": "abc", "비고": "추경"}


def test_diff_remark_shows_change():
    d = state.diff_remark("공고 마감", "추경 공고 접수 시작")
    assert "공고 마감" in d and "추경 공고 접수 시작" in d


def test_report_numbers_extracts_total():
    rows = [_row(차종="전기승용", 잔여=209)]
    assert state.report_numbers(rows) == [{"차종": "전기승용", "출고잔여대수_전체": 209}]


def test_compute_deltas_matches_by_차종():
    today = [{"차종": "전기승용", "출고잔여대수_전체": 200}]
    last = [{"차종": "전기승용", "출고잔여대수_전체": 209}]
    assert state.compute_deltas(today, last) == {"전기승용": -9}


def test_compute_deltas_none_when_no_last():
    today = [{"차종": "전기승용", "출고잔여대수_전체": 200}]
    assert state.compute_deltas(today, None) == {"전기승용": None}
