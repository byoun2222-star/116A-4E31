# -*- coding: utf-8 -*-
"""Content-completeness audit for the 145-book reflow expansion, same
method that caught 시편44's 22KB chapter loss in the 10-book pilot: compare
stripped-text character counts between each book's raw InDesign export and
its final processed output. A <1% difference is expected (blank-page/
printed-TOC-junk removal); anything bigger needs a direct look.
"""
import zipfile, re, os, glob
from urllib.parse import unquote

RAW_DIR = r"C:\Users\a\.cys\claude\jobs\8442bc1d\tmp\145book_reflow_raw"
FINAL_DIR = r"C:\Users\a\.cys\claude\jobs\8442bc1d\tmp\145book_reflow_final"


def total_text(path):
    z = zipfile.ZipFile(path)
    opf_name = [n for n in z.namelist() if n.endswith('.opf')][0]
    opf = z.read(opf_name).decode('utf-8')
    spine = re.findall(r'<itemref idref="([^"]+)"', opf)
    manifest = dict(re.findall(r'<item id="([^"]+)" href="([^"]+)"', opf))
    total = 0
    for s in spine:
        href = manifest.get(s)
        if not href:
            continue
        full = 'OEBPS/' + unquote(href)
        if full not in z.namelist():
            continue
        d = z.read(full).decode('utf-8', errors='replace')
        m = re.search(r'<body[^>]*>(.*)</body>', d, re.DOTALL)
        if not m:
            continue
        t = re.sub('<[^>]+>', '', m.group(1))
        t = re.sub(r'\s+', '', t)
        total += len(t)
    return total


def main():
    raw_files = sorted(glob.glob(os.path.join(RAW_DIR, "*_raw.epub")))
    results = []
    for raw_path in raw_files:
        base = os.path.basename(raw_path)[:-len("_raw.epub")]
        final_path = os.path.join(FINAL_DIR, base + "_final.epub")
        if not os.path.exists(final_path):
            results.append((base, None, None, None, "FINAL_MISSING"))
            continue
        try:
            raw_n = total_text(raw_path)
            final_n = total_text(final_path)
        except Exception as e:
            results.append((base, None, None, None, f"ERROR:{type(e).__name__}:{e}"))
            continue
        pct = 100 * final_n / raw_n if raw_n else 0
        flag = "OK" if pct >= 95 else "CHECK"
        results.append((base, raw_n, final_n, pct, flag))

    print(f"총 {len(results)}권 감사")
    bad = [r for r in results if r[4] != "OK"]
    print(f"문제 의심: {len(bad)}권\n")
    for base, raw_n, final_n, pct, flag in results:
        if flag != "OK":
            print(f"[{flag}] {base} | raw={raw_n} final={final_n} pct={pct}")


if __name__ == "__main__":
    main()
