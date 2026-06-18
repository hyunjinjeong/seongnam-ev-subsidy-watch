from .state import diff_remark

_KEYWORDS = ["추경", "접수", "공고", "마감"]


def keyword_flags(rows: list[dict]) -> dict[str, bool]:
    text = " ".join(r.get("비고", "") for r in rows)
    return {k: (k in text) for k in _KEYWORDS}


def _codes(rows: list[dict]) -> set[str]:
    return {f for r in rows for f in r.get("공고파일", [])}


def _fmt_file(s: str) -> str:
    """Format '라벨|코드' to '라벨 (코드)'. If no |, return as-is."""
    if "|" in s:
        label, code = s.split("|", 1)
        return f"{label} ({code})"
    return s


def _first_line(s: str) -> str:
    return (s or "").strip().splitlines()[0] if (s or "").strip() else ""


def format_change_alert(old_rows: list[dict], new_rows: list[dict], url: str) -> str:
    flags = keyword_flags(new_rows)
    flag_line = " ".join(f"{k}={'✅' if v else '⬜'}" for k, v in flags.items())
    old_remark = " ".join(r.get("비고", "") for r in old_rows)
    new_remark = " ".join(r.get("비고", "") for r in new_rows)
    diff = diff_remark(old_remark, new_remark)
    added = sorted(_codes(new_rows) - _codes(old_rows))
    removed = sorted(_codes(old_rows) - _codes(new_rows))
    parts = [
        "🔔 *성남시 전기차 보조금 공고 변화 감지*",
        f"키워드: {flag_line}",
    ]
    if added:
        parts.append(f"➕ 공고파일 추가: {', '.join(_fmt_file(f) for f in added)}")
    if removed:
        parts.append(f"➖ 공고파일 삭제: {', '.join(_fmt_file(f) for f in removed)}")
    if diff.strip():
        parts.append("📝 비고 변경:\n```\n" + diff + "\n```")
    parts.append(f"🔗 {url}")
    return "\n".join(parts)


def _num(row: dict, col: str, key: str = "전체"):
    v = (row.get(col) or {}).get(key)
    return v if v is not None else "-"


def format_daily_report(rows: list[dict], deltas: dict, now_str: str, url: str) -> str:
    parts = [f"📋 *성남시 전기차 보조금 일일 현황* ({now_str} KST)"]
    for r in rows:
        차종 = r.get("차종", "")
        d = deltas.get(차종)
        delta_str = "" if d is None else f" [전일 {d:+d}]"
        잔여전체 = _num(r, "출고잔여대수")
        잔여일반 = _num(r, "출고잔여대수", "일반")
        parts.append(
            f"\n*{차종}*\n"
            f"· 잔여대수: 전체 {잔여전체} (일반 {잔여일반}){delta_str}\n"
            f"· 접수 {_num(r,'접수대수')} / 출고 {_num(r,'출고대수')} / 공고 {_num(r,'민간공고대수')}\n"
            f"· 공고파일: {', '.join(r.get('공고파일', [])) or '-'}\n"
            f"· 비고: {_first_line(r.get('비고',''))}"
        )
    parts.append(f"\n🔗 {url}")
    return "\n".join(parts)


def format_startup(rows: list[dict], url: str) -> str:
    remark = _first_line(rows[0].get("비고", "")) if rows else "(데이터 없음)"
    return (
        "✅ *성남시 보조금 감시 시작*\n"
        f"현재 상태: {remark}\n"
        f"🔗 {url}"
    )
