# -*- coding: utf-8 -*-
"""Generic post-export fixer for InDesign-exported (fixed-layout) EPUBs.
Fixes: (1) parenthesis/Korean internal xhtml filenames -> text-NNN.xhtml
       (2) dc:title -> correct title, dc:language -> single 'ko'
       (3) IDPF font obfuscation -> deobfuscate + remove META-INF/encryption.xml
"""
import zipfile, re, os, hashlib
from urllib.parse import quote, unquote

WS = [0x20, 0x09, 0x0D, 0x0A]

def idpf_key(identifier_text):
    stripped = ''.join(ch for ch in identifier_text if ord(ch) not in WS)
    return hashlib.sha1(stripped.encode('utf-8')).digest()

def deobfuscate(data, key20):
    n = min(1040, len(data))
    head = bytearray(data[:n])
    for i in range(n):
        head[i] ^= key20[i % 20]
    return bytes(head) + data[n:]

def looks_like_font(data):
    if len(data) < 4:
        return False
    return data[:4] in (b'\x00\x01\x00\x00', b'OTTO', b'true', b'ttcf')

def fix_epub(src_path, out_path, correct_title, lang='ko', cover_jpg_path=None):
    """Returns dict with status info. Raises on unrecoverable problems."""
    zin = zipfile.ZipFile(src_path, 'r')
    names = zin.namelist()

    opf_name = [n for n in names if n.endswith('.opf')][0]
    oebps_dir = os.path.dirname(opf_name)  # usually 'OEBPS'
    opf_text = zin.read(opf_name).decode('utf-8')

    # ---- 1) chapter filename fix ----
    # find manifest items with media-type application/xhtml+xml whose href matches -N.xhtml pattern
    manifest_items = re.findall(r'<item\b[^>]*href="([^"]+)"[^>]*media-type="application/xhtml\+xml"[^>]*/>', opf_text)
    manifest_items += re.findall(r'<item\b[^>]*media-type="application/xhtml\+xml"[^>]*href="([^"]+)"[^>]*/>', opf_text)
    manifest_items = sorted(set(manifest_items))
    page_files = [h for h in manifest_items if re.search(r'-\d+\.xhtml$', unquote(h))]

    rename_map = {}
    if page_files:
        def pagenum(h):
            m = re.search(r'-(\d+)\.xhtml$', unquote(h))
            return int(m.group(1))
        page_files.sort(key=pagenum)
        for i, old_href in enumerate(page_files, start=1):
            new_href = f"text-{i:04d}.xhtml"
            rename_map[unquote(old_href)] = new_href  # key = literal filename as stored in zip

    # ---- 1b) any other manifest item (image/etc.) with problematic chars in filename ----
    all_hrefs = re.findall(r'<item\b[^>]*href="([^"]+)"', opf_text)
    img_counter = 0
    text_counter = len(rename_map)
    for h in sorted(set(all_hrefs)):
        literal = unquote(h)
        base = os.path.basename(literal)
        if base in rename_map:
            continue
        if re.search(r'[()가-힣\s]', base):  # parens, Korean, or spaces
            ext = os.path.splitext(base)[1]
            if ext.lower() in ('.xhtml', '.html'):
                text_counter += 1
                rename_map[base] = f"text-{text_counter:04d}.xhtml"
            else:
                img_counter += 1
                rename_map[base] = f"asset-{img_counter:03d}{ext}"

    new_opf = opf_text
    for old_literal, new_href in rename_map.items():
        # replace both percent-encoded and literal occurrences in the OPF text
        new_opf = new_opf.replace(quote(old_literal), new_href)
        new_opf = new_opf.replace(old_literal, new_href)

    # ---- 2) title / language fix ----
    new_opf = re.sub(r'(<dc:title[^>]*>)[^<]*(</dc:title>)', lambda m: m.group(1) + correct_title + m.group(2), new_opf, count=1)
    new_opf = re.sub(r'\s*<dc:language[^>]*>[^<]*</dc:language>', '', new_opf)
    new_opf = re.sub(r'(<dc:title[^>]*>[^<]*</dc:title>)', r'\1\n<dc:language>' + lang + '</dc:language>', new_opf, count=1)

    # also grab identifier for font key BEFORE we touch it (InDesign auto-UUID; leave as-is)
    m_id = re.search(r'<dc:identifier[^>]*>([^<]*)</dc:identifier>', opf_text)
    identifier_text = m_id.group(1) if m_id else ""

    # ---- 3) fonts / encryption ----
    has_encryption = 'META-INF/encryption.xml' in names
    new_font_bytes = {}
    font_status = []
    if has_encryption:
        enc_text = zin.read('META-INF/encryption.xml').decode('utf-8')
        font_refs = re.findall(r'CipherReference URI="([^"]+)"', enc_text)
        key = idpf_key(identifier_text)
        for ref in font_refs:
            zpath = unquote(ref)
            if zpath not in names:
                # try with oebps prefix variants
                candidates = [n for n in names if n.endswith(os.path.basename(zpath))]
                if len(candidates) == 1:
                    zpath = candidates[0]
                else:
                    font_status.append((ref, False, False, "path-not-found"))
                    continue
            raw = zin.read(zpath)
            before_ok = looks_like_font(raw)
            fixed = deobfuscate(raw, key)
            after_ok = looks_like_font(fixed)
            font_status.append((ref, before_ok, after_ok, "ok" if after_ok else "verify-fail"))
            if after_ok:
                new_font_bytes[zpath] = fixed
        all_ok = all(s[3] == "ok" for s in font_status) if font_status else True
    else:
        all_ok = True

    if has_encryption and not all_ok:
        zin.close()
        raise RuntimeError(f"font deobfuscation verification failed: {font_status}")

    # ---- 4) fix broken cover (InDesign leaves <img src="image/"> empty when
    #      EpubExportPreferences.CoverImageFile wasn't set at export time) ----
    cover_bytes = None
    cover_xhtml_name = [n for n in names if n.endswith('cover.xhtml')]
    cover_xhtml_name = cover_xhtml_name[0] if cover_xhtml_name else None
    if cover_jpg_path and cover_xhtml_name and os.path.exists(cover_jpg_path):
        cover_text = zin.read(cover_xhtml_name).decode('utf-8')
        if re.search(r'src="image/"\s', cover_text) or re.search(r'src="image/"\s*/>', cover_text):
            with open(cover_jpg_path, 'rb') as f:
                cover_bytes = f.read()
            cover_text = re.sub(r'src="image/"', 'src="image/cover.jpg"', cover_text)
            new_font_bytes[cover_xhtml_name] = cover_text.encode('utf-8')  # reuse pass-through write path
            if not re.search(r'<meta name="cover"', new_opf):
                new_opf = new_opf.replace(
                    '<manifest>',
                    '<manifest>\n\t\t<item id="cover-img-fixed" href="image/cover.jpg" media-type="image/jpeg" properties="cover-image" />'
                )
                new_opf = re.sub(
                    r'(<metadata[^>]*>)',
                    r'\1\n\t\t<meta name="cover" content="cover-img-fixed" />',
                    new_opf, count=1
                )

    # ---- write output zip ----
    tmp_path = out_path + ".tmp"
    zout = zipfile.ZipFile(tmp_path, 'w')
    for item in zin.infolist():
        fn = item.filename
        if fn == 'META-INF/encryption.xml':
            continue
        data = zin.read(fn)
        if fn == opf_name:
            data = new_opf.encode('utf-8')
        elif fn in new_font_bytes:
            data = new_font_bytes[fn]
        elif fn.lower().endswith(('.ncx', '.xhtml', '.html', '.smil')):
            # rewrite any href/src references to renamed files (e.g. toc.ncx nav targets)
            text = data.decode('utf-8')
            for old_literal, new_href in rename_map.items():
                text = text.replace(quote(old_literal), new_href)
                text = text.replace(old_literal, new_href)
            data = text.encode('utf-8')
        # rename chapter files
        target_name = fn
        base = os.path.basename(fn)
        if base in rename_map:
            target_name = os.path.join(os.path.dirname(fn), rename_map[base]).replace("\\", "/")
        elif fn in rename_map:
            target_name = rename_map[fn]
        if fn == 'mimetype':
            zout.writestr(item, data, compress_type=zipfile.ZIP_STORED)
        else:
            new_item = zipfile.ZipInfo(target_name, date_time=item.date_time)
            new_item.compress_type = item.compress_type
            new_item.external_attr = item.external_attr
            zout.writestr(new_item, data)
    if cover_bytes is not None:
        zout.writestr(f"{oebps_dir}/image/cover.jpg", cover_bytes)
    zout.close()
    zin.close()

    # verify
    zchk = zipfile.ZipFile(tmp_path, 'r')
    bad = zchk.testzip()
    assert bad is None, f"zip integrity failed: {bad}"
    names2 = zchk.namelist()
    assert 'META-INF/encryption.xml' not in names2
    remaining_paren = [n for n in names2 if ('(' in n or ')' in n)]
    zchk.close()

    os.replace(tmp_path, out_path)

    return {
        "renamed_pages": len(rename_map),
        "fonts_fixed": len([s for s in font_status if s[3] == "ok"]),
        "remaining_paren_names": remaining_paren,
        "cover_fixed": cover_bytes is not None,
        "out_size_mb": os.path.getsize(out_path) / (1024 * 1024),
    }
