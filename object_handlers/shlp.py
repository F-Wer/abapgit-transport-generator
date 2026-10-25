"""Search help metadata collection for abapGit transport generation."""

import html
from pathlib import Path
from typing import Type
from defusedxml import ElementTree as ET
from defusedxml.common import DefusedXmlException


def parse_shlp_xml(xml_path) -> dict:
    """
    Read the abapGit .shlp.xml metadata: every child element of <DD30V>
    (the search-help header + master-language text, catch-all by tag name --
    same approach parse_doma_xml uses for <DD01V>), the parameter list from
    <DD32P_TABLE><DD32P>...</DD32P></DD32P_TABLE> (a real table-of-
    structures, ElementTree, like TABL's DD03P_TABLE / VIEW's DD27P_TABLE),
    and -- when present, which is ONLY the collective-search-help case --
    the sub-search-help list (<DD31V_TABLE><DD31V>...) and the
    parameter-to-subhelp mapping (<DD33V_TABLE><DD33V>...).

    Returns {"header": {...}, "fields": [...], "submethods": [...] (empty
    when <DD31V_TABLE> is absent), "mappings": [...] (empty when
    <DD33V_TABLE> is absent)}. A tag not present in the XML is simply absent
    from its dict -- callers (_regenerate_shlp_rows in
    abapgit_to_transport.py) decide what to do.
    """
    out = {"header": {}, "fields": [], "submethods": [], "mappings": []}
    if xml_path is None or not Path(xml_path).exists():
        return out
    text = Path(xml_path).read_text(encoding="utf-8", errors="replace")
    try:
        root = ET.fromstring(text)
    except (ET.ParseError, DefusedXmlException) as exc:
        print(f"  WARNING: could not parse {Path(xml_path).name}: {exc}")
        return out

    dd30v = root.find(".//DD30V")
    if dd30v is not None:
        for el in dd30v:
            tag = el.tag.upper()
            if tag == "SHLPNAME":
                continue   # handled by the generic object-name rename
            out["header"][tag] = html.unescape((el.text or "").strip())

    dd32p_table = root.find(".//DD32P_TABLE")
    if dd32p_table is not None:
        for item in dd32p_table.findall("DD32P"):
            field = {}
            for el in item:
                tag = el.tag.upper()
                if tag == "SHLPNAME":
                    continue
                field[tag] = html.unescape((el.text or "").strip())
            if field.get("FIELDNAME"):
                out["fields"].append(field)

    dd31v_table = root.find(".//DD31V_TABLE")
    if dd31v_table is not None:
        for item in dd31v_table.findall("DD31V"):
            entry = {}
            for el in item:
                tag = el.tag.upper()
                if tag == "SHLPNAME":
                    continue
                entry[tag] = html.unescape((el.text or "").strip())
            if entry.get("SUBSHLP"):
                out["submethods"].append(entry)

    dd33v_table = root.find(".//DD33V_TABLE")
    if dd33v_table is not None:
        for item in dd33v_table.findall("DD33V"):
            entry = {}
            for el in item:
                tag = el.tag.upper()
                if tag == "SHLPNAME":
                    continue
                entry[tag] = html.unescape((el.text or "").strip())
            if entry.get("SUBSHLP"):
                out["mappings"].append(entry)

    return out


def collect_shlp_sources(src_dir: Path, obj_name: str, safe: str,
                         source_set_type: Type[dict]) -> dict[str, str]:
    """Collect search help metadata from abapGit's .shlp.xml file."""
    sources = source_set_type()
    shlp_xml = src_dir / f"{safe}.shlp.xml"
    sources.shlp_meta = parse_shlp_xml(shlp_xml)
    if not sources.shlp_meta.get("header"):
        print(f"  WARNING: no <DD30V> metadata found in {shlp_xml.name}")
    return sources
