# -*- coding: utf-8 -*-
"""Build the final, fully-restructured reflow EPUB from the v7 InDesign
native export (TOC-style-fixed, spine-reordered). This is the complete,
owner-approved structure:

  cover -> Korean cover image -> 출판사소개 -> 내지한글표지 -> 판권 ->
  내지영문표지 -> 스펄전목사님소개 -> (story1 title repeat) -> 서문 ->
  10 chapters (roman+title merged, sub-heading "1 스타일" anchored for
  nested TOC) -> 뒤표지(image)

No blank filler pages, no printed TOC page (nav-only), extra CSS spacing
between 장-제목/인용-및-성경구절/본문/1-스타일(sub-heading).
"""
import zipfile, re, os
from urllib.parse import quote

SRC = r"C:\Users\a\.cys\claude\jobs\8442bc1d\tmp\test_reflow_v7.epub"
OUT = r"C:\Users\a\.cys\claude\jobs\8442bc1d\tmp\test_reflow_v17.epub"
BASE = "테스트복사본"
ISBN13 = "9791124043264"

CHAPTERS = [
    (12, 13, '만물을 새롭게 하시는 그리스도(Christ the Maker of All Things New)'),
    (18, 19, '그리스도: 많은 사람의 넘어짐과 일어섬(Christ-The Fall and Rise of Many)'),
    (20, 21, '죽음과 지옥의 열쇠를 가지신 그리스도(Christ with the Keys of Death and Hell)'),
    (24, 25, '그리스도와 나(Christus Et Ego)'),
    (30, 31, '자신의 아름다움 가운데 계신 왕(The King in His Beauty)'),
    (36, 37, '그리스도의 헤아릴 수 없는 풍성함(The Unsearchable Riches of Christ)'),
    (38, 39, '영광의 왕의 승리의 입성(A Triumphal Entrance)'),
    (44, 45, '그리스도의 공로를 근거로(For Christ\u2019s Sake)'),
    (50, 51, '그리스도를 대적한 온 군대(The Whole Band Against Christ)'),
    (52, 53, '온전하신 그리스도를 먹음(Feeding on a Whole Christ)'),
]

PAGE_HEAD = (
    '<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n'
    '<!DOCTYPE html>\n'
    '<html xmlns="http://www.w3.org/1999/xhtml">\n'
    '\t<head>\n\t\t<title>{title}</title>\n'
    '\t\t<link href="css/idGeneratedStyles.css" rel="stylesheet" type="text/css" />\n'
    '\t</head>\n\t<body id="{fid}">\n{body}\n\t</body>\n</html>\n'
)

def page(fid, title, body):
    return PAGE_HEAD.format(title=title, fid=fid, body=body)

def get_body_inner(xhtml_text):
    return re.search(r'<body[^>]*>(.*)</body>', xhtml_text, re.DOTALL).group(1)

DOCTYPE_RE = re.compile(r'<!DOCTYPE html PUBLIC "[^"]*"(\s*"[^"]*")?>')
def fix_doctype(xhtml_text):
    return DOCTYPE_RE.sub('<!DOCTYPE html>', xhtml_text)

def main():
    zin = zipfile.ZipFile(SRC, 'r')
    def read(n):
        return zin.read(f"OEBPS/{BASE}-{n}.xhtml" if n else f"OEBPS/{BASE}.xhtml").decode('utf-8')

    d53 = read(53)
    d54 = read(54)
    d55 = read(55)
    d73 = read(73)
    d2 = read(2)
    d8 = read(8)

    # ---- extract front/back matter fragments ----
    m = re.search(r'<div id="_idContainer002"[^>]*>.*?</div>', d53, re.DOTALL)
    publisher_block = m.group(0)
    d53 = d53[:m.start()] + d53[m.end():]  # strip it from chapter 10 so it isn't duplicated there

    title_heading = re.search(r'<div class="_idGenObjectStyleOverride-1">\s*<p[^>]*class="장-제목"[^>]*>.*?</p>\s*</div>', d54, re.DOTALL).group(0)
    author_lines = re.search(r'<div class="_idGenObjectStyleOverride-1">.*?</div>', d55, re.DOTALL).group(0)
    colophon_block = re.search(r'<div id="_idContainer004"[^>]*>.*?</div>', d55, re.DOTALL).group(0)
    english_block = re.search(r'<div id="_idContainer005"[^>]*>.*?</div>', d55, re.DOTALL).group(0)

    bio_block = re.search(r'<div id="_idContainer010"[^>]*>.*?</div>', d73, re.DOTALL).group(0)
    backcover_img = re.search(r'<div class="_idGenObjectLayout-1">\s*<div id="_idContainer011">.*?</div>\s*</div>', d73, re.DOTALL).group(0)

    # ---- build new front-matter files ----
    files = {}  # spine_id -> (title, html_text)
    files['fm1-publisher'] = ('출판사 소개', page('fm1-publisher', '출판사 소개', '\t\t' + publisher_block))
    files['fm2-titlepage'] = ('내지 한글표지', page('fm2-titlepage', '내지 한글표지', '\t\t' + title_heading + '\n' + author_lines))
    files['fm3-colophon'] = ('판권', page('fm3-colophon', '판권', '\t\t' + colophon_block))
    files['fm4-english'] = ('내지 영문 표지', page('fm4-english', '내지 영문 표지', '\t\t' + english_block))
    files['fm5-spurgeon'] = ('스펄전 목사님 소개', page('fm5-spurgeon', '스펄전 목사님 소개', '\t\t' + bio_block))
    files['backcover'] = ('뒤표지', page('backcover', '뒤표지', '\t\t' + backcover_img))

    # story1's opening paragraph duplicates fm2-titlepage (title+author again) -
    # drop it as a separate page, keep only its non-duplicate blank-line spacer
    # dropped; intro essay starts the reading flow directly after front matter.
    files['intro'] = ('스펄전(Charles Haddon Spurgeon)에게 배우는 위대한 복음 시리즈를 출간하면서', fix_doctype(d8))

    # ---- chapters: merge roman + content, collect sub-heading anchors ----
    chapter_subheads = {}  # chap_key -> [(anchor_id, label), ...]
    for i, (roman_n, chap_n, chap_title) in enumerate(CHAPTERS, start=1):
        roman_text = read(roman_n)
        chap_text = d53 if chap_n == 53 else read(chap_n)
        roman_body = get_body_inner(roman_text).strip()
        chap_body = get_body_inner(chap_text)

        # add id anchors to sub-heading paragraphs (class contains _-스타일) that lack one
        subheads = []
        counter = 0
        def add_anchor(m):
            nonlocal counter
            counter += 1
            attrs = m.group(1)
            inner = m.group(2)
            text = re.sub('<[^>]+>', '', inner).strip()
            if 'id=' not in attrs:
                aid = f"sub-ch{i}-{counter}"
                attrs = f' id="{aid}"' + attrs
            else:
                aid = re.search(r'id="([^"]+)"', attrs).group(1)
            subheads.append((aid, text))
            return f'<p{attrs}>{inner}</p>'

        new_chap_body = re.sub(
            r'<p([^>]*class="[^"]*_-스타일[^"]*"[^>]*)>(.*?)</p>',
            add_anchor, chap_body, flags=re.DOTALL
        )
        chapter_subheads[f'ch{i}'] = subheads

        roman_body = re.sub(
            r'(<p\b)([^>]*class=")([^"]*)(")',
            lambda m: m.group(1) + m.group(2) + m.group(3) + ' chapter-roman' + m.group(4)
                      + ' style="text-align:center !important;text-indent:0 !important;'
                        'margin-left:0 !important;margin-right:0 !important;font-size:12pt !important;'
                        'font-family:&quot;HYHeadLine-Medium&quot;,serif !important;"',
            roman_body, count=1
        )
        merged_body = roman_body + "\n" + new_chap_body.strip()
        new_text = fix_doctype(chap_text.replace(chap_body, merged_body))
        files[f'ch{i}'] = (chap_title, new_text)

    zin.close()

    # ---- CSS: widen spacing for 장-제목 / 인용-및-성경구절 / 본문 / _-스타일 ----
    zin2 = zipfile.ZipFile(SRC, 'r')
    css = zin2.read('OEBPS/css/idGeneratedStyles.css').decode('utf-8')
    zin2.close()

    def bump_margin(css_text, cls, top=None, bottom=None):
        def repl(m):
            block = m.group(0)
            if top is not None:
                block = re.sub(r'margin-top:[^;]+;', f'margin-top:{top};', block)
            if bottom is not None:
                block = re.sub(r'margin-bottom:[^;]+;', f'margin-bottom:{bottom};', block)
            return block
        return re.sub(r'\.' + re.escape(cls) + r'\s*\{[^}]*\}', repl, css_text)

    css = bump_margin(css, '장-제목', top='2em', bottom='0.8em')
    css = bump_margin(css, '인용-및-성경구절', top='1em', bottom='1em')
    css = bump_margin(css, '본문', top='0.6em', bottom='0.6em')
    css = bump_margin(css, '_-스타일', top='1.5em', bottom='0.6em')

    # The visible text of every paragraph style is wrapped in InDesign's own
    # <span class="CharOverride-N"> which sets its own font-family and wins
    # over a plain .장-제목 rule (equal specificity, later in source). Force
    # genuinely distinct embedded typefaces with !important so every style
    # is visually unmistakable regardless of nested CharOverride spans:
    #   장-제목(title)=Myungjo serif, 소제목(_-스타일)=KoPub Bold gothic,
    #   본문(body)=SeoulHangang Medium, 인용구=SeoulHangang Bold + italic.
    # drop the light-blue highlight background on sub-headings - it read as
    # a stray "blue" style on what the reader expects to be plain body text
    css = re.sub(
        r'(\._-스타일\s*\{[^}]*)background-color:#d3edfb;',
        r'\1',
        css
    )
    css += (
        '\n.장-제목, .장-제목 span { font-family:"Adobe Myungjo Std M", serif !important; font-size:12pt !important; color:#000000 !important; }\n'
        '._-스타일, ._-스타일 span { font-family:"KoPubWorldDotum Bold", sans-serif !important; font-size:11pt !important; color:#000000 !important; background-color:transparent !important; }\n'
        '.본문, .본문 span { font-family:"SeoulHangang M", serif !important; font-size:10pt !important; color:#000000 !important; }\n'
        '.본문-줄이기, .본문-줄이기 span { font-family:"SeoulHangang M", serif !important; font-size:10pt !important; color:#000000 !important; }\n'
        '.인용-및-성경구절, .인용-및-성경구절 span, .인용-싯구, .인용-싯구 span { font-family:"SeoulHangang B", serif !important; font-style:italic !important; font-size:9pt !important; color:#0c3388 !important; }\n'
    )
    css += (
        '\n.chapter-roman {\n'
        '\ttext-align:center;\n'
        '\ttext-indent:0;\n'
        '\tfont-size:12pt !important;\n'
        '\tfont-family:"HYHeadLine-Medium", serif !important;\n'
        '\tmargin-left:0;\n'
        '\tmargin-right:0;\n'
        '}\n'
    )

    # ---- assemble spine order ----
    spine_order = ['cover', 'cover-img',
                    'fm1-publisher', 'fm2-titlepage', 'fm3-colophon', 'fm4-english', 'fm5-spurgeon',
                    'intro'] + [f'ch{i}' for i in range(1, 11)] + ['backcover']

    # ---- write output epub ----
    zin3 = zipfile.ZipFile(SRC, 'r')
    zout = zipfile.ZipFile(OUT, 'w')

    # copy all non-structural assets (fonts, images, mimetype, container.xml) unchanged
    keep_prefixes = ('mimetype', 'META-INF/', 'OEBPS/font/', 'OEBPS/image/')
    for item in zin3.infolist():
        if item.filename.startswith(keep_prefixes):
            data = zin3.read(item.filename)
            if item.filename == 'mimetype':
                zout.writestr(item, data, compress_type=zipfile.ZIP_STORED)
            else:
                ni = zipfile.ZipInfo(item.filename, date_time=item.date_time)
                ni.compress_type = item.compress_type
                ni.external_attr = item.external_attr
                zout.writestr(ni, data)

    zout.writestr('OEBPS/css/idGeneratedStyles.css', css)
    zout.writestr('OEBPS/cover.xhtml', fix_doctype(zin3.read('OEBPS/cover.xhtml').decode('utf-8')).encode('utf-8'))
    zout.writestr(f'OEBPS/{BASE}.xhtml', fix_doctype(zin3.read(f'OEBPS/{BASE}.xhtml').decode('utf-8')).encode('utf-8'))  # cover-img file (n=0)
    zin3.close()

    for sid, (label, content) in files.items():
        if sid == 'story-open':
            fname = f'OEBPS/{BASE}-2.xhtml'
        elif sid == 'intro':
            fname = f'OEBPS/{BASE}-8.xhtml'
        else:
            fname = f'OEBPS/{sid}.xhtml'
        data = content if isinstance(content, bytes) else content.encode('utf-8')
        zout.writestr(fname, data)

    id_to_href = {
        'cover': 'cover.xhtml',
        'cover-img': f'{BASE}.xhtml',
        'intro': f'{BASE}-8.xhtml',
    }
    for sid in files:
        if sid not in id_to_href:
            id_to_href[sid] = f'{sid}.xhtml'

    manifest_items = []
    for sid, href in id_to_href.items():
        mt = 'application/xhtml+xml'
        manifest_items.append(f'<item id="{sid}" href="{href}" media-type="{mt}" />')
    # fonts/images manifest entries (reuse original)
    zin4 = zipfile.ZipFile(SRC, 'r')
    orig_opf = zin4.read('OEBPS/content.opf').decode('utf-8')
    zin4.close()
    font_img_items = re.findall(r'<item id="[^"]*"[^>]*href="(?:font|image)/[^"]*"[^>]*/>', orig_opf)
    manifest_items.extend(font_img_items)
    ncx_item = '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml" />'
    manifest_items.append(ncx_item)
    nav_item = '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav" />'
    manifest_items.append(nav_item)
    css_item = '<item id="css" href="css/idGeneratedStyles.css" media-type="text/css" />'
    manifest_items.append(css_item)

    spine_xml = "\n\t\t".join(f'<itemref idref="{sid}" />' for sid in spine_order)

    import datetime
    modified_ts = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')

    opf = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<package version="3.0" xmlns="http://www.idpf.org/2007/opf" unique-identifier="bookid" xml:lang="ko-KR">
\t<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
\t\t<meta name="cover" content="cover-img-fixed" />
\t\t<meta property="dcterms:modified">{modified_ts}</meta>
\t\t<dc:title>1 예수 그리스도를 아는 지식</dc:title>
\t\t<dc:language>ko</dc:language>
\t\t<dc:identifier id="bookid">urn:uuid:2888097a-1c27-4aff-a691-800336498a58</dc:identifier>
\t\t<dc:identifier>urn:isbn:{ISBN13}</dc:identifier>
\t</metadata>
\t<manifest>
\t\t<item id="cover-img-fixed" href="image/cover.jpg" media-type="image/jpeg" properties="cover-image" />
\t\t{chr(10).join(manifest_items)}
\t</manifest>
\t<spine toc="ncx">
\t\t{spine_xml}
\t</spine>
</package>
'''
    zout.writestr('OEBPS/content.opf', opf)

    # ---- build one structured outline, then render BOTH toc.ncx (EPUB2 legacy)
    #      AND nav.xhtml (EPUB3 required nav doc) from it, so every reader -
    #      old or new - shows the real Korean labels instead of falling back
    #      to spine filenames (ch1, ch2...) when nav.xhtml is missing ----
    outline = [
        ('출판사 소개', 'fm1-publisher.xhtml', None, []),
        ('내지 한글표지', 'fm2-titlepage.xhtml', None, []),
        ('판권', 'fm3-colophon.xhtml', None, []),
        ('내지 영문 표지', 'fm4-english.xhtml', None, []),
        ('스펄전 목사님 소개', 'fm5-spurgeon.xhtml', None, []),
        ('스펄전(Charles Haddon Spurgeon)에게 배우는 위대한 복음 시리즈를 출간하면서', f'{BASE}-8.xhtml', None, []),
    ]
    ROMAN = ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X']
    for i, (roman_n, chap_n, chap_title) in enumerate(CHAPTERS, start=1):
        subheads = chapter_subheads[f'ch{i}']
        outline.append((f'{ROMAN[i-1]} {chap_title}', f'ch{i}.xhtml', None, subheads))

    # ---- toc.ncx ----
    play_order = 0
    ncx_parts = []
    for label, href, anchor, children in outline:
        play_order += 1
        src = quote(href)
        entry = (f'<navPoint id="navpoint{play_order}" playOrder="{play_order}">'
                 f'<navLabel><text>{label}</text></navLabel>'
                 f'<content src="{src}" />')
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
           '<docTitle><text>1 예수 그리스도를 아는 지식</text></docTitle>\n'
           '<navMap>\n' + "\n".join(ncx_parts) + '\n</navMap>\n</ncx>\n')
    zout.writestr('OEBPS/toc.ncx', ncx)

    # ---- nav.xhtml (EPUB3 required navigation document) ----
    li_parts = []
    for label, href, anchor, children in outline:
        li = f'<li><a href="{quote(href)}">{label}</a>'
        if children:
            sub_li = "".join(
                f'<li><a href="{quote(href)}#{quote(aid)}">{sub_label}</a></li>'
                for aid, sub_label in children
            )
            li += f'<ol>{sub_li}</ol>'
        li += '</li>'
        li_parts.append(li)

    nav_xhtml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE html>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="ko-KR" lang="ko-KR">\n'
        '<head><title>목차</title><link href="css/idGeneratedStyles.css" rel="stylesheet" type="text/css" /></head>\n'
        '<body>\n'
        '<nav epub:type="toc" id="toc"><h1>목차</h1><ol>\n' + "\n".join(li_parts) + '\n</ol></nav>\n'
        '</body>\n</html>\n'
    )
    zout.writestr('OEBPS/nav.xhtml', nav_xhtml)

    zout.close()
    return {"chapters": len(CHAPTERS), "subhead_total": sum(len(v) for v in chapter_subheads.values())}

if __name__ == "__main__":
    print(main())
