# check.py — CLI 엔트리 (레포 루트)
import argparse
import os
import sys
from ev_watch import config, state, messages, scraper, notifier

def _save_failure(state_path, url, send):
    st = state.load_state(state_path) or {}
    st["consecutive_failures"] = st.get("consecutive_failures", 0) + 1
    state.save_state(state_path, st)
    if st["consecutive_failures"] >= config.CONSECUTIVE_FAILURE_THRESHOLD:
        send(f"⚠️ 성남시 보조금 체크 실패 {st['consecutive_failures']}회 연속\n🔗 {url}")
    return "fail"

def do_change(fetch, send, *, state_path, url, now_iso):
    try:
        rows = fetch()
    except Exception:
        return _save_failure(state_path, url, send)
    new_hash = state.compute_change_hash(rows)
    prev = state.load_state(state_path)
    base = {**(prev or {}), "consecutive_failures": 0,
            "hash": new_hash, "rows": rows, "fetched_at": now_iso}
    if prev is None or prev.get("hash") is None:
        send(messages.format_startup(rows, url))
        state.save_state(state_path, base)
        return "first"
    if prev.get("hash") == new_hash:
        # 변화 없음: 매번 rewrite하면 15분마다 state 커밋이 쌓이므로(churn),
        # 직전에 실패 카운트가 남아있을 때만 리셋 저장한다.
        if prev.get("consecutive_failures"):
            prev["consecutive_failures"] = 0
            state.save_state(state_path, prev)
        return "nochange"
    send(messages.format_change_alert(prev.get("rows", []), rows, url))
    state.save_state(state_path, base)
    return "changed"

def do_daily(fetch, send, *, state_path, url, now_str):
    try:
        rows = fetch()
    except Exception:
        return _save_failure(state_path, url, send)
    prev = state.load_state(state_path) or {}
    today_nums = state.report_numbers(rows)
    deltas = state.compute_deltas(today_nums, prev.get("last_report"))
    send(messages.format_daily_report(rows, deltas, now_str, url))
    prev["consecutive_failures"] = 0
    prev["last_report"] = today_nums
    state.save_state(state_path, prev)
    return "ok"

def _env(name):
    v = os.environ.get(name)
    if not v:
        print(f"환경변수 {name} 없음", file=sys.stderr)
        sys.exit(2)
    return v

def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["change", "daily"])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--get-chat-id", action="store_true")
    ap.add_argument("--test-telegram", action="store_true")
    args = ap.parse_args(argv)

    from datetime import datetime
    now = datetime.now(config.KST)

    if args.get_chat_id:
        print(notifier.get_chat_id(_env("TELEGRAM_BOT_TOKEN")) or "(업데이트 없음 — 봇에게 먼저 /start)")
        return 0

    token = chat_id = None
    if not args.dry_run:
        token, chat_id = _env("TELEGRAM_BOT_TOKEN"), _env("TELEGRAM_CHAT_ID")

    def send(text):
        if args.dry_run:
            print("[DRY-RUN 전송]\n" + text)
            return True
        return notifier.send_telegram(token, chat_id, text)

    if args.test_telegram:
        send(f"✅ 연결 테스트 ({now:%Y-%m-%d %H:%M} KST)")
        return 0

    if args.dry_run and not args.mode:
        import json
        print(json.dumps(scraper.fetch_seongnam_rows(), ensure_ascii=False, indent=2))
        return 0

    if args.mode == "change":
        do_change(scraper.fetch_seongnam_rows, send,
                  state_path=config.STATE_PATH, url=config.URL, now_iso=now.isoformat())
    elif args.mode == "daily":
        do_daily(scraper.fetch_seongnam_rows, send,
                 state_path=config.STATE_PATH, url=config.URL, now_str=f"{now:%Y-%m-%d %H:%M}")
    else:
        ap.error("--mode 또는 --get-chat-id/--test-telegram/--dry-run 중 하나 필요")
    return 0

if __name__ == "__main__":
    sys.exit(main())
