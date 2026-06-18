from ev_watch import config
from ev_watch.parse import normalize_text, parse_number_cell

def test_config_constants():
    assert config.SEONGNAM_CODE == "4113"
    assert config.GYEONGGI_CODE == "4100"
    assert config.NUMBER_KEYS[0] == "전체"
    assert config.STATE_PATH.endswith("seongnam.json")

def test_normalize_text_collapses_whitespace():
    assert normalize_text("  a\n\n b   c \t") == "a b c"

def test_parse_number_cell_basic():
    assert parse_number_cell("1949 (0)(0)(0)(1949)") == {
        "전체": 1949, "우선순위": 0, "법인기관": 0, "택시": 0, "일반": 1949,
    }

def test_parse_number_cell_with_commas_and_spaces():
    assert parse_number_cell("2,092 (550) (49) (60) (1,086)") == {
        "전체": 2092, "우선순위": 550, "법인기관": 49, "택시": 60, "일반": 1086,
    }

def test_parse_number_cell_missing_values_are_none():
    assert parse_number_cell("209") == {
        "전체": 209, "우선순위": None, "법인기관": None, "택시": None, "일반": None,
    }

from ev_watch.scraper import _rows_from_raw

def test_rows_from_raw_parses_numbers_and_keeps_text():
    raw = [{
        "시도": "경기", "차종": "전기승용",
        "공고파일": ["본공고 1|A", "본공고 2|A02"],
        "접수방법": "*일반: 출고등록순",
        "민간공고대수_raw": "1949 (0)(0)(0)(1949)",
        "접수대수_raw": "1745 (550)(49)(60)(1086)",
        "출고대수_raw": "1740 (549)(49)(60)(1082)",
        "출고잔여대수_raw": "209 (0)(0)(0)(867)",
        "비고": "  ★ 성남시 ... 공고 마감 ",
    }]
    rows = _rows_from_raw(raw)
    assert len(rows) == 1
    r = rows[0]
    assert r["차종"] == "전기승용"
    assert r["공고파일"] == ["본공고 1|A", "본공고 2|A02"]
    assert r["민간공고대수"]["전체"] == 1949
    assert r["출고잔여대수"]["일반"] == 867
    assert r["비고"] == "★ 성남시 ... 공고 마감"   # 정규화됨
