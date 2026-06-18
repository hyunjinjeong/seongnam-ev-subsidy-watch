# 성남시 전기차 보조금 공고 변화 알림 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ev.or.kr 지급현황 페이지의 성남시 행을 15분마다 감시해 공고가 바뀌면 텔레그램으로 즉시 알리고, 매일 08:00 KST 현황 보고서를 보낸다.

**Architecture:** Playwright(sync)로 암호화된 페이지를 브라우저에서 렌더링→경기도(4100)→성남시(4113) 조회 후 "성남시" 행만 추출. 순수 로직(파싱·해시·diff·메시지 포맷)은 TDD로 구현하고, 부수효과(스크래핑·텔레그램·CLI 오케스트레이션)는 의존성 주입으로 테스트한다. GitHub Actions가 모드별(`change`/`daily`) 워크플로 2개로 cron 실행하며 상태 JSON을 레포에 커밋한다.

**Tech Stack:** Python 3.12 (uv), Playwright(sync_api) + Chromium, httpx, pytest. 상태는 `state/seongnam.json`(레포 커밋). 알림은 텔레그램 Bot `sendMessage`.

## Global Constraints

- **읽는 행은 오직 "성남시" 행** — `지역구분` 셀 텍스트가 `"성남시"`인 `<tr>`만. 다른 행 절대 금지.
- **변화 감지 해시 = `비고 + 공고파일`만** — 숫자 컬럼(민간공고대수/접수대수/출고대수/출고잔여대수)은 해시에서 제외(매일 변동→오탐).
- **일일 보고서는 숫자 컬럼 포함** — 잔여대수 등 + 전일 대비 증감.
- 경기도 코드 `"4100"`, 성남시 코드 `"4113"`. 대상 URL: `https://ev.or.kr/nportal/buySupprt/initSubsidyPaymentCheckAction.do`.
- 페이지는 `pnp4web` 암호화 → 반드시 실제 브라우저로 렌더. `wait_until="networkidle"` 금지(타임아웃) → `domcontentloaded` + 명시적 `wait_for_*`.
- 모든 표시 시각은 **KST**(`zoneinfo.ZoneInfo("Asia/Seoul")`).
- 비밀값은 코드에 두지 않음 — `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`는 env/Secret.
- 연속 실패 임계값 기본 `3`회. 스크랩 실패 시 상태의 해시/보고서 숫자는 덮어쓰지 않음.
- GitHub Actions cron은 UTC. 일일 보고서 `0 23 * * *` = 08:00 KST(한국 무서머타임으로 영구 고정), YAML에 주석 명시.
- 커밋은 자주, 작은 단위로. TDD(실패 테스트 → 최소 구현 → 통과 → 커밋).

## File Structure

```
seongnam-ev-subsidy-watch/
├── pyproject.toml              # uv 프로젝트, deps: playwright, httpx; dev: pytest
├── .gitignore
├── README.md                   # 셋업/텔레그램/시크릿 안내
├── ev_watch/
│   ├── __init__.py
│   ├── config.py               # 상수(URL, 코드, KST, 경로, 임계값, 컬럼 라벨)
│   ├── parse.py                # 순수: normalize_text, parse_number_cell
│   ├── state.py                # 상태 로드/저장, 변화 해시, diff, 전일대비
│   ├── messages.py             # 순수: keyword_flags, format_change_alert, format_daily_report
│   ├── scraper.py              # Playwright: fetch_seongnam_rows()
│   └── notifier.py             # send_telegram(), get_chat_id()  (httpx, 재시도, DI)
├── check.py                    # CLI 엔트리: --mode change|daily, --dry-run, --get-chat-id, --test-telegram
├── tests/
│   ├── test_parse.py
│   ├── test_state.py
│   ├── test_messages.py
│   ├── test_notifier.py
│   └── test_check.py
├── state/
│   └── .gitkeep
└── .github/workflows/
    ├── check-change.yml        # */15 * * * *  → python check.py --mode change
    └── daily-report.yml        # 0 23 * * *    → python check.py --mode daily
```

**Row 데이터 구조 (scraper가 반환, 전 모듈 공통):**
```python
{
  "시도": "경기",
  "차종": "전기승용",
  "공고파일": ["본공고 1|A", "본공고 2|A02", "본공고 3|A03"],   # "라벨|코드", 변화 해시 대상
  "접수방법": "*일반: 출고등록순 *우선: 출고등록순",
  "민간공고대수": {"전체":1949,"우선순위":0,"법인기관":0,"택시":0,"일반":1949},
  "접수대수":   {"전체":1745,"우선순위":550,"법인기관":49,"택시":60,"일반":1086},
  "출고대수":   {"전체":1740,"우선순위":549,"법인기관":49,"택시":60,"일반":1082},
  "출고잔여대수":{"전체":209,"우선순위":0,"법인기관":0,"택시":0,"일반":867},
  "비고": "★ 성남시 전기자동차(승용, 화물) 보급사업 공고 마감★ ... (정규화된 전체 텍스트)",
}
```

---

### Task 1: 프로젝트 스캐폴딩 + config

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `ev_watch/__init__.py`, `ev_watch/config.py`, `state/.gitkeep`
- Test: `tests/test_parse.py` (이 태스크에선 config import 스모크만)

**Interfaces:**
- Produces: `ev_watch.config` 모듈 상수 — `URL: str`, `GYEONGGI_CODE="4100"`, `SEONGNAM_CODE="4113"`, `KST: ZoneInfo`, `STATE_PATH="state/seongnam.json"`, `CONSECUTIVE_FAILURE_THRESHOLD=3`, `NUMBER_KEYS=["전체","우선순위","법인기관","택시","일반"]`

- [ ] **Step 1: pyproject.toml 작성**

```toml
[project]
name = "seongnam-ev-subsidy-watch"
version = "0.1.0"
description = "성남시 전기차 보조금 공고 변화 알림"
requires-python = ">=3.11"
dependencies = [
    "playwright>=1.40",
    "httpx>=0.27",
]

[dependency-groups]
dev = ["pytest>=8"]

[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
```

- [ ] **Step 2: .gitignore 작성**

```gitignore
__pycache__/
*.pyc
.venv/
.env
.pytest_cache/
artifacts/
```

- [ ] **Step 3: 패키지/디렉터리 생성**

```bash
mkdir -p ev_watch tests state .github/workflows
touch ev_watch/__init__.py state/.gitkeep
```

- [ ] **Step 4: config.py 작성**

```python
# ev_watch/config.py
from zoneinfo import ZoneInfo

URL = "https://ev.or.kr/nportal/buySupprt/initSubsidyPaymentCheckAction.do"
GYEONGGI_CODE = "4100"   # 경기도
SEONGNAM_CODE = "4113"   # 성남시
KST = ZoneInfo("Asia/Seoul")
STATE_PATH = "state/seongnam.json"
CONSECUTIVE_FAILURE_THRESHOLD = 3
# 숫자 셀 분해 순서 (표 헤더 기준): 전체 / (우선순위) / (법인·기관) / (택시) / (일반)
NUMBER_KEYS = ["전체", "우선순위", "법인기관", "택시", "일반"]
```

- [ ] **Step 5: config 스모크 테스트 작성**

```python
# tests/test_parse.py
from ev_watch import config

def test_config_constants():
    assert config.SEONGNAM_CODE == "4113"
    assert config.GYEONGGI_CODE == "4100"
    assert config.NUMBER_KEYS[0] == "전체"
    assert config.STATE_PATH.endswith("seongnam.json")
```

- [ ] **Step 6: 의존성 설치 + 테스트 통과 확인**

Run: `uv sync && uv run pytest tests/test_parse.py -v`
Expected: PASS (1 passed)

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml .gitignore ev_watch state tests uv.lock
git commit -m "chore: 프로젝트 스캐폴딩 + config 상수"
```

---

### Task 2: 셀 파싱 (`parse.py`)

**Files:**
- Create: `ev_watch/parse.py`
- Test: `tests/test_parse.py` (append)

**Interfaces:**
- Consumes: `ev_watch.config.NUMBER_KEYS`
- Produces:
  - `normalize_text(s: str) -> str` — 모든 연속 공백(개행 포함)을 단일 스페이스로 축약 후 trim.
  - `parse_number_cell(text: str) -> dict[str, int | None]` — `"1949 (0)(0)(0)(1949)"` → `{"전체":1949,"우선순위":0,"법인기관":0,"택시":0,"일반":1949}`. 숫자가 5개 미만이면 부족분은 `None`.

- [ ] **Step 1: 실패 테스트 작성**

```python
# tests/test_parse.py (이어서 추가)
from ev_watch.parse import normalize_text, parse_number_cell

def test_normalize_text_collapses_whitespace():
    assert normalize_text("  a\n\n b   c \t") == "a b c"

def test_parse_number_cell_basic():
    assert parse_number_cell("1949 (0)(0)(0)(1949)") == {
        "전체": 1949, "우선순위": 0, "법인기관": 0, "택시": 0, "일반": 1949,
    }

def test_parse_number_cell_with_commas_and_spaces():
    assert parse_number_cell("2,092 (550) (49) (60) (1,086)") == {
        "전체": 2092, "우선순위": 550, "법인기관": 49, "택시": 60, "일반": 1086,
    }

def test_parse_number_cell_missing_values_are_none():
    assert parse_number_cell("209") == {
        "전체": 209, "우선순위": None, "법인기관": None, "택시": None, "일반": None,
    }
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_parse.py -v`
Expected: FAIL (ImportError: cannot import name 'normalize_text')

- [ ] **Step 3: 최소 구현**

```python
# ev_watch/parse.py
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
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_parse.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add ev_watch/parse.py tests/test_parse.py
git commit -m "feat: 텍스트 정규화 + 숫자 셀 파싱"
```

---

### Task 3: 상태 관리 (`state.py`)

**Files:**
- Create: `ev_watch/state.py`
- Test: `tests/test_state.py`

**Interfaces:**
- Consumes: `parse.normalize_text`
- Produces:
  - `compute_change_hash(rows: list[dict]) -> str` — 각 행의 `{차종, 공고파일(정렬), 접수방법, 비고}`만 추려 canonical JSON(정규화) → sha256 hex.
  - `load_state(path: str) -> dict | None` — 파일 없으면 `None`.
  - `save_state(path: str, state: dict) -> None` — 디렉터리 보장, UTF-8, `ensure_ascii=False`, 들여쓰기 2.
  - `diff_remark(old: str, new: str) -> str` — 두 비고 텍스트의 unified diff 문자열(최대 40줄).
  - `report_numbers(rows: list[dict]) -> list[dict]` — 보고서/전일대비 저장용 `[{"차종":..,"출고잔여대수_전체": int|None}]`.
  - `compute_deltas(today: list[dict], last: list[dict] | None) -> dict[str, int | None]` — 차종별 `출고잔여대수_전체` 증감(전일 없거나 매칭 안 되면 `None`).

- [ ] **Step 1: 실패 테스트 작성**

```python
# tests/test_state.py
import json
from ev_watch import state

def _row(비고="공고 마감", 공고파일=None, 차종="전기승용", 잔여=209):
    return {
        "차종": 차종,
        "공고파일": 공고파일 if 공고파일 is not None else ["본공고 1|A", "본공고 2|A02"],
        "접수방법": "*일반: 출고등록순",
        "비고": 비고,
        "출고잔여대수": {"전체": 잔여},
    }

def test_hash_ignores_numbers_and_whitespace():
    a = _row(잔여=209)
    b = _row(잔여=5)            # 숫자만 다름
    b["접수대수"] = {"전체": 1}  # 숫자 컬럼 추가돼도
    assert state.compute_change_hash([a]) == state.compute_change_hash([b])

def test_hash_changes_when_remark_changes():
    a = _row(비고="공고 마감")
    b = _row(비고="추경 공고 접수 시작")
    assert state.compute_change_hash([a]) != state.compute_change_hash([b])

def test_hash_changes_when_files_change():
    a = _row(공고파일=["본공고 1|A"])
    b = _row(공고파일=["본공고 1|A", "추경공고|B"])
    assert state.compute_change_hash([a]) != state.compute_change_hash([b])

def test_hash_order_independent_for_files():
    a = _row(공고파일=["본공고 1|A", "본공고 2|A02"])
    b = _row(공고파일=["본공고 2|A02", "본공고 1|A"])
    assert state.compute_change_hash([a]) == state.compute_change_hash([b])

def test_load_missing_returns_none(tmp_path):
    assert state.load_state(str(tmp_path / "none.json")) is None

def test_save_then_load_roundtrip(tmp_path):
    p = str(tmp_path / "s.json")
    state.save_state(p, {"hash": "abc", "비고": "추경"})
    assert state.load_state(p) == {"hash": "abc", "비고": "추경"}

def test_diff_remark_shows_change():
    d = state.diff_remark("공고 마감", "추경 공고 접수 시작")
    assert "공고 마감" in d and "추경 공고 접수 시작" in d

def test_report_numbers_extracts_total():
    rows = [_row(차종="전기승용", 잔여=209)]
    assert state.report_numbers(rows) == [{"차종": "전기승용", "출고잔여대수_전체": 209}]

def test_compute_deltas_matches_by_차종():
    today = [{"차종": "전기승용", "출고잔여대수_전체": 200}]
    last = [{"차종": "전기승용", "출고잔여대수_전체": 209}]
    assert state.compute_deltas(today, last) == {"전기승용": -9}

def test_compute_deltas_none_when_no_last():
    today = [{"차종": "전기승용", "출고잔여대수_전체": 200}]
    assert state.compute_deltas(today, None) == {"전기승용": None}
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_state.py -v`
Expected: FAIL (ModuleNotFoundError / AttributeError)

- [ ] **Step 3: 최소 구현**

```python
# ev_watch/state.py
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
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_state.py -v`
Expected: PASS (10 passed)

- [ ] **Step 5: Commit**

```bash
git add ev_watch/state.py tests/test_state.py
git commit -m "feat: 상태 저장/로드 + 변화 해시(비고·공고파일) + 전일대비"
```

---

### Task 4: 메시지 포맷 (`messages.py`)

**Files:**
- Create: `ev_watch/messages.py`
- Test: `tests/test_messages.py`

**Interfaces:**
- Consumes: `state.diff_remark`, `state.compute_deltas`
- Produces:
  - `keyword_flags(rows: list[dict]) -> dict[str, bool]` — 모든 행 `비고` 합쳐 `추경/접수/공고/마감` 포함 여부.
  - `format_change_alert(old_rows: list[dict], new_rows: list[dict], url: str) -> str` — 제목 + 키워드 플래그 + 비고 diff + 공고파일 코드 집합 변화 + 링크.
  - `format_daily_report(rows: list[dict], deltas: dict[str,int|None], now_str: str, url: str) -> str` — 제목(날짜) + 행별 잔여(+전일대비)/접수/출고/공고/공고파일/비고 첫 줄 + 링크.
  - `format_startup(rows: list[dict], url: str) -> str` — 첫 실행용 "감시 시작" 메시지.

- [ ] **Step 1: 실패 테스트 작성**

```python
# tests/test_messages.py
from ev_watch import messages

def _row(비고, 공고파일, 차종="전기승용"):
    return {
        "차종": 차종, "공고파일": 공고파일, "접수방법": "*일반",
        "비고": 비고,
        "민간공고대수": {"전체": 1949}, "접수대수": {"전체": 1745},
        "출고대수": {"전체": 1740}, "출고잔여대수": {"전체": 209, "일반": 867},
    }

def test_keyword_flags():
    rows = [_row("추경예산 확보 후 공고 및 접수 예정", ["본공고 1|A"])]
    f = messages.keyword_flags(rows)
    assert f == {"추경": True, "접수": True, "공고": True, "마감": False}

def test_change_alert_contains_diff_and_file_change_and_link():
    old = [_row("공고 마감", ["본공고 1|A"])]
    new = [_row("추경 접수 시작", ["본공고 1|A", "추경공고|B"])]
    msg = messages.format_change_alert(old, new, "http://x")
    assert "변화 감지" in msg
    assert "추경 접수 시작" in msg      # diff에 신규 텍스트
    assert "B" in msg                    # 신규 공고파일 코드
    assert "http://x" in msg

def test_daily_report_shows_remaining_delta_and_date():
    rows = [_row("공고 마감", ["본공고 1|A"])]
    msg = messages.format_daily_report(rows, {"전기승용": -3}, "2026-06-18 08:00", "http://x")
    assert "일일 현황" in msg
    assert "2026-06-18" in msg
    assert "209" in msg                  # 잔여 전체
    assert "-3" in msg                   # 전일 대비
    assert "http://x" in msg

def test_daily_report_handles_none_delta():
    rows = [_row("공고 마감", ["본공고 1|A"])]
    msg = messages.format_daily_report(rows, {"전기승용": None}, "2026-06-18 08:00", "http://x")
    assert "209" in msg   # delta 없어도 현황은 나온다

def test_startup_message():
    rows = [_row("공고 마감", ["본공고 1|A"])]
    msg = messages.format_startup(rows, "http://x")
    assert "감시 시작" in msg and "http://x" in msg
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_messages.py -v`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: 최소 구현**

```python
# ev_watch/messages.py
from .state import diff_remark

_KEYWORDS = ["추경", "접수", "공고", "마감"]

def keyword_flags(rows: list[dict]) -> dict[str, bool]:
    text = " ".join(r.get("비고", "") for r in rows)
    return {k: (k in text) for k in _KEYWORDS}

def _codes(rows: list[dict]) -> set[str]:
    return {f for r in rows for f in r.get("공고파일", [])}

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
        parts.append(f"➕ 공고파일 추가: {', '.join(added)}")
    if removed:
        parts.append(f"➖ 공고파일 삭제: {', '.join(removed)}")
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
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_messages.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add ev_watch/messages.py tests/test_messages.py
git commit -m "feat: 텔레그램 메시지 포맷(변화 알림/일일 보고서/시작)"
```

---

### Task 5: 텔레그램 전송 (`notifier.py`)

**Files:**
- Create: `ev_watch/notifier.py`
- Test: `tests/test_notifier.py`

**Interfaces:**
- Produces:
  - `send_telegram(token: str, chat_id: str, text: str, *, post=None, sleep=None, max_retries: int = 3) -> bool` — `sendMessage` POST(`parse_mode="Markdown"`, `disable_web_page_preview=True`). 실패 시 지수 백오프 재시도. 성공 `True` / 최종 실패 `False`. `post`/`sleep` 주입으로 테스트.
  - `get_chat_id(token: str, *, get=None) -> str | None` — `getUpdates`에서 마지막 `message.chat.id` 문자열 반환.

- [ ] **Step 1: 실패 테스트 작성**

```python
# tests/test_notifier.py
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
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_notifier.py -v`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: 최소 구현**

```python
# ev_watch/notifier.py
import time
import httpx

_API = "https://api.telegram.org/bot{token}/{method}"

def send_telegram(token, chat_id, text, *, post=None, sleep=None, max_retries=3):
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
            sleep(2 ** attempt)  # 1s, 2s, ...
    return False

def get_chat_id(token, *, get=None):
    get = get or httpx.get
    url = _API.format(token=token, method="getUpdates")
    resp = get(url, timeout=20)
    results = resp.json().get("result", [])
    for upd in reversed(results):
        chat = (upd.get("message") or {}).get("chat") or {}
        if "id" in chat:
            return str(chat["id"])
    return None
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_notifier.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add ev_watch/notifier.py tests/test_notifier.py
git commit -m "feat: 텔레그램 전송(재시도) + chat_id 조회"
```

---

### Task 6: 스크래퍼 (`scraper.py`)

**Files:**
- Create: `ev_watch/scraper.py`
- Test: 라이브 스모크(아래 Step 5). 순수 변환 부분만 단위 테스트(`tests/test_parse.py`에 추가).

**Interfaces:**
- Consumes: `config.URL/GYEONGGI_CODE/SEONGNAM_CODE`, `parse.normalize_text/parse_number_cell`
- Produces:
  - `_rows_from_raw(raw: list[dict]) -> list[dict]` — 브라우저에서 뽑은 raw(문자열 셀)을 최종 Row 구조로 변환(숫자 파싱). **순수 함수, 단위 테스트 대상.**
  - `fetch_seongnam_rows(*, headless: bool = True) -> list[dict]` — Playwright로 조회 후 성남시 행 리스트 반환. 행을 못 찾으면 `RuntimeError`. 디버그용으로 실패 시 `artifacts/`에 스크린샷·HTML 저장.

- [ ] **Step 1: 순수 변환 함수 실패 테스트 작성**

```python
# tests/test_parse.py (이어서 추가)
from ev_watch.scraper import _rows_from_raw

def test_rows_from_raw_parses_numbers_and_keeps_text():
    raw = [{
        "시도": "경기", "차종": "전기승용",
        "공고파일": ["본공고 1|A", "본공고 2|A02"],
        "접수방법": "*일반: 출고등록순",
        "민간공고대수_raw": "1949 (0)(0)(0)(1949)",
        "접수대수_raw": "1745 (550)(49)(60)(1086)",
        "출고대수_raw": "1740 (549)(49)(60)(1082)",
        "출고잔여대수_raw": "209 (0)(0)(0)(867)",
        "비고": "  ★ 성남시 ... 공고 마감 ",
    }]
    rows = _rows_from_raw(raw)
    assert len(rows) == 1
    r = rows[0]
    assert r["차종"] == "전기승용"
    assert r["공고파일"] == ["본공고 1|A", "본공고 2|A02"]
    assert r["민간공고대수"]["전체"] == 1949
    assert r["출고잔여대수"]["일반"] == 867
    assert r["비고"] == "★ 성남시 ... 공고 마감"   # 정규화됨
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_parse.py -v`
Expected: FAIL (cannot import name '_rows_from_raw')

- [ ] **Step 3: scraper.py 구현**

> 추출 JS는 스파이크로 검증된 구조에 기반: `지역구분` 셀이 `"성남시"`인 `<tr>`만, 셀 인덱스 0..9 매핑, 공고파일은 `goDownloadFile('연도','지역','코드')`의 **코드(3번째 인자)** 와 라벨을 `"라벨|코드"`로.

```python
# ev_watch/scraper.py
import os
from .config import URL, GYEONGGI_CODE, SEONGNAM_CODE
from .parse import normalize_text, parse_number_cell

_EXTRACT_JS = r"""() => {
  const rows = [];
  document.querySelectorAll('tr').forEach(tr => {
    const cells = Array.from(tr.querySelectorAll('td,th'));
    const t = cells.map(c => (c.textContent || '').replace(/\s+/g, ' ').trim());
    if (t.length < 10 || t[1] !== '성남시') return;   // 지역구분 셀이 정확히 '성남시'
    const files = Array.from(cells[3].querySelectorAll('a,button')).map(b => {
      const m = (b.getAttribute('onclick') || '').match(/goDownloadFile\([^)]*'([^']*)'\s*\)/);
      const code = m ? m[1] : '';
      return (b.textContent || '').trim() + '|' + code;
    });
    rows.push({
      "시도": t[0], "차종": t[2], "공고파일": files, "접수방법": t[4],
      "민간공고대수_raw": t[5], "접수대수_raw": t[6],
      "출고대수_raw": t[7], "출고잔여대수_raw": t[8], "비고": t[9],
    });
  });
  return rows;
}"""

def _rows_from_raw(raw: list[dict]) -> list[dict]:
    out = []
    for r in raw:
        out.append({
            "시도": normalize_text(r.get("시도", "")),
            "차종": normalize_text(r.get("차종", "")),
            "공고파일": [normalize_text(x) for x in r.get("공고파일", [])],
            "접수방법": normalize_text(r.get("접수방법", "")),
            "민간공고대수": parse_number_cell(r.get("민간공고대수_raw", "")),
            "접수대수": parse_number_cell(r.get("접수대수_raw", "")),
            "출고대수": parse_number_cell(r.get("출고대수_raw", "")),
            "출고잔여대수": parse_number_cell(r.get("출고잔여대수_raw", "")),
            "비고": normalize_text(r.get("비고", "")),
        })
    return out

def fetch_seongnam_rows(*, headless: bool = True) -> list[dict]:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        ctx = browser.new_context(locale="ko-KR")
        page = ctx.new_page()
        try:
            page.goto(URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_selector("#localDo_cd", timeout=30000)
            page.select_option("#localDo_cd", GYEONGGI_CODE)
            # 시군구 옵션이 채워질 때까지 대기
            page.wait_for_selector(f"#local_cd1 option[value='{SEONGNAM_CODE}']", timeout=30000)
            page.select_option("#local_cd1", SEONGNAM_CODE)
            page.click("button:has-text('조회')", timeout=10000)
            # 결과 표에 '성남시' 행이 나타날 때까지 대기
            page.wait_for_function(
                "() => Array.from(document.querySelectorAll('tr td,tr th'))"
                ".some(c => c.textContent.trim() === '성남시')",
                timeout=30000,
            )
            raw = page.evaluate(_EXTRACT_JS)
            rows = _rows_from_raw(raw)
            if not rows:
                raise RuntimeError("성남시 행을 찾지 못함")
            return rows
        except Exception:
            os.makedirs("artifacts", exist_ok=True)
            try:
                page.screenshot(path="artifacts/fail.png", full_page=True)
                with open("artifacts/fail.html", "w", encoding="utf-8") as f:
                    f.write(page.content())
            except Exception:
                pass
            raise
        finally:
            browser.close()
```

- [ ] **Step 4: 단위 테스트 통과 확인**

Run: `uv run pytest tests/test_parse.py -v`
Expected: PASS (`test_rows_from_raw_parses_numbers_and_keeps_text` 포함 전부 통과)

- [ ] **Step 5: 라이브 스모크 (실제 사이트)**

Run:
```bash
uv run playwright install chromium
uv run python -c "from ev_watch.scraper import fetch_seongnam_rows; import json; print(json.dumps(fetch_seongnam_rows(), ensure_ascii=False, indent=2))"
```
Expected: 성남시 행 1개(이상) JSON 출력. `비고`에 "성남시 ... 공고" 텍스트, `출고잔여대수.전체`가 정수. 실패하면 `artifacts/fail.png`로 원인 확인(헤드리스 차단 의심 시 `headless=False`로 재시도).

- [ ] **Step 6: Commit**

```bash
git add ev_watch/scraper.py tests/test_parse.py
git commit -m "feat: Playwright 스크래퍼(성남시 행만 추출) + 순수 변환 함수"
```

---

### Task 7: CLI 오케스트레이터 (`check.py`)

**Files:**
- Create: `check.py`
- Test: `tests/test_check.py`

**Interfaces:**
- Consumes: `config`, `state`, `messages`, `scraper.fetch_seongnam_rows`, `notifier.send_telegram/get_chat_id`
- Produces (테스트 대상 — 의존성 주입):
  - `do_change(fetch, send, *, state_path, url, now_iso) -> str` — 결과 코드 문자열 반환(`"first"|"changed"|"nochange"|"fail"`). 동작: fetch 성공 시 해시 비교(첫 실행은 시작 메시지+베이스라인, 변화 시 알림, 동일 시 무동작), 실패 시 연속실패 카운트+임계 도달 시 알림. 해시/숫자는 실패 시 미변경.
  - `do_daily(fetch, send, *, state_path, url, now_str) -> str` — `"ok"|"fail"`. 성공 시 전일대비 포함 보고서 전송 + `last_report` 갱신. 실패 시 카운트+임계 알림.
  - `main(argv=None) -> int` — argparse: `--mode {change,daily}`, `--dry-run`, `--get-chat-id`, `--test-telegram`. env에서 토큰/챗ID 로드.

- [ ] **Step 1: 실패 테스트 작성**

```python
# tests/test_check.py
import json
import importlib.util, pathlib

# check.py는 레포 루트에 있으므로 경로로 로드
_spec = importlib.util.spec_from_file_location(
    "check", str(pathlib.Path(__file__).resolve().parent.parent / "check.py"))
check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check)

def _row(비고="공고 마감", 공고파일=None, 잔여=209):
    return {
        "차종": "전기승용",
        "공고파일": 공고파일 if 공고파일 is not None else ["본공고 1|A"],
        "접수방법": "*일반", "비고": 비고,
        "민간공고대수": {"전체": 1949}, "접수대수": {"전체": 1745},
        "출고대수": {"전체": 1740}, "출고잔여대수": {"전체": 잔여, "일반": 867},
    }

def _sender():
    sent = []
    def send(text): sent.append(text); return True
    return send, sent

def test_do_change_first_run_sends_startup_and_saves(tmp_path):
    sp = str(tmp_path / "s.json")
    send, sent = _sender()
    code = check.do_change(lambda: [_row()], send, state_path=sp, url="u", now_iso="2026-06-18T08:00:00+09:00")
    assert code == "first"
    assert "감시 시작" in sent[0]
    assert json.load(open(sp, encoding="utf-8"))["hash"]

def test_do_change_no_change_is_silent(tmp_path):
    sp = str(tmp_path / "s.json")
    send, sent = _sender()
    check.do_change(lambda: [_row()], send, state_path=sp, url="u", now_iso="t")  # baseline
    code = check.do_change(lambda: [_row(잔여=5)], send, state_path=sp, url="u", now_iso="t")  # 숫자만 변동
    assert code == "nochange"
    assert len(sent) == 1   # 시작 메시지 1개뿐, 추가 알림 없음

def test_do_change_detects_remark_change(tmp_path):
    sp = str(tmp_path / "s.json")
    send, sent = _sender()
    check.do_change(lambda: [_row("공고 마감")], send, state_path=sp, url="u", now_iso="t")
    code = check.do_change(lambda: [_row("추경 공고 접수 시작")], send, state_path=sp, url="u", now_iso="t")
    assert code == "changed"
    assert "변화 감지" in sent[-1]

def test_do_change_failure_increments_and_alerts_at_threshold(tmp_path):
    sp = str(tmp_path / "s.json")
    send, sent = _sender()
    def boom(): raise RuntimeError("blocked")
    for _ in range(3):
        code = check.do_change(boom, send, state_path=sp, url="u", now_iso="t")
    assert code == "fail"
    assert any("체크 실패" in m for m in sent)            # 3회째 알림
    st = json.load(open(sp, encoding="utf-8"))
    assert st["consecutive_failures"] == 3
    assert "hash" not in st or st.get("hash") is None      # 실패는 해시 미설정

def test_do_daily_sends_report_with_delta(tmp_path):
    sp = str(tmp_path / "s.json")
    # 전일 last_report를 미리 저장
    check.state.save_state(sp, {"last_report": [{"차종": "전기승용", "출고잔여대수_전체": 212}]})
    send, sent = _sender()
    code = check.do_daily(lambda: [_row(잔여=209)], send, state_path=sp, url="u", now_str="2026-06-18 08:00")
    assert code == "ok"
    assert "일일 현황" in sent[0]
    assert "-3" in sent[0]   # 212 -> 209
    assert json.load(open(sp, encoding="utf-8"))["last_report"][0]["출고잔여대수_전체"] == 209
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_check.py -v`
Expected: FAIL (AttributeError: module 'check' has no attribute 'do_change')

- [ ] **Step 3: check.py 구현**

```python
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
        state.save_state(state_path, base)   # 실패카운트 리셋·시간 갱신
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
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_check.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: 전체 테스트 + dry-run 스모크**

Run:
```bash
uv run pytest -v
uv run python check.py --mode change --dry-run    # 실제 스크랩 후 전송 대신 출력
```
Expected: 전 테스트 PASS. dry-run은 성남시 현황을 출력하고 "[DRY-RUN 전송]"로 시작 메시지/변화 메시지를 콘솔에 표시(또는 nochange 시 표시 없음).

- [ ] **Step 6: Commit**

```bash
git add check.py tests/test_check.py
git commit -m "feat: CLI 오케스트레이터(change/daily/dry-run/get-chat-id/test-telegram)"
```

---

### Task 8: GitHub Actions 워크플로 + README

**Files:**
- Create: `.github/workflows/check-change.yml`, `.github/workflows/daily-report.yml`, `README.md`

**Interfaces:**
- Consumes: `check.py` CLI, Secret `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID`

- [ ] **Step 1: check-change.yml 작성**

```yaml
# .github/workflows/check-change.yml
name: check-change
on:
  schedule:
    - cron: '*/15 * * * *'   # 15분마다 (타임존 무관)
  workflow_dispatch:
permissions:
  contents: write
concurrency:
  group: ev-watch-state      # 상태 커밋 충돌 방지(보고서와 공유)
jobs:
  run:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv sync
      - run: uv run playwright install --with-deps chromium
      - run: uv run python check.py --mode change
        env:
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
      - name: Commit state if changed
        if: always()
        run: |
          if ! git diff --quiet -- state/; then
            git config user.name "ev-watch-bot"
            git config user.email "actions@users.noreply.github.com"
            git add state/
            git commit -m "chore: update state [skip ci]"
            git push
          fi
      - uses: actions/upload-artifact@v4
        if: failure()
        with:
          name: debug-artifacts
          path: artifacts/
          if-no-files-found: ignore
```

- [ ] **Step 2: daily-report.yml 작성**

```yaml
# .github/workflows/daily-report.yml
name: daily-report
on:
  schedule:
    - cron: '0 23 * * *'     # 23:00 UTC = 08:00 KST (한국 무서머타임 → 영구 고정)
  workflow_dispatch:
permissions:
  contents: write
concurrency:
  group: ev-watch-state
jobs:
  run:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv sync
      - run: uv run playwright install --with-deps chromium
      - run: uv run python check.py --mode daily
        env:
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
      - name: Commit state if changed
        if: always()
        run: |
          if ! git diff --quiet -- state/; then
            git config user.name "ev-watch-bot"
            git config user.email "actions@users.noreply.github.com"
            git add state/
            git commit -m "chore: update last_report [skip ci]"
            git push
          fi
      - uses: actions/upload-artifact@v4
        if: failure()
        with:
          name: debug-artifacts
          path: artifacts/
          if-no-files-found: ignore
```

- [ ] **Step 3: YAML 유효성 확인**

Run: `uv run python -c "import yaml,glob; [yaml.safe_load(open(f)) for f in glob.glob('.github/workflows/*.yml')]; print('yaml ok')"`
Expected: `yaml ok` (PyYAML 없으면 `uv run --with pyyaml python -c ...`)

- [ ] **Step 4: README.md 작성 (텔레그램 셋업 가이드 포함)**

````markdown
# seongnam-ev-subsidy-watch

성남시 전기차 보조금 공고를 감시해 텔레그램으로 알림. (변화 감지 15분 / 일일 보고서 08:00 KST)

## 텔레그램 셋업 (처음 쓰는 경우)

1. 텔레그램 앱 설치·가입.
2. `@BotFather` → `/newbot` → 봇 이름·username 입력 → **봇 토큰** 발급.
3. 발급된 `t.me/<봇>` 링크 열어 **`/start`** 한 번 누르기.
4. chat_id 확인:
   ```bash
   TELEGRAM_BOT_TOKEN=<토큰> uv run python check.py --get-chat-id
   ```
5. 테스트 전송(휴대폰 수신 확인):
   ```bash
   TELEGRAM_BOT_TOKEN=<토큰> TELEGRAM_CHAT_ID=<챗ID> uv run python check.py --test-telegram
   ```
6. GitHub 레포 `Settings → Secrets and variables → Actions`에 `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` 등록.

## 로컬 실행

```bash
uv sync
uv run playwright install chromium
uv run python check.py --mode change --dry-run   # 전송 없이 현황 출력
```

## 동작

- `check-change.yml`: 15분마다 성남시 `비고+공고파일` 변화 시 알림.
- `daily-report.yml`: 매일 08:00 KST 현황(잔여대수+전일대비) 보고서. `workflow_dispatch`로 즉시 실행해 검증 가능.
- 상태는 `state/seongnam.json`에 커밋되어 유지.
````

- [ ] **Step 5: Commit**

```bash
git add .github README.md
git commit -m "ci: 워크플로(변화감지/일일보고서) + README 셋업 가이드"
```

---

### Task 9: 배포 + 수동 dispatch 검증

**Files:** 없음(운영 작업). 사용자와 함께 진행.

- [ ] **Step 1: GitHub에 public 레포 생성 + 푸시**

```bash
gh repo create seongnam-ev-subsidy-watch --public --source=. --remote=origin --push
```
(또는 사용자가 직접 생성 후 `git remote add origin ... && git push -u origin main`)

- [ ] **Step 2: Secret 등록 확인**

`Settings → Secrets and variables → Actions`에 `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` 존재 확인. (`gh secret set TELEGRAM_BOT_TOKEN` 사용 가능)

- [ ] **Step 3: 일일 보고서 수동 dispatch → 수신 확인 (R1 검증 겸함)**

```bash
gh workflow run daily-report.yml
gh run watch
```
Expected: 워크플로 성공 + 휴대폰에 "📋 성남시 전기차 보조금 일일 현황" 수신. 실패 시 Actions 로그/`debug-artifacts`로 원인 확인.
- **R1(미국 IP 차단) 현실화 시**: 워크플로가 성남시 행을 못 찾고 실패 → 폴백으로 맥 launchd 실행 전환(같은 `check.py`, `--mode change`/`daily`를 `cron`/`launchd`로). 본 플랜의 코드 변경 없음.

- [ ] **Step 4: 변화 감지 수동 dispatch → 베이스라인 생성 확인**

```bash
gh workflow run check-change.yml
gh run watch
```
Expected: 첫 실행이면 "✅ 감시 시작" 수신 + `state/seongnam.json` 커밋됨. 이후 15분 cron 자동 동작.

- [ ] **Step 5: 최종 확인**

- Actions 탭에서 두 워크플로가 스케줄 등록됐는지 확인.
- `state/seongnam.json`이 레포에 커밋돼 있는지 확인.

---

## Self-Review

**1. Spec coverage** (스펙 각 절 → 태스크 매핑):
- 2절 암호화 제약/접근 A → Task 6(Playwright, networkidle 금지, 헤드리스 폴백). ✅
- 3절 추출 규칙(성남시 행만, 비고+공고파일, 숫자 제외) → Task 6 `_EXTRACT_JS`(`t[1]==='성남시'`), Task 3 해시(숫자 제외). ✅
- 4절 컴포넌트 분리 → Task 1~7 모듈 매핑. ✅
- 5절 데이터 흐름(change/daily, 첫 실행) → Task 7 `do_change`/`do_daily`. ✅
- 6절 메시지 형식(변화/일일/KST) → Task 4 + Task 7 `now` KST. ✅
- 7절 상태 스키마(hash/rows/숫자/last_report/failures) → Task 3 + Task 7 저장 구조. ✅
- 8절 사일런트 실패(상태 보존, N회 알림, 아티팩트) → Task 7 `_save_failure`, Task 6 artifacts, Task 8 upload-artifact. ✅
- 9절 실행 환경(워크플로 2개, cron UTC=KST 주석, state 커밋, public) → Task 8. ✅
- 10절 R1/R2/R3 → Task 9 Step3(R1), Task 6 Step5(R2 headless), Task 6 artifacts(R3). ✅
- 11절 설정/시크릿 → Task 1 config, Task 8 env/secret. ✅
- 12절 테스트(순수 TDD + dry-run 스모크 + dispatch 검증) → Task 2~7 단위, Task 7 Step5, Task 9. ✅
- 14절 텔레그램 가이드(--get-chat-id/--test-telegram) → Task 7 main, Task 8 README. ✅

**2. Placeholder scan:** 모든 코드 스텝에 실제 코드 포함. "TBD/TODO/적절히 처리" 없음. ✅

**3. Type consistency:** Row 키(차종/공고파일/비고/출고잔여대수…)와 함수 시그니처(`compute_change_hash`, `report_numbers`, `compute_deltas`, `format_*`, `send_telegram`, `do_change/do_daily`)가 태스크 간 일치. 보고서 저장 키 `출고잔여대수_전체`가 `report_numbers`·`compute_deltas`·테스트에서 동일. ✅
