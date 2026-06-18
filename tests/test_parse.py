from ev_watch import config

def test_config_constants():
    assert config.SEONGNAM_CODE == "4113"
    assert config.GYEONGGI_CODE == "4100"
    assert config.NUMBER_KEYS[0] == "전체"
    assert config.STATE_PATH.endswith("seongnam.json")
