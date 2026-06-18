from ev_watch import notifier


class _Resp:
    def __init__(self, status=200, payload=None):
        self.status_code = status
        self._payload = payload or {"ok": True}

    def json(self):
        return self._payload


def test_send_telegram_success_posts_once():
    calls = []

    def fake_post(url, json=None, timeout=None):
        calls.append((url, json))
        return _Resp(200)

    ok = notifier.send_telegram("TOK", "42", "hi", post=fake_post, sleep=lambda s: None)
    assert ok is True
    assert len(calls) == 1
    assert "botTOK/sendMessage" in calls[0][0]
    assert calls[0][1]["chat_id"] == "42"
    assert calls[0][1]["text"] == "hi"


def test_send_telegram_retries_then_succeeds():
    seq = [_Resp(500), _Resp(500), _Resp(200)]

    def fake_post(url, json=None, timeout=None):
        return seq.pop(0)

    ok = notifier.send_telegram("T", "1", "x", post=fake_post, sleep=lambda s: None, max_retries=3)
    assert ok is True


def test_send_telegram_all_fail_returns_false():
    def fake_post(url, json=None, timeout=None):
        return _Resp(500)

    ok = notifier.send_telegram("T", "1", "x", post=fake_post, sleep=lambda s: None, max_retries=2)
    assert ok is False


def test_get_chat_id_extracts_last():
    def fake_get(url, timeout=None):
        return _Resp(200, {"ok": True, "result": [
            {"message": {"chat": {"id": 111}}},
            {"message": {"chat": {"id": 222}}},
        ]})

    assert notifier.get_chat_id("T", get=fake_get) == "222"


def test_get_chat_id_empty_returns_none():
    def fake_get(url, timeout=None):
        return _Resp(200, {"ok": True, "result": []})

    assert notifier.get_chat_id("T", get=fake_get) is None
