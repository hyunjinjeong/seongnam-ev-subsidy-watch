from ev_watch import config
from ev_watch.parse import normalize_text, normalize_multiline, parse_int

def test_config_constants():
    assert config.SEONGNAM_CODE == "4113"
    assert config.GYEONGGI_CODE == "4100"
    assert config.NUMBER_KEYS[0] == "전체"
    assert config.STATE_PATH.endswith("seongnam.json")

def test_normalize_text_collapses_whitespace():
    assert normalize_text("  a\n\n b   c \t") == "a b c"

def test_normalize_multiline_keeps_line_breaks():
    assert normalize_multiline("  가  나 \n\n  다   라  \n") == "가 나\n\n다 라"

def test_parse_int_handles_commas_and_blanks():
    assert parse_int("1,949") == 1949
    assert parse_int("0") == 0
    assert parse_int("-204") == -204
    assert parse_int("") is None
    assert parse_int("-") is None
    assert parse_int(None) is None


from ev_watch.scraper import _row_from_raw

_GRID = {
    "시도": "경기", "시군구": "성남시", "차종": "전기승용",
    "공고종류": "[본공고]",
    "접수기간": "2026.02.09 10:00 ~ 2026.05.13 18:00",
    "신청마감": "2026.05.18 18:00",
}
_DETAIL = {
    "공고파일": ["본공고 1", "본공고 2", "본공고 3"],
    "접수방법": "접수방법: *일반: 출고등록순 / *우선: 출고등록순",
    "비고": "  ★ 성남시 공고 마감 \n\n ○ 접수기간: 2026. 2. 9. ",
    "대수": [
        {"구분": "전체", "tcnt": "1,949", "recei": "1,745", "choice": "1,745",
         "relea": "1,745", "choiceRemain": "204", "resi": "204"},
        {"구분": "우선순위", "tcnt": "0", "recei": "550", "choice": "550",
         "relea": "550", "choiceRemain": "0", "resi": "0"},
        {"구분": "일반", "tcnt": "1,949", "recei": "1,086", "choice": "1,086",
         "relea": "1,086", "choiceRemain": "863", "resi": "863"},
        # 가운뎃점 포함 표기 → '법인기관' 키로 정규화되어야 한다
        {"구분": "법인·기관", "tcnt": "0", "recei": "49", "choice": "49",
         "relea": "49", "choiceRemain": "0", "resi": "0"},
        {"구분": "택시", "tcnt": "0", "recei": "60", "choice": "60",
         "relea": "60", "choiceRemain": "0", "resi": "0"},
    ],
}

def test_row_from_raw_maps_grid_and_detail():
    r = _row_from_raw(_GRID, _DETAIL)
    assert r["시도"] == "경기"
    assert r["시군구"] == "성남시"
    assert r["차종"] == "전기승용"
    assert r["공고종류"] == "본공고"          # 대괄호 제거
    assert r["신청마감"] == "2026.05.18 18:00"
    assert r["공고파일"] == ["본공고 1", "본공고 2", "본공고 3"]
    assert r["접수방법"] == "*일반: 출고등록순 / *우선: 출고등록순"  # '접수방법:' 접두어 제거

def test_row_from_raw_builds_number_dicts_by_category():
    r = _row_from_raw(_GRID, _DETAIL)
    assert r["민간공고대수"] == {
        "전체": 1949, "우선순위": 0, "법인기관": 0, "택시": 0, "일반": 1949}
    assert r["출고잔여대수"] == {
        "전체": 204, "우선순위": 0, "법인기관": 0, "택시": 0, "일반": 863}
    assert r["접수대수"]["전체"] == 1745
    assert r["출고대수"]["일반"] == 1086
    # 새 페이지에서 추가된 '선정' 지표
    assert r["선정대수"]["전체"] == 1745
    assert r["선정잔여대수"]["일반"] == 863

def test_row_from_raw_keeps_remark_line_breaks():
    r = _row_from_raw(_GRID, _DETAIL)
    assert r["비고"] == "★ 성남시 공고 마감\n\n○ 접수기간: 2026. 2. 9."

def test_row_from_raw_missing_categories_become_none():
    detail = {**_DETAIL, "대수": [{"구분": "전체", "tcnt": "10", "recei": "5",
                                   "choice": "5", "relea": "5",
                                   "choiceRemain": "5", "resi": "5"}]}
    r = _row_from_raw(_GRID, detail)
    assert r["민간공고대수"] == {
        "전체": 10, "우선순위": None, "법인기관": None, "택시": None, "일반": None}

def test_row_from_raw_tolerates_empty_detail():
    r = _row_from_raw(_GRID, {})
    assert r["비고"] == ""
    assert r["공고파일"] == []
    assert r["출고잔여대수"]["전체"] is None
