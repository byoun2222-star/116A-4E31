# -*- coding: utf-8 -*-
"""Reflow-EPUB raw export for the 145-book fixed-layout series, batched
20-at-a-time per the owner's instruction (2026-10-01: "145권은 실험적 의미가
강하니 대충해도 된다" - lower bar than the 10-book pilot, move fast, only
flag outright export failures).

Usage: python batch145_reflow_export.py <start_index> <count>
e.g. "python batch145_reflow_export.py 0 20" for the first batch.
"""
import sys, os, time, re
sys.path.insert(0, os.path.dirname(__file__))
import win32com.client
from resolve_indd_paths import get_all_resolved

EPUB = 1701868898
NEVER_INTERACT = 1699640946
SAVEOPTIONS_NO = 1852776480

OUT_DIR = r"C:\Users\a\.cys\claude\jobs\8442bc1d\tmp\145book_reflow_raw"
os.makedirs(OUT_DIR, exist_ok=True)


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def safe_key(title):
    return re.sub(r'[\\/:*?"<>|]', '_', title).strip()


def main():
    start = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 20

    result = get_all_resolved()
    batch = result[start:start + count]

    app = win32com.client.Dispatch("InDesign.Application")
    app.ScriptPreferences.UserInteractionLevel = NEVER_INTERACT

    for r, indd_path in batch:
        title = r['제목']
        key = safe_key(title)
        isbn = re.sub(r'\D', '', r['ISBN'])
        out_path = os.path.join(OUT_DIR, f"{key}__{isbn}_raw.epub")
        if os.path.exists(out_path):
            log(f"SKIP (이미 있음) - {title}")
            continue
        if not indd_path or not os.path.exists(indd_path):
            log(f"FAIL (indd 없음) - {title}")
            continue
        doc = None
        try:
            doc = app.Open(indd_path)
            tocstyles = doc.TOCStyles
            t = tocstyles.Item(1)
            if t.Name == "[기본값]":
                t.Name = f"EPUB목차_{key}"
            toc_style_name = t.Name
            try:
                e = t.TOCStyleEntries.Item(1)
                e.PageNumberPosition = int.from_bytes(b'none', 'big')
            except Exception as ex:
                log(f"  (페이지번호 설정 실패, 계속 진행: {ex})")

            ep = doc.EpubExportPreferences
            ep.BreakDocument = True
            ep.ParagraphStyleName = "장 제목"
            ep.TocStyleName = toc_style_name
            ep.EpubCreatePageNavigation = False

            doc.Export(EPUB, out_path, False)
            doc.Close(SAVEOPTIONS_NO)
            doc = None
            log(f"OK - {title} -> {os.path.basename(out_path)}")
        except Exception as ex:
            log(f"FAIL (예외) - {title} : {type(ex).__name__}: {ex}")
            try:
                if doc is not None:
                    doc.Close(SAVEOPTIONS_NO)
            except Exception:
                pass


if __name__ == "__main__":
    main()
