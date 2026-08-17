import difflib
import hashlib
import json
import os
from .parse import normalize_text


def _hash_payload(rows: list[dict]) -> list[dict]:
    payload = []
    for r in rows:
        payload.append({
            "차종": normalize_text(r.get("차종", "")),
            "공고파일": sorted(normalize_text(x) for x in r.get("공고파일", [])),
            "접수방법": normalize_text(r.get("접수방법", "")),
            # 공고 차수·기간·마감은 비고 수정 없이 바뀔 수 있어 함께 감시한다.
            # 대수는 15분마다 변해 알림 폭탄이 되므로 넣지 않는다.
            "공고종류": normalize_text(r.get("공고종류", "")),
            "접수기간": normalize_text(r.get("접수기간", "")),
            "신청마감": normalize_text(r.get("신청마감", "")),
            "비고": normalize_text(r.get("비고", "")),
        })
    return payload


def compute_change_hash(rows: list[dict]) -> str:
    canonical = json.dumps(_hash_payload(rows), ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_state(path: str) -> dict | None:
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_state(path: str, state: dict) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def diff_remark_hunks(old: str, new: str) -> list[list[str]]:
    """바뀐 곳만 hunk 단위로 묶어 ➖/➕ 줄 목록을 돌려준다.

    n=0으로 context 줄을 빼고, 사람이 읽을 수 없는 unified diff 헤더(---/+++/@@)도
    걷어낸다. 텔레그램에서 그대로 읽히는 형태가 목적이다.
    """
    hunks: list[list[str]] = []
    for line in difflib.unified_diff(
        (old or "").splitlines(), (new or "").splitlines(), n=0, lineterm="",
    ):
        if line.startswith("---") or line.startswith("+++"):
            continue
        if line.startswith("@@"):
            hunks.append([])
            continue
        if not hunks:                      # 방어: @@ 없이 변경 줄이 먼저 온 경우
            hunks.append([])
        mark = "➖" if line.startswith("-") else "➕"
        hunks[-1].append(f"{mark} {line[1:].strip()}")
    return [h for h in hunks if h]


def diff_remark(old: str, new: str) -> str:
    return "\n".join(line for hunk in diff_remark_hunks(old, new) for line in hunk)


def report_numbers(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        total = (r.get("출고잔여대수") or {}).get("전체")
        out.append({"차종": r.get("차종", ""), "출고잔여대수_전체": total})
    return out


def compute_deltas(today: list[dict], last: list[dict] | None) -> dict[str, int | None]:
    last_map = {r["차종"]: r.get("출고잔여대수_전체") for r in (last or [])}
    deltas: dict[str, int | None] = {}
    for r in today:
        t = r.get("출고잔여대수_전체")
        prev = last_map.get(r["차종"])
        deltas[r["차종"]] = (t - prev) if (t is not None and prev is not None) else None
    return deltas
