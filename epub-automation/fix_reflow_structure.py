# -*- coding: utf-8 -*-
"""Structural fixes on top of fix_reflow_spine_order.py output:
1) Merge bare-roman-numeral split files ("I", "II", ...) into the very next
   (real chapter title+content) file, so InDesign's split-by-style behavior
   doesn't create a separate, jarring page-turn between "I" and the title.
2) Split the tail file that mixes the last TOC entry with the author-bio
   back matter, keeping only the bio at the very end.
3) Regenerate toc.ncx from scratch: one clean navPoint per chapter (using
   the merged file + real title), plus navPoints for front-matter blocks
   (publisher blurb, title page, colophon, English cover) so they are
   reachable via navigation, not just present in spine.
"""
import zipfile, re, os
from urllib.parse import unquote, quote

def fn(base, n):
    return f"{base}.xhtml" if n == 0 else f"{base}-{n}.xhtml"

def get_body_inner(xhtml_text):
    m = re.search(r'<body[^>]*>(.*)</body>', xhtml_text, re.DOTALL)
    return m.group(1)

def get_title(xhtml_text):
    m = re.search(r'<title>([^<]*)</title>', xhtml_text)
    return m.group(1) if m else ""

def fix_structure(src_path, out_path, base_name,
                   roman_pairs,          # [(roman_file_n, chapter_file_n, chapter_title), ...]
                   tail_file_n,          # e.g. 73 - mixed toc-remnant + bio
                   tail_split_marker,    # literal text marking start of bio portion
                   toc_range,            # (start_n, end_n) - existing TOC block (after spine reorder)
                   front_nav_entries,    # [(file_n, label), ...] front matter items to add to nav
                   intro_file_n, intro_title,
                   title_page_file_n, title_page_title):
    zin = zipfile.ZipFile(src_path, 'r')
    names = zin.namelist()
    opf_name = [n for n in names if n.endswith('.opf')][0]
    opf_text = zin.read(opf_name).decode('utf-8')
    manifest = dict(re.findall(r'<item id="([^"]+)" href="([^"]+)"', opf_text))
    id_by_file = {}
    for iid, href in manifest.items():
        id_by_file[unquote(href)] = iid

    spine_ids = re.findall(r'<itemref idref="([^"]+)"', opf_text)
    itemref_tags = {m.group(1): m.group(0) for m in re.finditer(r'<itemref idref="([^"]+)"[^/]*/>', opf_text)}

    # ---- read all needed file contents ----
    contents = {}
    for n in set([r for r, c, t in roman_pairs] + [c for r, c, t in roman_pairs] + [tail_file_n]):
        contents[n] = zin.read(f"OEBPS/{fn(base_name, n)}").decode('utf-8')

    # ---- 1) merge roman + chapter ----
    merged_ids_to_drop = set()
    new_chapter_body = {}
    for roman_n, chap_n, chap_title in roman_pairs:
        roman_body = get_body_inner(contents[roman_n])
        chap_text = contents[chap_n]
        chap_body = get_body_inner(chap_text)
        merged = roman_body.strip() + "\n" + chap_body.strip()
        new_text = chap_text.replace(chap_body, merged)
        new_chapter_body[chap_n] = new_text
        merged_ids_to_drop.add(id_by_file[fn(base_name, roman_n)])

    # ---- 2) split tail file: drop the redundant last-TOC-entry fragment
    #      (its chapter is already represented by the real merged chapter file),
    #      keep only the genuine back-matter (author bio + back cover image) ----
    tail_text = contents[tail_file_n]
    tail_body = get_body_inner(tail_text)
    idx = tail_body.find(tail_split_marker)
    assert idx != -1, "tail split marker not found"
    bio_body = tail_body[idx:]
    bio_text = tail_text.replace(tail_body, bio_body)

    # ---- write updated OPF: drop merged roman ids from spine, keep order otherwise ----
    new_spine_ids = [s for s in spine_ids if s not in merged_ids_to_drop]
    new_spine_xml = "\n\t\t".join(itemref_tags[s] for s in new_spine_ids)
    new_opf = re.sub(
        r'(<spine[^>]*>)(.*?)(</spine>)',
        lambda m: m.group(1) + "\n\t\t" + new_spine_xml + "\n\t" + m.group(3),
        opf_text, flags=re.DOTALL
    )
    # remove manifest entries for dropped roman files too (optional cleanliness)
    for roman_n, chap_n, chap_title in roman_pairs:
        rid = id_by_file[fn(base_name, roman_n)]
        new_opf = re.sub(r'\s*<item id="' + re.escape(rid) + r'"[^/]*/>', '', new_opf)

    # ---- build new toc.ncx ----
    play_order = 0
    nav_points = []

    def add_nav(label, file_n, anchor=None):
        nonlocal play_order
        play_order += 1
        href = fn(base_name, file_n)
        src = quote(href) + (f"#{quote(anchor)}" if anchor else "")
        nav_points.append(
            f'<navPoint id="navpoint{play_order}" playOrder="{play_order}">'
            f'<navLabel><text>{label}</text></navLabel>'
            f'<content src="{src}" /></navPoint>'
        )

    for file_n, label in front_nav_entries:
        add_nav(label, file_n)
    add_nav(intro_title, intro_file_n)
    for roman_n, chap_n, chap_title in roman_pairs:
        add_nav(chap_title, chap_n)

    ncx = (
        '<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n'
        '<!DOCTYPE ncx PUBLIC "-//NISO//DTD ncx 2005-1//EN" "http://www.daisy.org/z3986/2005/ncx-2005-1.dtd">\n'
        '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">\n'
        '<head><meta name="dtb:depth" content="1" /></head>\n'
        f'<docTitle><text>{title_page_title}</text></docTitle>\n'
        '<navMap>\n' + "\n".join(nav_points) + '\n</navMap>\n</ncx>\n'
    )

    # ---- write output zip ----
    tmp_path = out_path + ".tmp"
    zout = zipfile.ZipFile(tmp_path, 'w')
    for item in zin.infolist():
        f_name = item.filename
        data = zin.read(f_name)
        if f_name == opf_name:
            data = new_opf.encode('utf-8')
        elif f_name == f"OEBPS/{fn(base_name, tail_file_n)}":
            data = bio_text.encode('utf-8')
        elif f_name.endswith('.ncx'):
            data = ncx.encode('utf-8')
        else:
            for chap_n, new_text in new_chapter_body.items():
                if f_name == f"OEBPS/{fn(base_name, chap_n)}":
                    data = new_text.encode('utf-8')
                    break
        # skip dropped roman files entirely
        dropped = any(f_name == f"OEBPS/{fn(base_name, rn)}" for rn, cn, ct in roman_pairs)
        if dropped:
            continue
        if f_name == 'mimetype':
            zout.writestr(item, data, compress_type=zipfile.ZIP_STORED)
        else:
            new_item = zipfile.ZipInfo(f_name, date_time=item.date_time)
            new_item.compress_type = item.compress_type
            new_item.external_attr = item.external_attr
            zout.writestr(new_item, data)
    zout.close()
    zin.close()
    os.replace(tmp_path, out_path)
    return {"merged": len(roman_pairs), "nav_points": play_order, "dropped_ids": list(merged_ids_to_drop)}
