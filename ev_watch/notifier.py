import time
import httpx

_API = "https://api.telegram.org/bot{token}/{method}"


def send_telegram(token, chat_id, text, *, post=None, sleep=None, max_retries=3):
    """
    Send a message via Telegram with exponential backoff retry.

    Args:
        token: Telegram bot token
        chat_id: Target chat ID (converted to string)
        text: Message text
        post: Optional injected POST function (defaults to httpx.post)
        sleep: Optional injected sleep function (defaults to time.sleep)
        max_retries: Maximum retry attempts

    Returns:
        True if message sent successfully, False after all retries exhausted
    """
    post = post or httpx.post
    sleep = sleep or time.sleep
    url = _API.format(token=token, method="sendMessage")
    payload = {
        "chat_id": str(chat_id),
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }
    for attempt in range(max_retries):
        try:
            resp = post(url, json=payload, timeout=20)
            if resp.status_code == 200 and resp.json().get("ok", True):
                return True
        except Exception:
            pass
        if attempt < max_retries - 1:
            sleep(2 ** attempt)  # 1s, 2s, 4s, ...
    return False


def get_chat_id(token, *, get=None):
    """
    Extract the last message's chat ID from Telegram getUpdates.

    Args:
        token: Telegram bot token
        get: Optional injected GET function (defaults to httpx.get)

    Returns:
        Chat ID as string, or None if no messages found
    """
    get = get or httpx.get
    url = _API.format(token=token, method="getUpdates")
    resp = get(url, timeout=20)
    results = resp.json().get("result", [])
    for upd in reversed(results):
        chat = (upd.get("message") or {}).get("chat") or {}
        if "id" in chat:
            return str(chat["id"])
    return None
