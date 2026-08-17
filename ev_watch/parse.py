import re

_WS = re.compile(r"\s+")
_INLINE_WS = re.compile(r"[^\S\n]+")

def normalize_text(s: str) -> str:
    return _WS.sub(" ", s or "").strip()

def normalize_multiline(s: str) -> str:
    """줄바꿈은 보존하고 각 줄 내부 공백만 정리한다(비고 원문 구조 유지용)."""
    lines = [_INLINE_WS.sub(" ", line).strip() for line in (s or "").splitlines()]
    return "\n".join(lines).strip()

def parse_int(text: str | None) -> int | None:
    """'1,949' → 1949. 숫자가 없으면 None."""
    m = re.search(r"-?\d[\d,]*", text or "")
    return int(m.group(0).replace(",", "")) if m else None
