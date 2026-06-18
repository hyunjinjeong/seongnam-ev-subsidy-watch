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
