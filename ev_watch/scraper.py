import os
import time
from .config import URL, GYEONGGI_CODE, SEONGNAM_CODE, SEONGNAM_NAME, NUMBER_KEYS
from .parse import normalize_text, normalize_multiline, parse_int

# 상세 모달의 '상세 대수 정보'(#myGrid3) 컬럼 → 기존 Row 키 매핑
_COUNT_COLUMNS = {
    "민간공고대수": "tcnt",
    "접수대수": "recei",
    "선정대수": "choice",
    "출고대수": "relea",
    "선정잔여대수": "choiceRemain",
    "출고잔여대수": "resi",
}
# 페이지 표기('법인·기관')를 기존 상태 파일 키('법인기관')로 맞춘다
_CATEGORY_ALIASES = {"법인·기관": "법인기관", "법인/기관": "법인기관"}

# 결과 그리드(#myGrid)에서 성남시 행들의 row-id와 셀 값을 읽는다.
# 결과가 AG Grid(div 기반)로 바뀌어 tr/td 대신 col-id 속성으로 셀을 찾는다.
_GRID_ROWS_JS = r"""(sigungu) => {
  const cell = (row, id) => {
    const c = row.querySelector(`.ag-cell[col-id="${id}"]`);
    return c ? (c.textContent || '').replace(/\s+/g, ' ').trim() : '';
  };
  const seen = new Set();
  return Array.from(document.querySelectorAll('#myGrid .ag-row'))
    // pinned 컬럼이 켜지면 같은 row-id가 여러 컨테이너에 중복 렌더링된다
    .filter(row => {
      const id = row.getAttribute('row-id');
      if (seen.has(id)) return false;
      seen.add(id);
      return true;
    })
    .map(row => {
      // 지역 셀은 <button>즐겨찾기</button><div><span>시도</span><span>시군구</span></div> 구조
      const spans = Array.from(row.querySelectorAll('.ag-cell[col-id="sido"] span'))
        .map(s => (s.textContent || '').trim())
        .filter(t => t && t !== '즐겨찾기');
      return {
        "시도": spans[0] || '', "시군구": spans[1] || '',
        "차종": cell(row, 'carNm'), "공고종류": cell(row, 'noticeKind'),
        "접수기간": cell(row, 'period'), "신청마감": cell(row, 'deadline'),
        "_rowId": row.getAttribute('row-id'),
      };
    })
    .filter(r => r["시군구"] === sigungu);
}"""

# 상세 모달(#modalArticleDetail)에서 비고·접수방법·공고파일·구분별 대수를 읽는다.
_DETAIL_JS = r"""() => {
  const text = sel => {
    const e = document.querySelector(sel);
    return e ? e.textContent : '';
  };
  const files = Array.from(
    document.querySelectorAll('#myGrid2 .ag-cell[col-id="files"] button[title]')
  ).map(b => b.getAttribute('title').replace(/\s*공고문\s*다운로드\s*$/, '').trim());
  const counts = Array.from(document.querySelectorAll('#myGrid3 .ag-row')).map(row => {
    const o = {};
    row.querySelectorAll('.ag-cell[col-id]').forEach(c => {
      o[c.getAttribute('col-id')] = (c.textContent || '').replace(/\s+/g, ' ').trim();
    });
    o["구분"] = o["category"] || '';
    return o;
  });
  return {"비고": text('#detailEtc'), "접수방법": text('#detailContact'),
          "공고파일": files, "대수": counts};
}"""


def _counts_by_category(rows: list[dict], col: str) -> dict[str, int | None]:
    """구분별 행 목록에서 한 컬럼을 뽑아 {구분: 값} 딕셔너리로 만든다."""
    found = {}
    for r in rows:
        name = normalize_text(r.get("구분", ""))
        found[_CATEGORY_ALIASES.get(name, name)] = parse_int(r.get(col))
    return {key: found.get(key) for key in NUMBER_KEYS}


def _row_from_raw(grid: dict, detail: dict) -> dict:
    """브라우저에서 추출한 그리드 행 + 상세 모달 데이터를 Row 구조로 변환 (순수 함수)."""
    counts = detail.get("대수") or []
    row = {
        "시도": normalize_text(grid.get("시도", "")),
        "시군구": normalize_text(grid.get("시군구", "")),
        "차종": normalize_text(grid.get("차종", "")),
        "공고종류": normalize_text(grid.get("공고종류", "")).strip("[]"),
        "접수기간": normalize_text(grid.get("접수기간", "")),
        "신청마감": normalize_text(grid.get("신청마감", "")),
        "공고파일": [normalize_text(f) for f in (detail.get("공고파일") or [])],
        # '접수방법: *일반: ...' 형태로 오므로 라벨 접두어를 떼어 기존 값 형태를 유지
        "접수방법": normalize_text(detail.get("접수방법", "")).removeprefix("접수방법:").strip(),
        "비고": normalize_multiline(detail.get("비고", "")),
    }
    for key, col in _COUNT_COLUMNS.items():
        row[key] = _counts_by_category(counts, col)
    return row


def _goto_with_retry(page, tries: int = 3) -> None:
    """ev.or.kr이 간헐적으로 빈 응답(ERR_EMPTY_RESPONSE)을 내려 재시도한다."""
    for attempt in range(tries):
        try:
            page.goto(URL, wait_until="domcontentloaded", timeout=60000)
            return
        except Exception:
            if attempt == tries - 1:
                raise
            time.sleep(5)


def _open_detail(page, row_id: str) -> dict:
    """해당 행의 '상세보기'를 눌러 모달을 열고 내용을 읽은 뒤 닫는다."""
    page.locator(f'#myGrid .ag-row[row-id="{row_id}"]').first.locator(
        '.ag-cell[col-id="button"] button').click()
    page.wait_for_selector("#modalArticleDetail.is-active", timeout=30000)
    page.wait_for_selector("#myGrid3 .ag-row", timeout=30000)
    detail = page.evaluate(_DETAIL_JS)
    page.click("#modalArticleDetail .js-detail-close")
    page.wait_for_selector("#modalArticleDetail.is-active", state="hidden", timeout=30000)
    return detail


def fetch_seongnam_rows(*, headless: bool = True) -> list[dict]:
    """Playwright로 ev.or.kr 지급현황 페이지에서 성남시 행만 추출해 반환."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        ctx = browser.new_context(locale="ko-KR")
        page = ctx.new_page()
        try:
            _goto_with_retry(page)
            page.wait_for_selector("#localDo_cd", timeout=30000)
            page.select_option("#localDo_cd", GYEONGGI_CODE)
            # 시군구 옵션은 이미 DOM에 있으나 hidden 상태 → state="attached"로 대기
            page.wait_for_selector(
                f"#local_cd1 option[value='{SEONGNAM_CODE}']",
                state="attached",
                timeout=30000,
            )
            page.select_option("#local_cd1", SEONGNAM_CODE)
            # 검색은 폼 POST로 페이지가 새로 로드된다(구 버전의 AJAX 조회와 다름)
            page.click("#btnSearch", timeout=10000)
            page.wait_for_selector("#myGrid .ag-row", timeout=60000)
            grids = page.evaluate(_GRID_ROWS_JS, SEONGNAM_NAME)
            rows = [_row_from_raw(g, _open_detail(page, g["_rowId"])) for g in grids]
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
