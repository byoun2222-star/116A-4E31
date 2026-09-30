# -*- coding: utf-8 -*-
import csv, os

BASE = r"C:\Users\a\install-jarvis\book-production\output\yeokseo\yeokseo_master_verified.csv"
BAD_KW = ['5단', 'paperbook', '교보', '목차미비', '틀잡기', '1차 작업']

PSALM_DIR = r"C:\Users\a\OneDrive\Desktop\출간용 책들\역서\스펄전 설교들\스펄전의 구약성경 복음설교 시리즈\15. 스펄전의 시편의 복음이야기"

MANUAL = {
    '기도의 용사되기': r"C:\Users\a\OneDrive\Desktop\출간용 책들\역서\스펄전 설교들\스펄전의 주제별 복음설교 시리즈\스펄전의 기도 시리즈\기도의 용사되기\스펄전의 기도의 용사되기271끝(ebook 출판본).indd",
    '스펄전의 성령 하나님을 아는 지식': r"C:\Users\a\OneDrive\Desktop\출간용 책들\역서\스펄전 설교들\스펄전의 주제별 복음설교 시리즈\스펄전의 성령 시리즈\스펄젼의 성령 하나님에 관한 지식\스펄전의 성령 하나님을 아는 지식(ebook) 282.indd",
    '2 예수 그리스도 안에 거하기': r"C:\Users\a\OneDrive\Desktop\출간용 책들\역서\스펄전 설교들\스펄전의 주제별 복음설교 시리즈\스펄전의 예수 그리스도 시리즈\2 예수 그리스도 안에 거하기\스펄전의 예수 그리스도 안에 거하기283(ebook 출판본).indd",
}

def resolve_indd(title, pdf_path, pages_hint):
    if title in MANUAL:
        p = MANUAL[title]
        return p if os.path.exists(p) else None

    # 시편1-40 special: look in per-volume subfolder under PSALM_DIR
    if title.startswith("스펄전의 시편의 복음이야기") and ("41" not in title and "42" not in title and "43" not in title and "44" not in title):
        num = title.replace("스펄전의 시편의 복음이야기", "").strip()
        subdir = os.path.join(PSALM_DIR, f"스펄전의 시편의 복음이야기{num}")
        if os.path.isdir(subdir):
            cands = [f for f in os.listdir(subdir) if f.lower().endswith('.indd')]
            filtered = [f for f in cands if not any(k in f for k in BAD_KW)]
            ebook_only = [f for f in filtered if 'ebook' in f.lower()]
            pool = ebook_only if ebook_only else filtered
            if len(pool) == 1:
                return os.path.join(subdir, pool[0])
            if pages_hint:
                m = [f for f in pool if pages_hint in f]
                if len(m) == 1:
                    return os.path.join(subdir, m[0])
        return None

    direct = os.path.splitext(pdf_path)[0] + '.indd'
    if os.path.exists(direct):
        return direct
    d = os.path.dirname(pdf_path)
    if not os.path.isdir(d):
        return None
    cands = [f for f in os.listdir(d) if f.lower().endswith('.indd')]
    filtered = [f for f in cands if not any(k in f for k in BAD_KW)]
    ebook_only = [f for f in filtered if 'ebook' in f.lower()]
    pool = ebook_only if ebook_only else filtered
    if len(pool) == 1:
        return os.path.join(d, pool[0])
    if pages_hint:
        m = [f for f in pool if pages_hint in f]
        if len(m) == 1:
            return os.path.join(d, m[0])
    return None

def get_all_resolved():
    with open(BASE, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    result = []
    for r in rows:
        indd = resolve_indd(r['제목'], r['PDF'], r['페이지수'].strip())
        result.append((r, indd))
    return result

if __name__ == "__main__":
    result = get_all_resolved()
    ok = [x for x in result if x[1]]
    bad = [x for x in result if not x[1]]
    print("resolved:", len(ok), "/", len(result))
    for r, _ in bad:
        print("UNRESOLVED:", r['제목'])
