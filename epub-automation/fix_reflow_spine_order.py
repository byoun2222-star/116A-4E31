# -*- coding: utf-8 -*-
"""Reorder spine (+ NCX/nav) of an InDesign-native split reflow EPUB.

InDesign's reflow exporter (even with ExportOrder=layout, BreakDocument=True,
TocStyleName set) still appends orphan/unthreaded stories (front-matter:
title page, colophon, English title page; and TOC) AFTER the fully-threaded
main story, instead of interleaving them at their correct physical position.
This script fixes reading order by moving those file groups to the right
spot in the OPF spine (content order only - no HTML content is altered).

Usage: identify, per book, the base filename (without .xhtml/-N suffix),
and the filename-number boundaries for front-matter and TOC blocks (found
by inspecting file contents once per book structure family).
"""
import zipfile, re, os

def reorder_spine(src_path, out_path, base_name,
                   front_matter_range, toc_range,
                   insert_front_before, insert_toc_before):
    """
    base_name: e.g. '테스트복사본' (filename stem InDesign used)
    front_matter_range: (start_n, end_n) inclusive, e.g. (54, 55)
    toc_range: (start_n, end_n) inclusive, e.g. (56, 72)
    insert_front_before: filename (e.g. '테스트복사본-8.xhtml') - front matter goes right before this
    insert_toc_before: filename (e.g. '테스트복사본-12.xhtml') - TOC goes right before this
    """
    def fn(n):
        return f"{base_name}.xhtml" if n == 0 else f"{base_name}-{n}.xhtml"

    zin = zipfile.ZipFile(src_path, 'r')
    opf_name = [n for n in zin.namelist() if n.endswith('.opf')][0]
    opf_text = zin.read(opf_name).decode('utf-8')

    spine_items = re.findall(r'<itemref idref="([^"]+)"[^/]*/>', opf_text)
    manifest = dict(re.findall(r'<item id="([^"]+)" href="([^"]+)"', opf_text))
    href_to_id = {v: k for k, v in manifest.items()}

    def idref_for_file(filename):
        href = filename  # hrefs are percent-encoded but manifest stores encoded too; match by unquoted compare
        for iid, h in manifest.items():
            from urllib.parse import unquote
            if unquote(h) == filename:
                return iid
        raise KeyError(filename)

    front_ids = [idref_for_file(fn(n)) for n in range(front_matter_range[0], front_matter_range[1] + 1)]
    toc_ids = [idref_for_file(fn(n)) for n in range(toc_range[0], toc_range[1] + 1)]
    insert_front_id = idref_for_file(insert_front_before)
    insert_toc_id = idref_for_file(insert_toc_before)

    remaining = [s for s in spine_items if s not in front_ids and s not in toc_ids]

    new_spine = []
    for s in remaining:
        if s == insert_front_id:
            new_spine.extend(front_ids)
        if s == insert_toc_id:
            new_spine.extend(toc_ids)
        new_spine.append(s)

    assert len(new_spine) == len(spine_items), f"{len(new_spine)} != {len(spine_items)}"
    assert set(new_spine) == set(spine_items)

    # rebuild spine section in OPF text (preserve each itemref's own attributes)
    itemref_tags = {}
    for m in re.finditer(r'<itemref idref="([^"]+)"[^/]*/>', opf_text):
        itemref_tags[m.group(1)] = m.group(0)

    new_spine_xml = "\n\t\t".join(itemref_tags[s] for s in new_spine)
    new_opf = re.sub(
        r'(<spine[^>]*>)(.*?)(</spine>)',
        lambda m: m.group(1) + "\n\t\t" + new_spine_xml + "\n\t" + m.group(3),
        opf_text, flags=re.DOTALL
    )

    zout = zipfile.ZipFile(out_path + '.tmp', 'w')
    for item in zin.infolist():
        data = zin.read(item.filename)
        if item.filename == opf_name:
            data = new_opf.encode('utf-8')
        if item.filename == 'mimetype':
            zout.writestr(item, data, compress_type=zipfile.ZIP_STORED)
        else:
            new_item = zipfile.ZipInfo(item.filename, date_time=item.date_time)
            new_item.compress_type = item.compress_type
            new_item.external_attr = item.external_attr
            zout.writestr(new_item, data)
    zout.close()
    zin.close()
    os.replace(out_path + '.tmp', out_path)
    return {"front_ids": front_ids, "toc_ids": toc_ids, "new_spine_len": len(new_spine)}

if __name__ == "__main__":
    result = reorder_spine(
        r"C:\Users\a\.cys\claude\jobs\8442bc1d\tmp\test_reflow_v2.epub",
        r"C:\Users\a\.cys\claude\jobs\8442bc1d\tmp\test_reflow_v3.epub",
        base_name="테스트복사본",
        front_matter_range=(54, 55),
        toc_range=(56, 72),
        insert_front_before="테스트복사본-8.xhtml",
        insert_toc_before="테스트복사본-12.xhtml",
    )
    print(result)
