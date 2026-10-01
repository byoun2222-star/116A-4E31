# -*- coding: utf-8 -*-
"""Batch-fix the shared dc:identifier defect found across BOTH the 145-book
fixed-layout batch and the 10-book reflow batch: InDesign exported every one
of these 155 books with the exact same urn:uuid, because later books were
made by duplicating/saving-as from an earlier book's .indd file, which never
regenerates this internal metadata field.

Fixed-layout books in this series have no IDPF font protection (no
META-INF/encryption.xml), so unlike the reflow pipeline's font-reobfuscation
step, this fix is a pure text substitution in content.opf - nothing else in
the EPUB needs to change.

Usage: point BASE_DIR at the root folder containing one subfolder per book,
each with the book's own cover image named "<isbn13>.jpg" (this series'
existing convention) and one .epub file. Writes corrected copies to OUT_DIR,
mirroring the same per-book subfolder layout, and never touches the source.
"""
import zipfile, re, os, glob, uuid

BASE_DIR = r"C:\Users\a\OneDrive\Desktop\내지와 표지 업로드용 역서145권\역서_고정형이펍_145권"
OUT_DIR = r"C:\Users\a\OneDrive\Desktop\역서145권_UUID수정본"


def fix_uuid(epub_path, isbn13, out_path):
    # uuid5 (not uuid4): deterministic from the ISBN, so re-running this
    # script on the same book always reproduces the same id instead of
    # minting a new "edition" identity every time.
    new_id = 'urn:uuid:' + str(uuid.uuid5(uuid.NAMESPACE_URL, 'isbn:' + isbn13))
    tmp = out_path + '.tmp'
    zin = zipfile.ZipFile(epub_path, 'r')
    zout = zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED)
    changed = False
    for item in zin.infolist():
        data = zin.read(item.filename)
        if item.filename.endswith('.opf'):
            text = data.decode('utf-8')
            new_text, n = re.subn(
                r'(<dc:identifier[^>]*>)[^<]*(</dc:identifier>)',
                lambda m: m.group(1) + new_id + m.group(2), text, count=1)
            if n == 1:
                data = new_text.encode('utf-8')
                changed = True
        if item.filename == 'mimetype':
            zout.writestr(item, data, compress_type=zipfile.ZIP_STORED)
        else:
            ni = zipfile.ZipInfo(item.filename, date_time=item.date_time)
            ni.compress_type = item.compress_type
            ni.external_attr = item.external_attr
            zout.writestr(ni, data)
    zin.close()
    zout.close()
    os.replace(tmp, out_path)
    return changed, new_id


def main():
    dirs = sorted(d for d in os.listdir(BASE_DIR) if os.path.isdir(os.path.join(BASE_DIR, d)))
    ids_seen = set()
    ok = 0
    for d in dirs:
        full = os.path.join(BASE_DIR, d)
        jpgs = glob.glob(os.path.join(full, '*.jpg'))
        epubs = glob.glob(os.path.join(full, '*.epub'))
        if not jpgs or not epubs:
            print('SKIP (jpg/epub 없음):', d)
            continue
        isbn13 = os.path.splitext(os.path.basename(jpgs[0]))[0]
        out_dir = os.path.join(OUT_DIR, d)
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, os.path.basename(epubs[0]))
        changed, new_id = fix_uuid(epubs[0], isbn13, out_path)
        if changed:
            ok += 1
            ids_seen.add(new_id)
        else:
            print('FAIL (identifier 매칭 안됨):', d)
    print(f'{len(dirs)}권 중 {ok}권 성공, 고유 UUID {len(ids_seen)}개')


if __name__ == '__main__':
    main()
