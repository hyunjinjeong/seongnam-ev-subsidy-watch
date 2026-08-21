from ev_watch import messages


def _row(비고, 공고파일, 차종="전기승용", **over):
    r = {
        "차종": 차종, "공고파일": 공고파일, "접수방법": "*일반",
        "비고": 비고,
        "공고종류": "본공고", "상태": "마감",
        "접수기간": "2026.02.09 10:00 ~ 2026.05.13 18:00",
        "신청마감": "2026.05.18 18:00",
        "민간공고대수": {"전체": 1949}, "접수대수": {"전체": 1745},
        "출고대수": {"전체": 1740}, "출고잔여대수": {"전체": 209, "일반": 867},
    }
    r.update(over)
    return r


# --- 변화 감지: 구조화 요약 -------------------------------------------------

def test_change_alert_summarises_field_changes():
    old = [_row("공고 마감", ["본공고 1"])]
    new = [_row("공고 마감", ["본공고 1"], 공고종류="추경공고",
                신청마감="2026.06.30 18:00")]
    msg = messages.format_change_alert(old, new, "http://x")
    assert "본공고 → " in msg and "추경공고" in msg
    assert "2026.05.18 18:00 → " in msg and "2026.06.30 18:00" in msg


def test_change_alert_shows_number_context_when_alerting():
    old = [_row("공고 마감", ["본공고 1"])]
    new = [_row("추경 접수 시작", ["본공고 1"],
                출고잔여대수={"전체": 512, "일반": 867})]
    msg = messages.format_change_alert(old, new, "http://x")
    assert "209 → " in msg and "512" in msg     # 천단위 미만은 콤마 없이


def test_change_alert_skips_fields_absent_in_old_state():
    """개편 전 state에는 공고종류/신청마감이 없다. '→' 노이즈를 만들지 않아야 한다."""
    old = [{"차종": "전기승용", "공고파일": ["본공고 1"], "접수방법": "*일반",
            "비고": "공고 마감", "출고잔여대수": {"전체": 209}}]
    new = [_row("추경 접수 시작", ["본공고 1"])]
    msg = messages.format_change_alert(old, new, "http://x")
    assert "공고종류" not in msg
    assert "신청마감" not in msg


def test_change_alert_reports_new_car_type():
    old = [_row("공고 마감", ["본공고 1"])]
    new = [_row("공고 마감", ["본공고 1"]),
           _row("화물 공고", ["본공고 1"], 차종="전기화물")]
    msg = messages.format_change_alert(old, new, "http://x")
    assert "전기화물" in msg and "신규" in msg


# --- 변화 감지: 비고 diff ---------------------------------------------------

def test_change_alert_remark_diff_has_no_unified_diff_noise():
    old = [_row("가\n나\n다", ["본공고 1"])]
    new = [_row("가\n나 수정\n다", ["본공고 1"])]
    msg = messages.format_change_alert(old, new, "http://x")
    assert "@@" not in msg          # hunk 헤더 없음
    assert "--- 이전" not in msg     # diff 헤더 없음
    assert "+++ 현재" not in msg
    body = msg.split("<blockquote expandable>")[1].split("</blockquote>")[0]
    assert body.splitlines() == ["➖ 나", "➕ 나 수정"]   # 바뀐 줄만, context 없음


def test_change_alert_wraps_remark_diff_in_expandable_blockquote():
    old = [_row("가", ["본공고 1"])]
    new = [_row("나", ["본공고 1"])]
    msg = messages.format_change_alert(old, new, "http://x")
    assert "<blockquote expandable>" in msg and "</blockquote>" in msg


def test_change_alert_escapes_html_in_content():
    old = [_row("보통 문구", ["본공고 1"])]
    new = [_row("a < b & c > d", ["본공고 1"])]
    msg = messages.format_change_alert(old, new, "http://x")
    assert "&lt; b &amp; c &gt;" in msg


def test_change_alert_reports_file_changes():
    old = [_row("공고 마감", ["본공고 1"])]
    new = [_row("공고 마감", ["본공고 1", "추경공고 1"])]
    msg = messages.format_change_alert(old, new, "http://x")
    assert "추경공고 1" in msg


def test_change_alert_returns_none_when_nothing_visible_changed():
    """해시만 달라지고 보여줄 내용이 없으면 빈 알림을 보내지 않는다."""
    rows = [_row("공고 마감", ["본공고 1"])]
    assert messages.format_change_alert(rows, rows, "http://x") is None


def test_change_alert_clips_huge_diff_and_says_so():
    old = [_row("\n".join(f"줄 {i}" for i in range(400)), ["본공고 1"])]
    new = [_row("\n".join(f"바뀐 줄 {i}" for i in range(400)), ["본공고 1"])]
    msg = messages.format_change_alert(old, new, "http://x")
    assert len(msg) <= 4096          # 텔레그램 한도
    assert "생략" in msg              # 조용히 자르지 않는다
    assert msg.count("<blockquote expandable>") == msg.count("</blockquote>")


# --- 일일 보고서 ------------------------------------------------------------

def test_daily_report_shows_remaining_delta_and_date():
    rows = [_row("공고 마감", ["본공고 1"])]
    msg = messages.format_daily_report(rows, {"전기승용": -3}, "2026-06-18 08:00", "http://x")
    assert "일일 현황" in msg
    assert "2026-06-18" in msg
    assert "209" in msg
    assert "-3" in msg
    assert "http://x" in msg
    assert "본공고 1" in msg


def test_daily_report_handles_none_delta():
    rows = [_row("공고 마감", ["본공고 1"])]
    msg = messages.format_daily_report(rows, {"전기승용": None}, "2026-06-18 08:00", "http://x")
    assert "209" in msg
    assert "전일 대비" not in msg


def test_daily_report_section_format():
    rows = [_row("공고 마감", ["본공고 1"])]
    msg = messages.format_daily_report(rows, {"전기승용": -3}, "2026-06-18 (목) 08:00", "http://x")
    assert "<b>전기승용</b>" in msg
    assert "잔여대수 209대" in msg
    assert "전일 대비 -3대" in msg
    assert "공고 1,949 · 접수 1,745 · 출고 1,740" in msg


def test_daily_report_keeps_remark_in_code_block():
    long_remark = (
        "★ 성남시 보급사업 공고 마감★\n"
        "※ 예산 조기소진에 따라 추경예산 확보 후 공고 예정입니다.\n"
        "○ 접수기간: 2026. 2. 9.\n"
        "○ 지원대수: 2,092대"
    )
    rows = [_row(long_remark, ["본공고 1"])]
    msg = messages.format_daily_report(rows, {"전기승용": -3}, "2026-06-18 (목) 08:00", "http://x")
    assert "접수기간" in msg and "지원대수" in msg   # 잘리지 않음
    assert "<pre>" in msg and "</pre>" in msg        # 기존 코드블록 모양 유지
    assert "<blockquote" not in msg                  # 접기는 변화 알림에서만


def test_daily_report_shows_status_badge():
    rows = [_row("공고 마감", ["본공고 1"])]
    msg = messages.format_daily_report(rows, {}, "2026-06-18 08:00", "http://x")
    assert "🚦 마감" in msg


def test_daily_report_omits_status_when_absent():
    rows = [_row("공고 마감", ["본공고 1"], 상태="")]
    msg = messages.format_daily_report(rows, {}, "2026-06-18 08:00", "http://x")
    assert "🚦" not in msg


def test_change_alert_shows_status_transition():
    old = [_row("공고 마감", ["본공고 1"])]
    new = [_row("추경 접수 시작", ["본공고 1"], 상태="접수중")]
    msg = messages.format_change_alert(old, new, "http://x")
    assert "마감 → " in msg and "접수중" in msg


def test_daily_report_escapes_html():
    rows = [_row("a < b & c", ["본공고 1"])]
    msg = messages.format_daily_report(rows, {}, "2026-06-18 08:00", "http://x")
    assert "a &lt; b &amp; c" in msg


def test_daily_report_stays_within_telegram_limit():
    rows = [_row("\n".join(f"아주 긴 비고 줄 {i}" for i in range(500)), ["본공고 1"])]
    msg = messages.format_daily_report(rows, {}, "2026-06-18 08:00", "http://x")
    assert len(msg) <= 4096
    assert msg.count("<pre>") == msg.count("</pre>")


def test_startup_message():
    rows = [_row("공고 마감", ["본공고 1"])]
    msg = messages.format_startup(rows, "http://x")
    assert "감시 시작" in msg and "http://x" in msg
