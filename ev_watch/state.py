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


def diff_remark(old: str, new: str) -> str:
    lines = difflib.unified_diff(
        (old or "").splitlines(), (new or "").splitlines(),
        fromfile="이전", tofile="현재", lineterm="",
    )
    return "\n".join(list(lines)[:40])


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
