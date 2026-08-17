import html
import re

from .state import diff_remark_hunks

# 텔레그램 메시지 상한은 4096자. 접기(blockquote) 본문을 자를 때 쓰는 여유분.
TELEGRAM_LIMIT = 4096
_BODY_BUDGET = 2600


def _esc(s) -> str:
    """텔레그램 HTML parse_mode용 이스케이프. 비고 원문에 <, & 가 섞여도 안전하게."""
    return html.escape(str(s if s is not None else ""), quote=False)


def _clip(lines: list[str], budget: int = _BODY_BUDGET) -> list[str]:
    """길면 자르되, 잘랐다는 사실을 반드시 남긴다(조용한 유실 방지)."""
    out: list[str] = []
    used = 0
    for i, line in enumerate(lines):
        if used + len(line) + 1 > budget:
            out.append(f"…… 외 {len(lines) - i}줄 생략")
            break
        out.append(line)
        used += len(line) + 1
    return out


def _quote(lines: list[str], budget: int = _BODY_BUDGET) -> str:
    """긴 내용은 접히는 인용문으로. 텔레그램이 4줄 넘으면 '더 보기'로 접어준다."""
    body = "\n".join(_esc(x) for x in _clip(lines, budget))
    return f"<blockquote expandable>{body}</blockquote>"


def _fmt_file(s: str) -> str:
    """'라벨|코드' → '라벨 (코드)'. 개편 전 state에 남아있는 형식 호환용."""
    if "|" in s:
        label, code = s.split("|", 1)
        return f"{label} ({code})" if code else label
    return s


def _first_line(s: str) -> str:
    return (s or "").strip().splitlines()[0] if (s or "").strip() else ""


_REMARK_BREAK = re.compile(r"\s*(○|※|\* |-{3,})")


def _format_remark(s: str) -> str:
    """○/※/* 불릿과 구분선 앞에 줄바꿈을 넣어 읽기 좋게 만든다(내용은 그대로)."""
    s = (s or "").strip()
    return _REMARK_BREAK.sub(lambda m: "\n" + m.group(1), s).strip()


# --- 변화 감지 --------------------------------------------------------------

# 값이 바뀌면 요약 한 줄로 알린다. 해시 대상이기도 해서 이 셋이 알림 트리거다.
_TEXT_FIELDS = [
    ("공고종류", "📌", "공고종류"),
    ("접수기간", "📅", "접수기간"),
    ("신청마감", "🗓", "신청마감"),
]
# 대수는 알림 트리거가 아니다(15분마다 변함). 알림이 뜰 때 맥락으로만 덧붙인다.
_NUMBER_FIELDS = [
    ("민간공고대수", "📦", "공고대수"),
    ("출고잔여대수", "🔢", "출고잔여"),
]


def _summary_lines(old_rows: list[dict], new_rows: list[dict]) -> list[str]:
    old_map = {r.get("차종", ""): r for r in old_rows}
    multi = len(new_rows) > 1
    lines = []
    for new in new_rows:
        car = new.get("차종", "")
        old = old_map.get(car)
        if old is None:
            lines.append(f"🆕 <b>{_esc(car)}</b> 신규 등장")
            continue
        tag = f"[{_esc(car)}] " if multi else ""
        for key, icon, label in _TEXT_FIELDS:
            o, n = old.get(key), new.get(key)
            # 개편 전 state에는 없던 필드다. 한쪽이 비면 '→' 노이즈를 만들지 않는다.
            if o and n and o != n:
                lines.append(f"{icon} {tag}{label}  {_esc(o)} → <b>{_esc(n)}</b>")
        for key, icon, label in _NUMBER_FIELDS:
            o = (old.get(key) or {}).get("전체")
            n = (new.get(key) or {}).get("전체")
            if isinstance(o, int) and isinstance(n, int) and o != n:
                lines.append(f"{icon} {tag}{label}  {o:,} → <b>{n:,}</b>대")
    return lines


def _files(rows: list[dict]) -> set[str]:
    return {f for r in rows for f in r.get("공고파일", [])}


def _remark(rows: list[dict]) -> str:
    return "\n".join(r.get("비고", "") for r in rows)


def format_change_alert(old_rows: list[dict], new_rows: list[dict], url: str) -> str | None:
    """변화 알림 본문. 보여줄 변화가 하나도 없으면 None(= 발송하지 않음)."""
    summary = _summary_lines(old_rows, new_rows)
    added = sorted(_files(new_rows) - _files(old_rows))
    removed = sorted(_files(old_rows) - _files(new_rows))
    hunks = diff_remark_hunks(_remark(old_rows), _remark(new_rows))
    if not (summary or added or removed or hunks):
        return None

    parts = ["🔔 <b>성남시 전기차 보조금 공고 변화 감지</b>", ""]
    parts += summary
    if added:
        parts.append(f"➕ 공고파일  {_esc(', '.join(_fmt_file(f) for f in added))}")
    if removed:
        parts.append(f"➖ 공고파일  {_esc(', '.join(_fmt_file(f) for f in removed))}")
    if hunks:
        parts += ["", f"📝 비고 변경 ({len(hunks)}곳)",
                  _quote([line for hunk in hunks for line in hunk])]
    parts += ["", f"🔗 {_esc(url)}"]
    return "\n".join(parts)


# --- 일일 보고서 ------------------------------------------------------------

def _num(row: dict, col: str, key: str = "전체"):
    v = (row.get(col) or {}).get(key)
    return v if v is not None else "-"


def _comma(v) -> str:
    return f"{v:,}" if isinstance(v, int) else "-"


def format_daily_report(rows: list[dict], deltas: dict, now_str: str, url: str) -> str:
    parts = [
        "📋 <b>성남시 전기차 보조금 일일 현황</b>",
        f"🗓 {_esc(now_str)} KST",
    ]
    # 비고가 여러 차종이면 예산을 나눠 써야 4096자 안에 들어온다
    budget = max(400, _BODY_BUDGET // max(1, len(rows)))
    for r in rows:
        차종 = r.get("차종", "")
        d = deltas.get(차종)
        files = " · ".join(_fmt_file(f) for f in r.get("공고파일", [])) or "-"
        parts.append("")
        parts.append(f"🚙 <b>{_esc(차종)}</b>")
        parts.append(
            f"🔋 <b>잔여대수 {_comma(_num(r, '출고잔여대수'))}대</b>"
            f"  (일반 {_comma(_num(r, '출고잔여대수', '일반'))})"
        )
        if d is not None:
            parts.append(f"📉 전일 대비 {d:+d}대")
        parts.append("─────────────")
        parts.append(
            f"공고 {_comma(_num(r, '민간공고대수'))}"
            f" · 접수 {_comma(_num(r, '접수대수'))}"
            f" · 출고 {_comma(_num(r, '출고대수'))}"
        )
        parts.append("")
        parts.append(f"📎 {_esc(files)}")
        parts.append("")
        parts.append("📌 비고")
        parts.append(_quote(_format_remark(r.get("비고", "")).splitlines(), budget))
    parts.append("")
    parts.append(f"🔗 {_esc(url)}")
    return "\n".join(parts)


def format_startup(rows: list[dict], url: str) -> str:
    remark = _first_line(rows[0].get("비고", "")) if rows else "(데이터 없음)"
    return (
        "✅ <b>성남시 보조금 감시 시작</b>\n"
        f"현재 상태: {_esc(remark)}\n"
        f"🔗 {_esc(url)}"
    )
