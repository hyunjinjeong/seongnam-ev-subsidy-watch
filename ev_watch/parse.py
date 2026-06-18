import re
from .config import NUMBER_KEYS

_WS = re.compile(r"\s+")
_NUM = re.compile(r"-?\d[\d,]*")

def normalize_text(s: str) -> str:
    return _WS.sub(" ", s or "").strip()

def parse_number_cell(text: str) -> dict[str, int | None]:
    nums = [int(m.group(0).replace(",", "")) for m in _NUM.finditer(text or "")]
    out: dict[str, int | None] = {}
    for i, key in enumerate(NUMBER_KEYS):
        out[key] = nums[i] if i < len(nums) else None
    return out
