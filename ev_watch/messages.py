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


def _status_line(s: str, limit: int = 60) -> str:
    """일일 보고서용 짧은 상태 한 줄. 공고문이 ★…★ 머리말이면 그 부분만,
    아니면 limit자까지 자르고 …를 붙인다. (전체 공고문은 변화 알림 diff로 확인)"""
    s = (s or "").strip()
    if s.startswith("★") and s.count("★") >= 2:
        return s[: s.index("★", 1) + 1]
    return s if len(s) <= limit else s[:limit].rstrip() + "…"


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


def _comma(v) -> str:
    """천단위 콤마. 정수가 아니면(없음 등) '-'."""
    return f"{v:,}" if isinstance(v, int) else "-"


def format_daily_report(rows: list[dict], deltas: dict, now_str: str, url: str) -> str:
    parts = [
        "📋 *성남시 전기차 보조금 일일 현황*",
        f"🗓 {now_str} KST",
    ]
    for r in rows:
        차종 = r.get("차종", "")
        d = deltas.get(차종)
        files = " · ".join(_fmt_file(f) for f in r.get("공고파일", [])) or "-"
        parts.append("")
        parts.append(f"🚙 *{차종}*")
        parts.append(
            f"🔋 *잔여대수 {_comma(_num(r,'출고잔여대수'))}대*"
            f"  (일반 {_comma(_num(r,'출고잔여대수','일반'))})"
        )
        if d is not None:
            parts.append(f"📉 전일 대비 {d:+d}대")
        parts.append("─────────────")
        parts.append(
            f"공고 {_comma(_num(r,'민간공고대수'))}"
            f" · 접수 {_comma(_num(r,'접수대수'))}"
            f" · 출고 {_comma(_num(r,'출고대수'))}"
        )
        parts.append(f"📎 {files}")
        parts.append(f"📌 {_status_line(r.get('비고',''))}")
    parts.append("")
    parts.append(f"🔗 {url}")
    return "\n".join(parts)


def format_startup(rows: list[dict], url: str) -> str:
    remark = _first_line(rows[0].get("비고", "")) if rows else "(데이터 없음)"
    return (
        "✅ *성남시 보조금 감시 시작*\n"
        f"현재 상태: {remark}\n"
        f"🔗 {url}"
    )
