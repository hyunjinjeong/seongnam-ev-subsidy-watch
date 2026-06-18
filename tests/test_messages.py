from ev_watch import messages


def _row(비고, 공고파일, 차종="전기승용"):
    return {
        "차종": 차종, "공고파일": 공고파일, "접수방법": "*일반",
        "비고": 비고,
        "민간공고대수": {"전체": 1949}, "접수대수": {"전체": 1745},
        "출고대수": {"전체": 1740}, "출고잔여대수": {"전체": 209, "일반": 867},
    }


def test_keyword_flags():
    rows = [_row("추경예산 확보 후 공고 및 접수 예정", ["본공고 1|A"])]
    f = messages.keyword_flags(rows)
    assert f == {"추경": True, "접수": True, "공고": True, "마감": False}


def test_change_alert_contains_diff_and_file_change_and_link():
    old = [_row("공고 마감", ["본공고 1|A"])]
    new = [_row("추경 접수 시작", ["본공고 1|A", "추경공고|B"])]
    msg = messages.format_change_alert(old, new, "http://x")
    assert "변화 감지" in msg
    assert "추경 접수 시작" in msg      # diff에 신규 텍스트
    assert "B" in msg                    # 신규 공고파일 코드
    assert "http://x" in msg


def test_daily_report_shows_remaining_delta_and_date():
    rows = [_row("공고 마감", ["본공고 1|A"])]
    msg = messages.format_daily_report(rows, {"전기승용": -3}, "2026-06-18 08:00", "http://x")
    assert "일일 현황" in msg
    assert "2026-06-18" in msg
    assert "209" in msg                  # 잔여 전체
    assert "-3" in msg                   # 전일 대비
    assert "http://x" in msg


def test_daily_report_handles_none_delta():
    rows = [_row("공고 마감", ["본공고 1|A"])]
    msg = messages.format_daily_report(rows, {"전기승용": None}, "2026-06-18 08:00", "http://x")
    assert "209" in msg   # delta 없어도 현황은 나온다


def test_startup_message():
    rows = [_row("공고 마감", ["본공고 1|A"])]
    msg = messages.format_startup(rows, "http://x")
    assert "감시 시작" in msg and "http://x" in msg
