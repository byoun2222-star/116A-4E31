# -*- coding: utf-8 -*-
"""Generalized reflow-EPUB post-processor (derived from build_reflow_final.py,
book1-specific hardcoding replaced with content-pattern detection).

Pipeline per book:
 1. classify every spine xhtml file: blank / bare-roman-numeral / chapter-title
    (paired with the following file) / orphan front-matter (by content pattern)
    / everything else (kept in place - assumed to be the main threaded body).
 2. merge roman+title pairs, add sub-heading (_-스타일) anchors, drop blanks
    and the printed TOC-page dump (its files score very low unique length and
    duplicate roman numerals with page-number digits attached).
 3. relocate orphan front-matter (publisher blurb / title page / colophon /
    English title / author bio) to the very front, in a best-guess order
    inferred from content markers.
 4. rebuild manifest/spine/nav.xhtml/toc.ncx from scratch; apply the
    font/size CSS spec; fix the broken cover <img>; add ISBN identifier;
    apply the 5 epubcheck-required OPF/DOCTYPE fixes.
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
    return len(data) >= 4 and data[:4] in (b'\x00\x01\x00\x00', b'OTTO', b'true', b'ttcf')

DOCTYPE_RE = re.compile(r'<!DOCTYPE html PUBLIC "[^"]*"(\s*"[^"]*")?>')
def fix_doctype(text):
    return DOCTYPE_RE.sub('<!DOCTYPE html>', text)

def get_body_inner(xhtml_text):
    m = re.search(r'<body[^>]*>(.*)</body>', xhtml_text, re.DOTALL)
    return m.group(1) if m else ''

def visible_text(xhtml_text):
    body = get_body_inner(xhtml_text)
    return re.sub(r'\s+', ' ', re.sub('<[^>]+>', ' ', body)).strip()

ROMAN_RE = re.compile(r'^[IVXLCDM]{1,6}\s*$')

def classify(idx, href, text, has_img, raw=''):
    t = text.strip()
    if not t and not has_img:
        return 'blank'
    if ROMAN_RE.match(t):
        return 'roman'
    # printed TOC page with real hyperlinks to other chapter files (a
    # different InDesign export sub-pattern than the "empty href" kind) -
    # 3+ cross-references to other xhtml files is the signature.
    cross_links = re.findall(r'<a href="[^"#]*\.xhtml#[^"]*"', raw)
    if len(cross_links) >= 3:
        return 'toc_dump'
    if '도서출판' in t or 'TNF' in t:
        return 'publisher'
    # dedicated title-page file: "<title> ... 지음 ... 옮김", short, no body prose
    if '지음' in t and '옮김' in t and len(t) < 150:
        return 'fm_title'
    if re.search(r'ISBN', t) and ('등록번호' in t or '발행' in t):
        return 'colophon'
    if ('Copyright' in t or 'Written by' in t or 'All rights reserved' in t) and re.search('[A-Za-z]{4,}', t):
        return 'english_title'
    if '내용' == t[:2] and re.search(r'\d', t) and len(t) < 400:
        return 'toc_heading'
    # printed TOC list entries: short, mostly digits/roman + page numbers, or
    # a lone short line ending in a number (page ref) without sentence punctuation
    if len(t) < 60 and re.search(r'\d{1,3}\s*$', t) and not re.search('[.!?"”]$', t):
        return 'toc_entry'
    return 'body'

def fix_epub_core(src_path, out_path, correct_title, isbn13, cover_jpg_path, lang='ko'):
    zin = zipfile.ZipFile(src_path, 'r')
    names = zin.namelist()
    opf_name = [n for n in names if n.endswith('.opf')][0]
    base_stem = None
    for n in names:
        if n.endswith('.xhtml') and 'OEBPS/' in n and n.count('/') == 1:
            fn = os.path.basename(n)
            if not re.search(r'-\d+\.xhtml$', fn) and fn not in ('cover.xhtml', 'nav.xhtml', 'toc.xhtml'):
                base_stem = fn[:-6]
    opf_text = zin.read(opf_name).decode('utf-8')
    manifest = dict(re.findall(r'<item id="([^"]+)" href="([^"]+)"', opf_text))
    href_by_id = {k: unquote(v) for k, v in manifest.items()}
    spine_ids = re.findall(r'<itemref idref="([^"]+)"', opf_text)

    def split_combined_frontmatter(sid, raw):
        """InDesign often dumps title-page-conclusion + colophon + English
        title-page + an empty frame + the printed-TOC heading all into ONE
        file, tagged with consistent div ids (_idContainer003/004/005/006/007).
        Split it into separate synthetic entries so each becomes its own page
        (matches the hand-verified book1/아가서1 structure), instead of
        letting classify() lump the whole file under one category."""
        if '_idContainer004"' not in raw or '_idContainer005"' not in raw:
            return None  # not the combined pattern - leave as-is
        def extract_div(html, div_id):
            m = re.search(r'<div id="' + div_id + r'"[^>]*>.*?</div>', html, re.DOTALL)
            return m.group(0) if m else ''
        colophon_block = extract_div(raw, '_idContainer004')
        english_block = extract_div(raw, '_idContainer005')
        # everything between <body> and the colophon div is "title page"
        # content, whether or not InDesign gave it an explicit _idContainer003
        # id (observed both variants across this book series).
        body_tag_m = re.search(r'<body[^>]*>', raw)
        head_text_block = raw[body_tag_m.end():raw.find('<div id="_idContainer004"')]
        title_block = ''

        def page(new_id, title, inner):
            return (
                '<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n<!DOCTYPE html>\n'
                '<html xmlns="http://www.w3.org/1999/xhtml">\n\t<head>\n\t\t<title>' + title + '</title>\n'
                '\t\t<link href="css/idGeneratedStyles.css" rel="stylesheet" type="text/css" />\n'
                '\t</head>\n\t<body id="' + new_id + '">\n' + inner + '\n\t</body>\n</html>\n'
            )
        # NOTE: the leading head_text_block (author/translator only, no title)
        # is intentionally NOT turned into its own page here - it's always a
        # duplicate of a dedicated short "<title> ... 지음 ... 옮김" file that
        # already exists elsewhere in the spine and gets classified as
        # 'fm_title' directly (see classify()). Keeping both would show an
        # incomplete title-less "내지 한글표지" page alongside the real one.
        parts = []
        if colophon_block:
            parts.append(('__fm_colophon_' + sid, page('__fm_colophon_' + sid, '판권', colophon_block), 'colophon'))
        if english_block:
            parts.append(('__fm_english_' + sid, page('__fm_english_' + sid, '내지 영문 표지', english_block), 'english_title'))
        return parts

    # ---- classify every spine item ----
    info = {}  # id -> dict(href, text, kind, img_count)
    for sid in spine_ids:
        href = href_by_id.get(sid)
        if not href or href == 'cover.xhtml':
            continue
        full = 'OEBPS/' + href
        if full not in names:
            continue
        raw = zin.read(full).decode('utf-8')

        split_parts = split_combined_frontmatter(sid, raw)
        if split_parts:
            for new_id, new_raw, kind in split_parts:
                t = visible_text(new_raw)
                info[new_id] = {'href': new_id + '.xhtml', 'text': t, 'kind': kind, 'raw': new_raw, 'img': 0}
            continue

        text = visible_text(raw)
        img_count = len(re.findall(r'<img', raw))
        kind = classify(sid, href, text, img_count > 0, raw)
        info[sid] = {'href': href, 'text': text, 'kind': kind, 'raw': raw, 'img': img_count}

    ordered = []
    for sid in spine_ids:
        if sid in info:
            ordered.append(sid)
        else:
            ordered.extend(k for k in info if k.endswith('_' + sid))

    # ---- split embedded orphan tails out of otherwise-real chapter files ----
    # InDesign sometimes appends an unthreaded story (publisher blurb, or a
    # left-over printed-TOC fragment with empty self-links) onto the END of
    # the last real paragraph block of an ordinary chapter file. Detect by
    # finding a sibling <div> that starts with a publisher-blurb marker or a
    # 장-제목 paragraph whose only link is an empty href="" (broken TOC self-
    # link), split it off into its own synthetic entry.
    extra_front = []
    extra_counter = 0
    for sid in list(ordered):
        raw = info[sid]['raw']
        divs = list(re.finditer(r'<div\b[^>]*>', raw))
        split_at = None
        for m in divs:
            tail = raw[m.start():]
            head_p = re.search(r'<p\b[^>]*class="([^"]*)"[^>]*>(.*?)</p>', tail, re.DOTALL)
            if not head_p:
                continue
            cls, inner = head_p.group(1), head_p.group(2)
            if '도서출판' in inner or 'TNF' in inner:
                split_at = m.start()
                kind = 'publisher'
                break
            if '장-제목' in cls and re.search(r'<a href=""[^>]*>.*?</a>\s*<a href="">', inner):
                split_at = m.start()
                kind = 'toc_junk'
                break
        if split_at is not None and split_at > 200:
            body_open = re.search(r'<body[^>]*>', raw).end()
            if split_at > body_open + 100:
                prefix = raw[:split_at] + '</body>\n</html>\n'
                suffix_block = raw[split_at:]
                suffix_block = re.sub(r'</body>\s*</html>\s*$', '', suffix_block).rstrip()
                info[sid]['raw'] = prefix
                info[sid]['text'] = visible_text(prefix)
                if kind == 'publisher':
                    extra_counter += 1
                    new_id = f'__orphan_pub_{extra_counter}'
                    wrapper = re.sub(r'<body[^>]*>.*</body>', f'<body id="{new_id}">' + suffix_block + '</body>', raw, flags=re.DOTALL)
                    info[new_id] = {'href': f'{new_id}.xhtml', 'text': visible_text(wrapper), 'kind': 'publisher', 'raw': wrapper, 'img': 0}
                    idx = ordered.index(sid)
                    ordered.insert(idx + 1, new_id)
                # toc_junk suffix is simply discarded (owner: printed TOC not needed)

    # ---- merge roman-numeral-only files into the NEXT file ----
    merged_bodies = {}
    drop_ids = set()
    i = 0
    while i < len(ordered):
        sid = ordered[i]
        if info[sid]['kind'] == 'roman' and i + 1 < len(ordered):
            nxt = ordered[i + 1]
            roman_body = get_body_inner(info[sid]['raw']).strip()
            roman_body = re.sub(
                r'(<p\b)([^>]*class=")([^"]*)(")',
                lambda m: m.group(1) + m.group(2) + m.group(3) + ' chapter-roman' + m.group(4)
                          + ' style="text-align:center !important;text-indent:0 !important;'
                            'margin-left:0 !important;margin-right:0 !important;font-size:12pt !important;'
                            'font-family:&quot;HYHeadLine-Medium&quot;,serif !important;"',
                roman_body, count=1
            )
            nxt_raw = info[nxt]['raw']
            nxt_body = get_body_inner(nxt_raw)
            merged = roman_body + "\n" + nxt_body.strip()
            merged_bodies[nxt] = nxt_raw.replace(nxt_body, merged)
            info[nxt]['kind'] = 'chapter'
            info[nxt]['roman_label'] = re.sub(r'\s+', '', re.sub('<[^>]+>', '', roman_body))
            drop_ids.add(sid)
        i += 1

    # ---- merge stray 'body' continuation files into the chapter right
    #      before them. Some chapters have a footnote (translator's note)
    #      attached directly to the title paragraph, which InDesign exports
    #      as its own short file; the actual sermon text then continues in a
    #      SEPARATE following file with no roman-numeral marker of its own,
    #      producing an unwanted page break right after the footnote. Any
    #      'body' file sitting between a chapter and the next roman/chapter
    #      is such a continuation and must be appended to that chapter. ----
    i = 0
    while i < len(ordered):
        sid = ordered[i]
        if info[sid]['kind'] == 'chapter' and sid not in drop_ids:
            j = i + 1
            while j < len(ordered) and info[ordered[j]]['kind'] == 'body':
                cont_sid = ordered[j]
                cur_raw = merged_bodies.get(sid, info[sid]['raw'])
                cur_body = get_body_inner(cur_raw)
                cont_body = get_body_inner(info[cont_sid]['raw'])
                # the continuation file may have its OWN footnotes whose
                # internal anchors/backlinks self-reference its own filename
                # (e.g. "...-35.xhtml#footnote-002") - once merged into the
                # chapter file those must point at the chapter's own filename
                # or they become dangling links (epubcheck RSC-007).
                own_href = info[cont_sid]['href']
                target_href = info[sid]['href']
                if own_href != target_href:
                    cont_body = cont_body.replace(quote(own_href), quote(target_href))
                    cont_body = cont_body.replace(own_href, target_href)
                merged = cur_body.rstrip() + "\n" + cont_body.strip()
                merged_bodies[sid] = cur_raw.replace(cur_body, merged)
                info[sid]['text'] = info[sid]['text'] + ' ' + info[cont_sid]['text']
                drop_ids.add(cont_sid)
                j += 1
            i = j
        else:
            i += 1

    # ---- de-dup: a printed TOC-page dump sometimes lands as a SECOND (or
    #      later) "roman numeral only" file that pairs up with whatever odd
    #      fragment follows it, producing a fake duplicate "chapter" with
    #      near-zero content. Drop ONLY when the merged content is itself
    #      junk-sized - some source documents genuinely mislabel two
    #      consecutive real chapters with the same roman numeral (observed:
    #      "시편44" has two substantial chapters both labelled "V"), and a
    #      real chapter must never be dropped just because its label repeats. ----
    JUNK_DUP_MAX_LEN = 500
    seen_roman = set()
    for sid in ordered:
        if info[sid].get('kind') == 'chapter' and sid not in drop_ids:
            label = info[sid].get('roman_label', '')
            body_len = len(info[sid]['text'])
            if label and label in seen_roman:
                if body_len < JUNK_DUP_MAX_LEN:
                    drop_ids.add(sid)
                # else: substantial content despite duplicate label - keep it,
                # just leave the label as-is (nav will show the repeated roman).
            elif label:
                seen_roman.add(label)

    # ---- drop blanks, toc_entry, toc_heading, roman(consumed) ----
    DROP_KINDS = {'blank', 'toc_entry', 'toc_heading', 'roman', 'toc_dump'}
    front_order_score = {'publisher': 0, 'fm_title': 1, 'colophon': 2, 'english_title': 3}
    front_items = [s for s in ordered if info[s]['kind'] in front_order_score and s not in drop_ids]
    front_items.sort(key=lambda s: front_order_score[info[s]['kind']])

    kept = [s for s in ordered if s not in drop_ids and info[s]['kind'] not in DROP_KINDS and s not in front_items]

    # find insertion point: right before the first 'chapter' or, failing that,
    # right before the first substantial 'body' file (the intro essay)
    insert_at = 0
    for idx, s in enumerate(kept):
        if info[s]['kind'] in ('chapter', 'body') and len(info[s]['text']) > 80:
            insert_at = idx
            break
    new_order = kept[:insert_at] + front_items + kept[insert_at:]

    # ---- build fresh manifest/spine, applying merged bodies + doctype fix ----
    manifest_items = []
    spine_items = []
    write_data = {}
    used_hrefs = set()

    cover_href = href_by_id.get('cover') or 'cover.xhtml'
    if 'OEBPS/' + cover_href in names:
        manifest_items.append(f'<item id="cover" href="{cover_href}" media-type="application/xhtml+xml" />')
        spine_items.append('cover')
        write_data[cover_href] = fix_doctype(zin.read('OEBPS/' + cover_href).decode('utf-8'))

    chapter_titles = []  # (sid, title_text) in final order, for nav
    for sid in new_order:
        href = info[sid]['href']
        raw = merged_bodies.get(sid, info[sid]['raw'])
        raw = fix_doctype(raw)
        write_data[href] = raw
        manifest_items.append(f'<item id="{sid}" href="{href}" media-type="application/xhtml+xml" />')
        spine_items.append(sid)
        if info[sid]['kind'] == 'chapter':
            m = re.search(r'<title>([^<]*)</title>', raw)
            title_txt = m.group(1) if m else info[sid]['text'][:60]
            roman = info[sid].get('roman_label', '')
            chapter_titles.append((sid, href, f'{roman} {title_txt}'.strip()))

    # ---- sub-heading anchors (_-스타일) within chapters, for nested nav ----
    chapter_subheads = {}
    for sid, href, _ in chapter_titles:
        raw = write_data[href]
        subheads = []
        counter = 0
        def add_anchor(m, sid=sid):
            nonlocal counter
            counter += 1
            attrs, inner = m.group(1), m.group(2)
            text = re.sub('<[^>]+>', '', inner).strip()
            if 'id=' not in attrs:
                aid = f"sub-{sid}-{counter}"
                attrs = f' id="{aid}"' + attrs
            else:
                aid = re.search(r'id="([^"]+)"', attrs).group(1)
            subheads.append((aid, text))
            return f'<p{attrs}>{inner}</p>'
        new_raw = re.sub(r'<p([^>]*class="[^"]*_-스타일[^"]*"[^>]*)>(.*?)</p>', add_anchor, raw, flags=re.DOTALL)
        write_data[href] = new_raw
        chapter_subheads[sid] = subheads

    # ---- fonts/images manifest (carry over unchanged) + css ----
    font_img_items = re.findall(r'<item id="[^"]*"[^>]*href="(?:font|image)/[^"]*"[^>]*/>', opf_text)
    manifest_items.extend(font_img_items)
    has_css = any('css/idGeneratedStyles.css' in v for v in href_by_id.values()) or 'OEBPS/css/idGeneratedStyles.css' in names
    css_text = zin.read('OEBPS/css/idGeneratedStyles.css').decode('utf-8') if 'OEBPS/css/idGeneratedStyles.css' in names else ''
    manifest_items.append('<item id="css" href="css/idGeneratedStyles.css" media-type="text/css" />')
    manifest_items.append('<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml" />')
    manifest_items.append('<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav" />')

    # ---- cover image fix ----
    cover_bytes = None
    cover_meta_id = None
    if cover_href in write_data:
        ct = write_data[cover_href]
        if 'src="image/"' in ct and cover_jpg_path and os.path.exists(cover_jpg_path):
            write_data[cover_href] = ct.replace('src="image/"', 'src="image/cover.jpg"')
            with open(cover_jpg_path, 'rb') as f:
                cover_bytes = f.read()
            manifest_items.insert(0, '<item id="cover-img-fixed" href="image/cover.jpg" media-type="image/jpeg" properties="cover-image" />')
            cover_meta_id = 'cover-img-fixed'
        else:
            m_cov = re.search(r'<meta name="cover" content="([^"]+)"', opf_text)
            if m_cov:
                cover_meta_id = m_cov.group(1)

    # ---- CSS: font/size spec + drop subhead bg ----
    css_text = re.sub(r'(\._-스타일\s*\{[^}]*)background-color:#d3edfb;', r'\1', css_text)
    css_text += (
        '\n.장-제목, .장-제목 span { font-family:"Adobe Myungjo Std M", serif !important; font-size:12pt !important; color:#000000 !important; }\n'
        '._-스타일, ._-스타일 span { font-family:"KoPubWorldDotum Bold", sans-serif !important; font-size:11pt !important; color:#000000 !important; background-color:transparent !important; }\n'
        '.본문, .본문 span { font-family:"SeoulHangang M", serif !important; font-size:10pt !important; color:#000000 !important; }\n'
        '.본문-줄이기, .본문-줄이기 span, .본문-간격-축소, .본문-간격-축소 span { font-family:"SeoulHangang M", serif !important; font-size:10pt !important; color:#000000 !important; }\n'
        '.인용-및-성경구절, .인용-및-성경구절 span, .인용-싯구, .인용-싯구 span, .인용-간격-축소, .인용-간격-축소 span'
        ' { font-family:"SeoulHangang B", serif !important; font-style:italic !important; font-size:9pt !important; color:#0c3388 !important; }\n'
        '.chapter-roman { text-align:center; text-indent:0; font-size:12pt !important; font-family:"HYHeadLine-Medium", serif !important; margin-left:0; margin-right:0; }\n'
    )

    # ---- nav.xhtml + toc.ncx ----
    play_order = 0
    ncx_parts, li_parts = [], []
    def add_nav(label, href, anchor=None):
        nonlocal play_order
        play_order += 1
        src = quote(href) + (f"#{quote(anchor)}" if anchor else "")
        ncx_parts.append((play_order, label, src))
        return src

    for s in front_items:
        label = {'publisher': '출판사 소개', 'fm_title': '내지 한글표지', 'colophon': '판권', 'english_title': '내지 영문 표지'}[info[s]['kind']]
        add_nav(label, info[s]['href'])
        li_parts.append(f'<li><a href="{quote(info[s]["href"])}">{label}</a></li>')

    for sid, href, title in chapter_titles:
        subheads = chapter_subheads.get(sid, [])
        add_nav(title, href)
        sub_li = "".join(f'<li><a href="{quote(href)}#{quote(aid)}">{lbl}</a></li>' for aid, lbl in subheads)
        li_parts.append(f'<li><a href="{quote(href)}">{title}</a>' + (f'<ol>{sub_li}</ol>' if sub_li else '') + '</li>')
        for aid, lbl in subheads:
            play_order += 1
            ncx_parts.append((play_order, lbl, f'{quote(href)}#{quote(aid)}', sid))

    # rebuild ncx with proper nesting (chapter navPoint wraps its subhead navPoints)
    ncx_nav_xml = []
    pi = 0
    for s in front_items:
        pi += 1
        label = {'publisher': '출판사 소개', 'fm_title': '내지 한글표지', 'colophon': '판권', 'english_title': '내지 영문 표지'}[info[s]['kind']]
        ncx_nav_xml.append(f'<navPoint id="navpoint{pi}" playOrder="{pi}"><navLabel><text>{label}</text></navLabel><content src="{quote(info[s]["href"])}" /></navPoint>')
    for sid, href, title in chapter_titles:
        pi += 1
        entry = f'<navPoint id="navpoint{pi}" playOrder="{pi}"><navLabel><text>{title}</text></navLabel><content src="{quote(href)}" />'
        for aid, lbl in chapter_subheads.get(sid, []):
            pi += 1
            entry += f'<navPoint id="navpoint{pi}" playOrder="{pi}"><navLabel><text>{lbl}</text></navLabel><content src="{quote(href)}#{quote(aid)}" /></navPoint>'
        entry += '</navPoint>'
        ncx_nav_xml.append(entry)

    ncx = ('<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n'
           '<!DOCTYPE ncx PUBLIC "-//NISO//DTD ncx 2005-1//EN" "http://www.daisy.org/z3986/2005/ncx-2005-1.dtd">\n'
           '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">\n'
           '<head><meta name="dtb:depth" content="2" /></head>\n'
           f'<docTitle><text>{correct_title}</text></docTitle>\n'
           '<navMap>\n' + "\n".join(ncx_nav_xml) + '\n</navMap>\n</ncx>\n')

    nav_xhtml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE html>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="ko-KR" lang="ko-KR">\n'
        '<head><title>목차</title><link href="css/idGeneratedStyles.css" rel="stylesheet" type="text/css" /></head>\n<body>\n'
        '<nav epub:type="toc" id="toc"><h1>목차</h1><ol>\n' + "\n".join(li_parts) + '\n</ol></nav>\n</body>\n</html>\n'
    )

    # ---- fonts: read+deobfuscate (if encrypted), identifier for key from ORIGINAL opf ----
    m_id = re.search(r'<dc:identifier[^>]*>([^<]*)</dc:identifier>', opf_text)
    identifier_text = m_id.group(1) if m_id else ""
    has_encryption = 'META-INF/encryption.xml' in names
    new_font_bytes = {}
    if has_encryption:
        enc_text = zin.read('META-INF/encryption.xml').decode('utf-8')
        font_refs = re.findall(r'CipherReference URI="([^"]+)"', enc_text)
        key = idpf_key(identifier_text)
        for ref in font_refs:
            zpath = unquote(ref)
            if zpath not in names:
                cands = [n for n in names if n.endswith(os.path.basename(zpath))]
                if len(cands) == 1:
                    zpath = cands[0]
                else:
                    continue
            raw = zin.read(zpath)
            fixed = deobfuscate(raw, key)
            if looks_like_font(fixed):
                new_font_bytes[zpath] = fixed

    import datetime
    modified_ts = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

    opf = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<package version="3.0" xmlns="http://www.idpf.org/2007/opf" unique-identifier="bookid" xml:lang="ko-KR">
\t<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
\t\t{f'<meta name="cover" content="{cover_meta_id}" />' if cover_meta_id else ''}
\t\t<meta property="dcterms:modified">{modified_ts}</meta>
\t\t<dc:title>{correct_title}</dc:title>
\t\t<dc:language>{lang}</dc:language>
\t\t<dc:identifier id="bookid">{identifier_text}</dc:identifier>
\t\t<dc:identifier>urn:isbn:{isbn13}</dc:identifier>
\t</metadata>
\t<manifest>
\t\t{chr(10).join(manifest_items)}
\t</manifest>
\t<spine toc="ncx">
\t\t{chr(10).join(f'<itemref idref="{s}" />' for s in spine_items)}
\t</spine>
</package>
'''

    tmp_path = out_path + '.tmp'
    zout = zipfile.ZipFile(tmp_path, 'w')
    for item in zin.infolist():
        fn = item.filename
        if fn == 'mimetype':
            zout.writestr(item, zin.read(fn), compress_type=zipfile.ZIP_STORED)
            continue
        if fn == 'META-INF/encryption.xml':
            continue
        if fn.startswith('META-INF/'):
            zout.writestr(fn, zin.read(fn))
            continue
        if fn.startswith('OEBPS/font/') and fn in new_font_bytes:
            zout.writestr(fn, new_font_bytes[fn])
            continue
        if fn.startswith('OEBPS/font/') or fn.startswith('OEBPS/image/'):
            zout.writestr(fn, zin.read(fn))
            continue
    zout.writestr('OEBPS/content.opf', opf)
    zout.writestr('OEBPS/toc.ncx', ncx)
    zout.writestr('OEBPS/nav.xhtml', nav_xhtml)
    zout.writestr('OEBPS/css/idGeneratedStyles.css', css_text)
    for href, data in write_data.items():
        zout.writestr(f'OEBPS/{href}', data.encode('utf-8') if isinstance(data, str) else data)
    if cover_bytes:
        zout.writestr('OEBPS/image/cover.jpg', cover_bytes)
    zout.close()
    zin.close()
    os.replace(tmp_path, out_path)
    return {
        'chapters': len(chapter_titles),
        'subheads': sum(len(v) for v in chapter_subheads.values()),
        'front_items': [info[s]['kind'] for s in front_items],
        'dropped': len(drop_ids) + sum(1 for s in ordered if info[s]['kind'] in DROP_KINDS),
    }
