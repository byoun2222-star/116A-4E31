# -*- coding: utf-8 -*-
import win32com.client, os, time

EPUB = 1701868898
NEVER_INTERACT = 1699640946
SAVEOPTIONS_NO = 1852776480

OUT_DIR = r"C:\Users\a\.cys\claude\jobs\8442bc1d\tmp\10book_raw"
os.makedirs(OUT_DIR, exist_ok=True)

BASE = r"C:\Users\a\OneDrive\Desktop\출간용 책들\역서\스펄전 설교들\스펄전의 구약성경 복음설교 시리즈"
BOOKS = [
    ("시편41", "9791124736548", BASE + r"\15. 스펄전의 시편의 복음이야기\스펄전의 시편의 복음이야기 41\새 폴더\시편의 복음이야기 41권(316 ebook 출판용).indd"),
    ("시편42", "9791124736562", BASE + r"\15. 스펄전의 시편의 복음이야기\스펄전의 시편의 복음이야기 42\새 폴더\시편의 복음이야기 42(263 ebook 출판용).indd"),
    ("시편43", "9791124736586", BASE + r"\15. 스펄전의 시편의 복음이야기\스펄전의 시편의 복음이야기 43\스펄전의 시편의 복음이야기 43(312 ebook 출판용).indd"),
    ("시편44", "9791124736609", BASE + r"\15. 스펄전의 시편의 복음이야기\스펄전의 시편의 복음이야기 44\새 폴더\스펄전의 시편의 복음이야기 44(238 ebook 출판용).indd"),
    ("잠언1", "9791124736623", BASE + r"\16. 스펄전의 잠언의 복음이야기\잠언 1권\새 폴더\스펄전의 잠언의 복음이야기 1(294 ebook 출판용).indd"),
    ("잠언2", "9791124736647", BASE + r"\16. 스펄전의 잠언의 복음이야기\잠언2권\새 폴더\스펄전의 잠언의 복음이야기 2(319 ebook 출판용).indd"),
    ("잠언3", "9791124736661", BASE + r"\16. 스펄전의 잠언의 복음이야기\잠언3권\새 폴더\스펄전의 잠언의 복음이야기 3(292 ebook출판용).indd"),
    ("잠언4", "9791124736685", BASE + r"\16. 스펄전의 잠언의 복음이야기\잠언4권\새 폴더\스펄전의 잠언의 복음이야기 4(353 ebook출판용).indd"),
    ("전도서", "9791124736708", BASE + r"\17. 스펄전의 전도서의 복음이야기\새 폴더\스펄전의 전도서의 복음이야기(330 ebook출판용).indd"),
    ("아가서1", "9791124736722", BASE + r"\18. 스펄전의 아가서의 복음이야기\스펄전의 아가의 복음이야기 1\스펄전의 아가서의 복음이야기 1(273  ebook출판용).indd"),
]

def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)

def main():
    app = win32com.client.Dispatch("InDesign.Application")
    app.ScriptPreferences.UserInteractionLevel = NEVER_INTERACT

    for key, isbn, indd_path in BOOKS:
        out_path = os.path.join(OUT_DIR, f"{key}_raw.epub")
        if os.path.exists(out_path):
            log(f"SKIP (이미 있음) - {key}")
            continue
        if not os.path.exists(indd_path):
            log(f"FAIL (indd 없음) - {key} : {indd_path}")
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
            log(f"OK - {key} -> {out_path}")
        except Exception as ex:
            log(f"FAIL (예외) - {key} : {type(ex).__name__}: {ex}")
            try:
                if doc is not None:
                    doc.Close(SAVEOPTIONS_NO)
            except Exception:
                pass

if __name__ == "__main__":
    main()
