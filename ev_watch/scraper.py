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
    """브라우저에서 추출한 raw 셀 데이터를 최종 Row 구조로 변환 (순수 함수)."""
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
    """Playwright로 ev.or.kr 지급현황 페이지에서 성남시 행만 추출해 반환."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        ctx = browser.new_context(locale="ko-KR")
        page = ctx.new_page()
        try:
            page.goto(URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_selector("#localDo_cd", timeout=30000)
            page.select_option("#localDo_cd", GYEONGGI_CODE)
            # 시군구 옵션은 이미 DOM에 있으나 hidden 상태 → state="attached"로 대기
            page.wait_for_selector(
                f"#local_cd1 option[value='{SEONGNAM_CODE}']",
                state="attached",
                timeout=30000,
            )
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
