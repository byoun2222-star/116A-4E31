# -*- coding: utf-8 -*-
"""Post-process raw reflow exports for the 145-book batch using the same
generic pipeline validated on the 10-book pilot. Per owner (2026-10-01):
this batch is experimental - move fast, light epubcheck pass only, don't
deep-dive every quirk the way the 10-book pilot did.

Usage: python batch145_reflow_postprocess.py <glob_pattern_for_raw_files>
Default processes everything in 145book_reflow_raw/.
"""
import sys, os, glob, subprocess, re
sys.path.insert(0, os.path.dirname(__file__))
from build_reflow_generic import fix_epub_core

RAW_DIR = r"C:\Users\a\.cys\claude\jobs\8442bc1d\tmp\145book_reflow_raw"
OUT_DIR = r"C:\Users\a\.cys\claude\jobs\8442bc1d\tmp\145book_reflow_final"
os.makedirs(OUT_DIR, exist_ok=True)

COVER_DIR = r"C:\Users\a\OneDrive\Desktop\내지와 표지 업로드용 역서145권\역서_고정형이펍_145권"


def find_cover_jpg(isbn):
    cands = glob.glob(os.path.join(COVER_DIR, "*", f"{isbn}.jpg"))
    return cands[0] if cands else None

JAVA = r"C:\Program Files (x86)\KTSpeedClient\jre\bin\java.exe"
import epubcheck
EPUBCHECK_JAR = os.path.join(os.path.dirname(epubcheck.__file__), "epubcheck.jar")


def run_epubcheck(path):
    r = subprocess.run([JAVA, "-Xss8m", "-jar", EPUBCHECK_JAR, path],
                        capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = r.stdout + r.stderr
    has_fatal = "FATAL" in out
    has_error = re.search(r'ERROR\(', out) is not None
    return out, has_fatal, has_error


def main():
    raw_files = sorted(glob.glob(os.path.join(RAW_DIR, "*_raw.epub")))
    results = {"ok": [], "build_fail": [], "epub_error": []}
    for raw_path in raw_files:
        base = os.path.basename(raw_path)[:-len("_raw.epub")]
        title, isbn = base.rsplit("__", 1)
        out_path = os.path.join(OUT_DIR, base + "_final.epub")
        print(f"=== {title} ===", flush=True)
        try:
            info = fix_epub_core(raw_path, out_path, title, isbn, find_cover_jpg(isbn))
            print(" build:", info)
        except Exception as e:
            print(" build FAILED:", type(e).__name__, e)
            results["build_fail"].append(title)
            continue
        out, has_fatal, has_error = run_epubcheck(out_path)
        tail = "\n".join(out.strip().splitlines()[-2:])
        print(" epubcheck:", tail)
        if has_fatal or has_error:
            results["epub_error"].append(title)
        else:
            results["ok"].append(title)
    print()
    print(f"성공: {len(results['ok'])} / 빌드실패: {len(results['build_fail'])} / epubcheck오류: {len(results['epub_error'])}")
    for t in results["build_fail"]:
        print(" 빌드실패:", t)
    for t in results["epub_error"]:
        print(" epubcheck오류:", t)


if __name__ == "__main__":
    main()
