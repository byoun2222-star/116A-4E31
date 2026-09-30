# -*- coding: utf-8 -*-
import sys, os, re, csv, shutil, traceback, time
sys.path.insert(0, os.path.dirname(__file__))
from resolve_indd_paths import get_all_resolved
from fix_indesign_epub import fix_epub
import win32com.client

FIXED_LAYOUT_EPUB = 1701865080
SAVEOPTIONS_NO = 1852776480

DESK = r"C:\Users\a\OneDrive\Desktop"
OUT_ROOT = os.path.join(DESK, "역서_고정형이펍_145권")
TMP_DIR = r"C:\Users\a\.cys\claude\jobs\8442bc1d\tmp\indesign_epub_raw"
COVER_DIR = r"C:\Users\a\install-jarvis\book-production\output\yeokseo\표지_업로드용"
LOG_PATH = os.path.join(OUT_ROOT, "_변환로그.txt")

os.makedirs(OUT_ROOT, exist_ok=True)
os.makedirs(TMP_DIR, exist_ok=True)

def isbn_num(s):
    return re.sub(r"[^0-9]", "", s or "")

def safe_folder_name(name):
    return re.sub(r'[\\/:*?"<>|]', "_", name).strip()

def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")

NEVER_INTERACT = 1699640946

def main():
    app = win32com.client.Dispatch("InDesign.Application")
    app.ScriptPreferences.UserInteractionLevel = NEVER_INTERACT
    log("UserInteractionLevel set to NEVER_INTERACT (dialogs suppressed)")
    resolved = get_all_resolved()

    total = len(resolved)
    ok_count = 0
    fail_count = 0

    for idx, (row, indd_path) in enumerate(resolved, start=1):
        title = row["제목"].strip()
        isbn = isbn_num(row["ISBN"])
        folder = os.path.join(OUT_ROOT, safe_folder_name(title))

        if not indd_path or not os.path.exists(indd_path):
            log(f"[{idx}/{total}] SKIP (indd not found) - {title}")
            fail_count += 1
            continue

        raw_out = os.path.join(TMP_DIR, f"{isbn}_raw.epub")
        final_out = os.path.join(folder, f"{isbn}.epub")

        if os.path.exists(final_out):
            log(f"[{idx}/{total}] SKIP (already done) - {title}")
            ok_count += 1
            continue

        doc = None
        try:
            doc = app.Open(indd_path)
            doc.Export(FIXED_LAYOUT_EPUB, raw_out, False)
            doc.Close(SAVEOPTIONS_NO)
            doc = None

            os.makedirs(folder, exist_ok=True)
            result = fix_epub(raw_out, final_out, title)

            cover_src = os.path.join(COVER_DIR, isbn + ".jpg")
            if os.path.exists(cover_src):
                shutil.copy2(cover_src, os.path.join(folder, isbn + ".jpg"))

            os.remove(raw_out)
            ok_count += 1
            log(f"[{idx}/{total}] OK - {title} | pages={result['renamed_pages']} fonts={result['fonts_fixed']} size={result['out_size_mb']:.1f}MB")
        except Exception as e:
            fail_count += 1
            log(f"[{idx}/{total}] FAIL - {title} | {type(e).__name__}: {e}")
            try:
                if doc is not None:
                    doc.Close(SAVEOPTIONS_NO)
            except Exception:
                pass

    log(f"=== DONE: {ok_count} ok, {fail_count} failed, {total} total ===")

if __name__ == "__main__":
    main()
