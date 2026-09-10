"""Embed TrueType fonts into a .docx (OOXML obfuscated-font format).

Word/LibreOffice read fonts embedded as 'obfuscated' parts: the first 32
bytes of the TTF are XOR-masked with a key derived from a per-font GUID.
We register each weight/style we actually use as its own font family so the
document's `w:rFonts` names resolve to the embedded face even on a machine
that has none of these fonts installed.

Usage: python embed_fonts_docx.py <in.docx> <out.docx> <fonts_dir>
"""
from __future__ import annotations
import shutil, sys, uuid, zipfile
from pathlib import Path
from lxml import etree

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
CT = "http://schemas.openxmlformats.org/package/2006/content-types"
REL = "http://schemas.openxmlformats.org/package/2006/relationships"
FONT_REL = R + "/font"
OBF_CT = "application/vnd.openxmlformats-officedocument.obfuscatedFont"

# family name in the doc -> {style: ttf filename}
FONTS = {
    "Zilla Slab":            {"bold":    "ZillaSlab-Bold.ttf"},
    "Zilla Slab SemiBold":   {"regular": "ZillaSlab-SemiBold.ttf"},
    "Source Sans 3":         {"regular": "SourceSans3-Regular.ttf",
                              "italic":  "SourceSans3-Italic.ttf"},
    "Source Sans 3 SemiBold":{"regular": "SourceSans3-SemiBold.ttf"},
    "IBM Plex Mono":         {"regular": "IBMPlexMono-Regular.ttf"},
}
EMBED_TAG = {"regular": "embedRegular", "bold": "embedBold",
             "italic": "embedItalic", "boldItalic": "embedBoldItalic"}


def obfuscate(data: bytes, guid: str) -> bytes:
    """XOR the first 32 bytes with the 16-byte key derived from the GUID."""
    h = guid.replace("-", "").replace("{", "").replace("}", "")
    key = bytes.fromhex(h)[::-1]            # reversed 16 bytes
    out = bytearray(data)
    for i in range(32):
        out[i] ^= key[i % 16]
    return bytes(out)


def main():
    src, dst, fonts_dir = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    tmp = dst.with_suffix(".build")
    if tmp.exists(): shutil.rmtree(tmp)
    with zipfile.ZipFile(src) as z:
        z.extractall(tmp)

    # 1) build obfuscated font parts + collect (family, style, part, guid, rid)
    (tmp / "word" / "fonts").mkdir(parents=True, exist_ok=True)
    entries = []  # (family, style, partname, guid, rid)
    n = 0
    for family, styles in FONTS.items():
        for style, fname in styles.items():
            n += 1
            guid = "{" + str(uuid.uuid4()).upper() + "}"
            data = (fonts_dir / fname).read_bytes()
            part = f"font{n}.odttf"
            (tmp / "word" / "fonts" / part).write_bytes(obfuscate(data, guid))
            entries.append((family, style, part, guid, f"rIdFont{n}"))

    # 2) fontTable.xml — one <w:font> per family, grouping its styles
    ns = {"w": W, "r": R}
    fnt = etree.Element(f"{{{W}}}fonts", nsmap={"w": W, "r": R})
    by_family = {}
    for family, style, part, guid, rid in entries:
        by_family.setdefault(family, []).append((style, guid, rid))
    for family, rows in by_family.items():
        fe = etree.SubElement(fnt, f"{{{W}}}font")
        fe.set(f"{{{W}}}name", family)
        for style, guid, rid in rows:
            emb = etree.SubElement(fe, f"{{{W}}}{EMBED_TAG[style]}")
            emb.set(f"{{{R}}}id", rid)
            emb.set(f"{{{W}}}fontKey", guid)
            emb.set(f"{{{W}}}subsetted", "false")
    (tmp / "word" / "fontTable.xml").write_bytes(
        etree.tostring(fnt, xml_declaration=True, encoding="UTF-8", standalone=True))

    # 3) fontTable.xml.rels — relationships to the font parts
    rels_dir = tmp / "word" / "_rels"; rels_dir.mkdir(exist_ok=True)
    rels_path = rels_dir / "fontTable.xml.rels"
    if rels_path.exists():
        rels = etree.parse(str(rels_path)).getroot()
    else:
        rels = etree.Element(f"{{{REL}}}Relationships", nsmap={None: REL})
    for family, style, part, guid, rid in entries:
        rel = etree.SubElement(rels, f"{{{REL}}}Relationship")
        rel.set("Id", rid); rel.set("Type", FONT_REL); rel.set("Target", f"fonts/{part}")
    rels_path.write_bytes(etree.tostring(rels, xml_declaration=True,
                                         encoding="UTF-8", standalone=True))

    # 4) document.xml.rels must relate to fontTable (python-docx already does,
    #    but ensure it exists)
    doc_rels = tmp / "word" / "_rels" / "document.xml.rels"
    dr = etree.parse(str(doc_rels)).getroot()
    has_ft = any(r.get("Type", "").endswith("/fontTable") for r in dr)
    if not has_ft:
        rel = etree.SubElement(dr, f"{{{REL}}}Relationship")
        rel.set("Id", "rIdFontTable")
        rel.set("Type", R + "/fontTable"); rel.set("Target", "fontTable.xml")
        doc_rels.write_bytes(etree.tostring(dr, xml_declaration=True,
                                            encoding="UTF-8", standalone=True))

    # 5) [Content_Types].xml — default for .odttf + ensure fontTable override
    ctp = tmp / "[Content_Types].xml"
    ct = etree.parse(str(ctp)).getroot()
    if not any(d.get("Extension") == "odttf" for d in ct if d.tag.endswith("Default")):
        d = etree.SubElement(ct, f"{{{CT}}}Default")
        d.set("Extension", "odttf"); d.set("ContentType", OBF_CT)
    ft_ct = "application/vnd.openxmlformats-officedocument.wordprocessingml.fontTable+xml"
    if not any(o.get("PartName") == "/word/fontTable.xml" for o in ct if o.tag.endswith("Override")):
        o = etree.SubElement(ct, f"{{{CT}}}Override")
        o.set("PartName", "/word/fontTable.xml"); o.set("ContentType", ft_ct)
    ctp.write_bytes(etree.tostring(ct, xml_declaration=True, encoding="UTF-8", standalone=True))

    # 6) settings.xml — turn embedding on
    st = tmp / "word" / "settings.xml"
    se = etree.parse(str(st)).getroot()
    if se.find(f"{{{W}}}embedTrueTypeFonts") is None:
        et = etree.Element(f"{{{W}}}embedTrueTypeFonts")
        et.set(f"{{{W}}}val", "true")
        # CT_Settings order: embedTrueTypeFonts sits just after <w:zoom>
        # (and before proofState/defaultTabStop). Placing it at the end makes
        # LibreOffice reject the settings part on export; Word is lenient but
        # we keep it schema-correct.
        zoom = se.find(f"{{{W}}}zoom")
        if zoom is not None:
            zoom.addnext(et)
        else:
            se.insert(0, et)
    st.write_bytes(etree.tostring(se, xml_declaration=True, encoding="UTF-8", standalone=True))

    # 7) rezip
    if dst.exists(): dst.unlink()
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as z:
        # content types first
        z.write(ctp, "[Content_Types].xml")
        for f in sorted(tmp.rglob("*")):
            if f.is_file() and f != ctp:
                z.write(f, f.relative_to(tmp).as_posix())
    shutil.rmtree(tmp)
    kb = dst.stat().st_size / 1024
    print(f"  embedded {len(entries)} font faces -> {dst.name}  {kb:.0f} KB")


if __name__ == "__main__":
    main()
