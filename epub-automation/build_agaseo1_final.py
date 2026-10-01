# -*- coding: utf-8 -*-
import zipfile, re, os, sys
from urllib.parse import quote
sys.path.insert(0, r'C:\Users\a\install-jarvis\book-production\v5\com')

SRC = r"C:\Users\a\.cys\claude\jobs\8442bc1d\tmp\10book_raw\아가서1_raw6.epub"
OUT = r"C:\Users\a\.cys\claude\jobs\8442bc1d\tmp\10book_raw\아가서1_v2.epub"
BASE = "스펄전의_아가서의_복음이야기_1(273__ebook출판용)"
ISBN13 = "9791124736722"

CH_TITLES = [
    '포도주보다 나은 사랑(Better Than Wine)',
    '기뻐하며 기억함(Rejoicing and Remembering)',
    '그리스도의 사랑을 기억함(The Memory of Christ\u2019s Love)',
    '상쾌하게 하는 찬가(A Refreshing Canticle)',
    '지키지 못한 포도원-또는 소홀히 한 자신의 일(The Unkept Vineyard-Or, Personal Work Neglected)',
    '자기 낮춤과 자기 성찰(Self-Humbling and Self-Searching)',
    '예수님을 향한 사랑(Love to Jesus)',
    '사랑의 주님을 향한 교회의 사랑(The Church\u2019s Love to Her Loving Lord)',
    '선한 목자(The Good Shepherdess)',
    '향기로운 은혜들(Fragrant Graces)',
]
ROMAN = ['I','II','III','IV','V','VI','VII','VIII','IX','X']

def get_body_inner(t):
    return re.search(r'<body[^>]*>(.*)</body>', t, re.DOTALL).group(1)

def quote_href(href):
    # quote() on a raw "#" turns it into "%23" and breaks the fragment -
    # quote only the file-path part, leave an existing "#anchor" suffix as-is.
    path, sep, frag = href.partition('#')
    return quote(path) + sep + frag

def main():
    zin = zipfile.ZipFile(SRC, 'r')
    def read(suffix):
        return zin.read(f"OEBPS/{BASE}{suffix}.xhtml").decode('utf-8')

    base_text = read("")
    base_body = get_body_inner(base_text)

    # strip trailing bare "I" paragraph from base (belongs to chapter 1)
    m = re.search(r'<p[^>]*class="[^"]*장-제목[^"]*"[^>]*>(?:<span[^>]*><a[^>]*></a></span>)?I\s*</p>\s*$', base_body)
    if m:
        base_body_clean = base_body[:m.start()]
    else:
        base_body_clean = base_body
    base_text_clean = base_text.replace(base_body, base_body_clean)

    # ---- chapter files ----
    files = {}
    subheads_all = {}
    for i, title in enumerate(CH_TITLES, start=1):
        chap_text = read(f"-{i}")
        chap_body = get_body_inner(chap_text)
        subheads = []
        counter = 0
        def add_anchor(m, i=i):
            nonlocal counter
            counter += 1
            attrs, inner = m.group(1), m.group(2)
            text = re.sub('<[^>]+>', '', inner).strip()
            if 'id=' not in attrs:
                aid = f"sub-ch{i}-{counter}"
                attrs = f' id="{aid}"' + attrs
            else:
                aid = re.search(r'id="([^"]+)"', attrs).group(1)
            subheads.append((aid, text))
            return f'<p{attrs}>{inner}</p>'
        SUBHEAD_RE = re.compile('<p([^>]*class="[^"]*1-' + chr(0xc2a4) + chr(0xd0c0) + chr(0xc77c) + '[^"]*"[^>]*)>(.*?)</p>', re.DOTALL)
        new_body = SUBHEAD_RE.sub(add_anchor, chap_body)
        subheads_all[f'ch{i}'] = subheads
        new_text = chap_text.replace(chap_body, new_body)
        files[f'ch{i}'] = (title, new_text)

    # merge trailing "I" into ch1 start
    ch1_title, ch1_text = files['ch1']
    ch1_body = get_body_inner(ch1_text)
    files['ch1'] = (ch1_title, ch1_text)  # roman already implicit in style-merge; content itself already starts with title text, fine as-is

    # ---- extract front matter from ch10 tail ----
    ch10_title, ch10_text = files['ch10']
    ch10_body = get_body_inner(ch10_text)
    idx2 = ch10_body.find('<div id="_idContainer002"')
    assert idx2 != -1, "publisher marker not found"
    tail = ch10_body[idx2:]
    ch10_body_clean = ch10_body[:idx2]
    files['ch10'] = (ch10_title, ch10_text.replace(ch10_body, ch10_body_clean))

    def extract_div(html, div_id):
        m = re.search(r'<div id="' + div_id + r'"[^>]*>.*?</div>', html, re.DOTALL)
        return m.group(0) if m else ''

    publisher_block = extract_div(tail, '_idContainer002')
    titlepage_block = extract_div(tail, '_idContainer003')
    colophon_block = extract_div(tail, '_idContainer004')
    english_block = extract_div(tail, '_idContainer005')

    def page(fid, title, body):
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n'
            '<!DOCTYPE html>\n'
            '<html xmlns="http://www.w3.org/1999/xhtml">\n'
            f'\t<head>\n\t\t<title>{title}</title>\n'
            '\t\t<link href="css/idGeneratedStyles.css" rel="stylesheet" type="text/css" />\n'
            f'\t</head>\n\t<body id="{fid}">\n{body}\n\t</body>\n</html>\n'
        )

    files['fm1-publisher'] = ('출판사 소개', page('fm1-publisher', '출판사 소개', '\t\t' + publisher_block))
    files['fm2-titlepage'] = ('내지 한글표지', page('fm2-titlepage', '내지 한글표지', '\t\t' + titlepage_block))
    files['fm3-colophon'] = ('판권', page('fm3-colophon', '판권', '\t\t' + colophon_block))
    files['fm4-english'] = ('내지 영문 표지', page('fm4-english', '내지 영문 표지', '\t\t' + english_block))

    # backcover image from the printed-TOC file (-11), which we otherwise drop
    toc_print = read("-11")
    bc_m = re.search(r'<div class="_idGenObjectLayout-1">\s*<div id="_idContainer009">.*?</div>\s*</div>', toc_print, re.DOTALL)
    if bc_m:
        files['backcover'] = ('뒤표지', page('backcover', '뒤표지', '\t\t' + bc_m.group(0)))

    # ---- CSS ----
    css = zin.read('OEBPS/css/idGeneratedStyles.css').decode('utf-8')

    def bump_margin(css_text, cls, top=None, bottom=None):
        def repl(m):
            block = m.group(0)
            if top is not None:
                block = re.sub(r'margin-top:[^;]+;', f'margin-top:{top};', block)
            if bottom is not None:
                block = re.sub(r'margin-bottom:[^;]+;', f'margin-bottom:{bottom};', block)
            return block
        return re.sub(r'\.' + re.escape(cls) + r'\s*\{[^}]*\}', repl, css_text)

    for cls in ['장-제목', '마틴-루터의-갈라디아서-강의와-복음-V_장-제목']:
        css = bump_margin(css, cls, top='2em', bottom='0.8em')
    for cls in ['인용-및-성경구절', '마틴-루터의-갈라디아서-강의와-복음-V_인용-및-성경구절']:
        css = bump_margin(css, cls, top='1em', bottom='1em')
    for cls in ['본문', '마틴-루터의-갈라디아서-강의와-복음-V_본문']:
        css = bump_margin(css, cls, top='0.6em', bottom='0.6em')

    css += (
        '\n.장-제목, .장-제목 span, .마틴-루터의-갈라디아서-강의와-복음-V_장-제목, .마틴-루터의-갈라디아서-강의와-복음-V_장-제목 span'
        ' { font-family:"Adobe Myungjo Std M", serif !important; font-size:12pt !important; color:#000000 !important; }\n'
        '.마틴-루터의-갈라디아서-강의와-복음-V_1-\uc2a4\ud0c0\uc77c, .마틴-루터의-갈라디아서-강의와-복음-V_1-\uc2a4\ud0c0\uc77c span'
        ' { font-family:"KoPubWorldDotum Bold", sans-serif !important; font-size:11pt !important; color:#000000 !important; background-color:transparent !important; }\n'
        '.본문, .본문 span, .마틴-루터의-갈라디아서-강의와-복음-V_본문, .마틴-루터의-갈라디아서-강의와-복음-V_본문 span'
        ' { font-family:"SeoulHangang M", serif !important; font-size:10pt !important; color:#000000 !important; }\n'
        '.인용-및-성경구절, .인용-및-성경구절 span, .마틴-루터의-갈라디아서-강의와-복음-V_인용-및-성경구절, .마틴-루터의-갈라디아서-강의와-복음-V_인용-및-성경구절 span'
        ' { font-family:"SeoulHangang B", serif !important; font-style:italic !important; font-size:9pt !important; color:#0c3388 !important; }\n'
    )

    # ---- spine order ----
    spine_order = ['cover', 'fm0-title-intro', 'fm1-publisher', 'fm2-titlepage', 'fm3-colophon', 'fm4-english'] \
        + [f'ch{i}' for i in range(1, 11)]
    if 'backcover' in files:
        spine_order.append('backcover')

    # ---- write output ----
    zout = zipfile.ZipFile(OUT, 'w')
    keep_prefixes = ('mimetype', 'META-INF/', 'OEBPS/font/', 'OEBPS/image/')
    for item in zin.infolist():
        if item.filename.startswith(keep_prefixes):
            data = zin.read(item.filename)
            if item.filename == 'mimetype':
                zout.writestr(item, data, compress_type=zipfile.ZIP_STORED)
            else:
                ni = zipfile.ZipInfo(item.filename, date_time=item.date_time)
                ni.compress_type = item.compress_type
                ni.external_attr = item.external_attr
                zout.writestr(ni, data)
    zout.writestr('OEBPS/css/idGeneratedStyles.css', css)
    zout.writestr('OEBPS/cover.xhtml', zin.read('OEBPS/cover.xhtml'))
    zout.writestr(f'OEBPS/{BASE}.xhtml', base_text_clean.encode('utf-8'))

    # NOTE: this id used to be named 'cover-img' under the (wrong) assumption
    # it was just a throwaway duplicate of the cover image. It is not - it is
    # the real "내지 한글표지 + 저자소개" page (title/author/translator block
    # followed by the full Spurgeon biography essay, ~8600 chars). It was
    # missing from the nav outline entirely, which is why the owner reported
    # "저자소개가 빠졌다" (2026-10-01) even though the text was present in the
    # spine - a reader had no bookmark to find it. Renamed + added to outline.
    id_to_href = {'cover': 'cover.xhtml', 'fm0-title-intro': f'{BASE}.xhtml'}
    for sid in files:
        id_to_href[sid] = f'{sid}.xhtml' if not sid.startswith('ch') else f'{sid}.xhtml'
    for sid, (label, content) in files.items():
        fname = f'OEBPS/{sid}.xhtml'
        data = content.encode('utf-8')
        zout.writestr(fname, data)

    manifest_items = [f'<item id="{sid}" href="{href}" media-type="application/xhtml+xml" />' for sid, href in id_to_href.items()]
    orig_opf = zin.read('OEBPS/content.opf').decode('utf-8')
    font_img_items = re.findall(r'<item id="[^"]*"[^>]*href="(?:font|image)/[^"]*"[^>]*/>', orig_opf)
    manifest_items.extend(font_img_items)
    manifest_items.append('<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml" />')
    manifest_items.append('<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav" />')
    manifest_items.append('<item id="css" href="css/idGeneratedStyles.css" media-type="text/css" />')

    spine_xml = "\n\t\t".join(f'<itemref idref="{sid}" />' for sid in spine_order)

    import datetime
    modified_ts = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

    opf = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<package version="3.0" xmlns="http://www.idpf.org/2007/opf" unique-identifier="bookid" xml:lang="ko-KR">
\t<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
\t\t<meta name="cover" content="x1.png" />
\t\t<meta property="dcterms:modified">{modified_ts}</meta>
\t\t<dc:title>스펄전의 아가서의 복음이야기 1</dc:title>
\t\t<dc:language>ko</dc:language>
\t\t<dc:identifier id="bookid">urn:uuid:29d919dd-24f5-4384-be78-b447c9dc299b</dc:identifier>
\t\t<dc:identifier>urn:isbn:{ISBN13}</dc:identifier>
\t</metadata>
\t<manifest>
\t\t{chr(10).join(manifest_items)}
\t</manifest>
\t<spine toc="ncx">
\t\t{spine_xml}
\t</spine>
</package>
'''
    zout.writestr('OEBPS/content.opf', opf)

    # ---- nav + ncx ----
    outline = [
        ('내지 한글표지', f'{BASE}.xhtml', []),
        ('저자 소개', f'{BASE}.xhtml#_idTextAnchor000', []),
        ('출판사 소개', 'fm1-publisher.xhtml', []),
        ('내지 한글표지', 'fm2-titlepage.xhtml', []),
        ('판권', 'fm3-colophon.xhtml', []),
        ('내지 영문 표지', 'fm4-english.xhtml', []),
    ]
    for i, title in enumerate(CH_TITLES, start=1):
        outline.append((f'{ROMAN[i-1]} {title}', f'ch{i}.xhtml', subheads_all[f'ch{i}']))

    play_order = 0
    ncx_parts = []
    for label, href, children in outline:
        play_order += 1
        entry = (f'<navPoint id="navpoint{play_order}" playOrder="{play_order}">'
                 f'<navLabel><text>{label}</text></navLabel>'
                 f'<content src="{quote_href(href)}" />')
        for aid, sub_label in children:
            play_order += 1
            entry += (f'<navPoint id="navpoint{play_order}" playOrder="{play_order}">'
                       f'<navLabel><text>{sub_label}</text></navLabel>'
                       f'<content src="{quote(href)}#{quote(aid)}" /></navPoint>')
        entry += '</navPoint>'
        ncx_parts.append(entry)

    ncx = ('<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n'
           '<!DOCTYPE ncx PUBLIC "-//NISO//DTD ncx 2005-1//EN" "http://www.daisy.org/z3986/2005/ncx-2005-1.dtd">\n'
           '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">\n'
           '<head><meta name="dtb:depth" content="2" /></head>\n'
           '<docTitle><text>스펄전의 아가서의 복음이야기 1</text></docTitle>\n'
           '<navMap>\n' + "\n".join(ncx_parts) + '\n</navMap>\n</ncx>\n')
    zout.writestr('OEBPS/toc.ncx', ncx)

    li_parts = []
    for label, href, children in outline:
        li = f'<li><a href="{quote_href(href)}">{label}</a>'
        if children:
            sub_li = "".join(f'<li><a href="{quote(href)}#{quote(aid)}">{sub_label}</a></li>' for aid, sub_label in children)
            li += f'<ol>{sub_li}</ol>'
        li += '</li>'
        li_parts.append(li)
    nav_xhtml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE html>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="ko-KR" lang="ko-KR">\n'
        '<head><title>목차</title><link href="css/idGeneratedStyles.css" rel="stylesheet" type="text/css" /></head>\n'
        '<body>\n<nav epub:type="toc" id="toc"><h1>목차</h1><ol>\n' + "\n".join(li_parts) + '\n</ol></nav>\n</body>\n</html>\n'
    )
    zout.writestr('OEBPS/nav.xhtml', nav_xhtml)

    zin.close()
    zout.close()
    print("done", OUT)

if __name__ == "__main__":
    main()
