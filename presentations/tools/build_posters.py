r"""
專題海報輸出：presentations/2026-10_專題海報/src/poster{1,2}.html → A1 PDF（向量文字）＋ 300 dpi PNG ＋ 預覽圖。

需要：pip install playwright pymupdf（用本機已安裝的 Microsoft Edge，不必另外下載瀏覽器）。

    python presentations\tools\build_posters.py            # 兩張都輸出：PDF、300 dpi PNG、預覽
    python presentations\tools\build_posters.py --preview  # 只輸出 PDF 與預覽（快）

輸出到 presentations/2026-10_專題海報/：
  海報1_系統介紹.pdf、海報2_技術與成果.pdf    ← 交給影印店（A1 594 × 841 mm，向量，任何解析度都清楚）
  海報1_系統介紹_300dpi.png、海報2_技術與成果_300dpi.png  ← 備用（7016 × 9933 px，300 dpi）
  preview/海報{1,2}_預覽.png                    ← 低解析度預覽
"""
import argparse
import sys
from pathlib import Path

import pymupdf
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "2026-10_專題海報"
SRC = OUT / "src"
POSTERS = [("poster1.html", "海報1_系統介紹"), ("poster2.html", "海報2_技術與成果")]


# 海報與每個區塊（.box 是 overflow: hidden，內容超出會被默默切掉）超出多少 mm；另列出各區塊高度
CHECK_JS = """(() => {
  const mm = px => Math.round(px * 25.4 / 96 * 10) / 10;
  const out = {overflow: [], heights: []};
  const p = document.querySelector('.poster');
  if (p.scrollHeight - p.clientHeight > 1) out.overflow.push(['poster', mm(p.scrollHeight - p.clientHeight)]);
  for (const b of document.querySelectorAll('.box')) {
    const name = (b.querySelector('h2') || {}).textContent || '?';
    if (b.scrollHeight - b.clientHeight > 1) out.overflow.push([name, mm(b.scrollHeight - b.clientHeight)]);
    if (b.scrollWidth - b.clientWidth > 1) out.overflow.push([name + ' (width)', mm(b.scrollWidth - b.clientWidth)]);
    out.heights.push([name, mm(b.getBoundingClientRect().height)]);
  }
  return out;
})()"""


def render_pdf(page, html: Path, pdf: Path, measure: bool = False) -> None:
    page.goto(html.as_uri(), wait_until="networkidle", timeout=120000)
    page.evaluate("document.fonts.ready")
    page.wait_for_timeout(500)
    check = page.evaluate(CHECK_JS)
    for name, amount in check["overflow"]:
        print(f"  WARNING {html.name}: {name} overflows by {amount} mm", flush=True)
    if measure:
        for name, height in check["heights"]:
            print(f"  {name}: {height} mm", flush=True)
    page.pdf(path=str(pdf), prefer_css_page_size=True, print_background=True,
             margin={"top": "0", "right": "0", "bottom": "0", "left": "0"})


def rasterize(pdf: Path, png: Path, dpi: int) -> None:
    doc = pymupdf.open(pdf)
    pix = doc[0].get_pixmap(dpi=dpi)
    pix.set_dpi(dpi, dpi)
    pix.save(png)
    doc.close()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--preview", action="store_true", help="skip the 300 dpi PNG")
    ap.add_argument("--measure", action="store_true", help="print each section's height in mm")
    args = ap.parse_args(argv)
    (OUT / "preview").mkdir(exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge")
        page = browser.new_page()
        for src, name in POSTERS:
            html = SRC / src
            if not html.exists():
                continue
            pdf = OUT / f"{name}.pdf"
            render_pdf(page, html, pdf, measure=args.measure)
            rasterize(pdf, OUT / "preview" / f"{name}_預覽.png", 40)
            if not args.preview:
                rasterize(pdf, OUT / f"{name}_300dpi.png", 300)
            print(f"{name}: ok", flush=True)
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
