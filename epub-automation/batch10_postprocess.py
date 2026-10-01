# -*- coding: utf-8 -*-
import sys, os, subprocess
sys.path.insert(0, os.path.dirname(__file__))
from build_reflow_generic import fix_epub_core

RAW_DIR = r"C:\Users\a\.cys\claude\jobs\8442bc1d\tmp\10book_raw"
COVER_DIR = r"C:\Users\a\OneDrive\Desktop\내지와 표지 업로드용 10권(시편41-아가서1)\표지_업로드용_10권(시편41-아가서1)"
JAVA = r"C:\Program Files (x86)\KTSpeedClient\jre\bin\java.exe"
EPUBCHECK_JAR = None
import epubcheck
EPUBCHECK_JAR = os.path.join(os.path.dirname(epubcheck.__file__), "epubcheck.jar")

BOOKS = [
    ("시편41", "시편의 복음이야기 41권", "9791124736548"),
    ("시편42", "시편의 복음이야기 42권", "9791124736562"),
    ("시편43", "스펄전의 시편의 복음이야기 43", "9791124736586"),
    ("시편44", "스펄전의 시편의 복음이야기 44", "9791124736609"),
    ("잠언1", "스펄전의 잠언의 복음이야기 1", "9791124736623"),
    ("잠언2", "스펄전의 잠언의 복음이야기 2", "9791124736647"),
    ("잠언3", "스펄전의 잠언의 복음이야기 3", "9791124736661"),
    ("잠언4", "스펄전의 잠언의 복음이야기 4", "9791124736685"),
    ("전도서", "스펄전의 전도서의 복음이야기", "9791124736708"),
    # 아가서1은 구조가 달라(BreakDocument 스타일그룹 버그) build_agaseo1_final.py로
    # 별도 처리·검증 완료 - 이 범용 배치에서 제외(덮어쓰기 방지).
]

def run_epubcheck(path):
    out = path + ".epubcheck.txt"
    with open(out, "w", encoding="utf-8") as f:
        subprocess.run([JAVA, "-Xss8m", "-jar", EPUBCHECK_JAR, path], stdout=f, stderr=subprocess.STDOUT)
    with open(out, encoding="utf-8", errors="replace") as f:
        text = f.read()
    ok = "0개의 치명적 오류 / 0개의 오류" in text or "Message: 0" in text
    # locale-independent: parse the summary numbers
    import re
    m = re.search(r'(\d+).*?(\d+).*?(\d+).*?(\d+)', text[-300:])
    fatal_ok = ("0" in text.splitlines()[-2]) if len(text.splitlines()) >= 2 else False
    return text, ("치명적 오류 0" in text.replace(" ", "") or "0\uac1c\uce58\uba85\uc801" in text.replace(" ", ""))

for key, title, isbn in BOOKS:
    raw = os.path.join(RAW_DIR, f"{key}_raw.epub")
    final = os.path.join(RAW_DIR, f"{key}_final.epub")
    cover = os.path.join(COVER_DIR, f"{isbn}.jpg")
    print(f"=== {key} ===")
    try:
        result = fix_epub_core(raw, final, title, isbn, cover)
        print(" build:", result)
    except Exception as e:
        print(" build FAILED:", type(e).__name__, e)
        continue
    text, ok = run_epubcheck(final)
    tail = "\n".join(text.strip().splitlines()[-3:])
    print(" epubcheck tail:", tail)
