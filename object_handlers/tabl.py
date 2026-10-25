"""Table/structure metadata collection for abapGit transport generation."""

import html
from pathlib import Path
from typing import Type
from defusedxml import ElementTree as ET
from defusedxml.common import DefusedXmlException


def parse_tabl_xml(xml_path) -> dict:
    """
    Read the abapGit .tabl.xml metadata: the table header (<DD02V>) and the
    field list (<DD03P_TABLE><DD03P>...). Verified against abapGit's own
    serializer (zcl_abapgit_object_tabl.clas.abap / lcl_tabl_xml, pulled
    from github.com/abapGit/abapGit) and real .tabl.xml files from public
    GitHub repos -- both a transparent table
    (christianjianelli/yaai's yaai_log.tabl.xml, TABCLASS=TRANSP, DD09L
    present, 14 fields including a direct-typed CLIENT/EXPIRY_DATE and
    several data-element-referencing fields) and a structure
    (abap2xlsx/abap2xlsx's zexcel_s_rtf.tabl.xml, TABCLASS=INTTAB, no
    DD09L block at all, 3 fields).

    A real ElementTree parse (not a regex) because DD03P_TABLE wraps a list
    of <DD03P> elements -- a real table-of-structures, unlike MSAG's
    same-name-nested <T100><T100>...</T100></T100> shape, but the same
    class of "needs real XML scoping" problem a regex would mis-handle.

    Also reads <DD09L> (technical settings -- buffering, table category),
    present in abapGit's serialization only when the table has one (a real
    transparent table); a structure's .tabl.xml carries no <DD09L> element
    at all (confirmed: abap2xlsx/abap2xlsx's zexcel_s_rtf.tabl.xml,
    TABCLASS=INTTAB, no DD09L block). Schema confirmed against
    tricktresor/cute's zcute_tech.tabl.xml (TABNAME, AS4LOCAL, TABKAT,
    TABART, BUFALLOW) and christianjianelli/yaai's yaai_log.tabl.xml.

    Returns {tabname, ddlanguage, tabclass, ddtext, masterlang, contflag,
    clidep, exclass, fields: [{...}, ...], dd09l: {...} or {}}. Fields not
    present in the XML are simply absent from the returned dicts -- callers
    decide what to do (write it, or leave the template's own value, per
    field). `dd09l` is an empty dict when the XML has no <DD09L> element at
    all -- callers use that as the drop-vs-populate signal (see
    _regenerate_tabl_rows in abapgit_to_transport.py).
    """
    out = {"tabname": "", "ddlanguage": "", "tabclass": "", "ddtext": "",
           "masterlang": "", "contflag": "", "clidep": "", "exclass": "",
           "fields": [], "dd09l": {}, "dd02v": {}}
    if xml_path is None or not Path(xml_path).exists():
        return out
    text = Path(xml_path).read_text(encoding="utf-8", errors="replace")
    try:
        root = ET.fromstring(text)
    except (ET.ParseError, DefusedXmlException) as exc:
        print(f"  WARNING: could not parse {Path(xml_path).name}: {exc}")
        return out

    dd02v = root.find(".//DD02V")
    if dd02v is not None:
        for tag, key in (("TABNAME", "tabname"), ("DDLANGUAGE", "ddlanguage"),
                          ("TABCLASS", "tabclass"), ("DDTEXT", "ddtext"),
                          ("MASTERLANG", "masterlang"), ("CONTFLAG", "contflag"),
                          ("CLIDEP", "clidep"), ("EXCLASS", "exclass")):
            el = dd02v.find(tag)
            if el is not None and el.text is not None:
                out[key] = html.unescape(el.text.strip())

        # Every header field, by column name -- what the XML does not carry
        # is initial on the source system (abapGit drops initial fields).
        out["dd02v"] = {el.tag.upper(): html.unescape((el.text or "").strip())
                        for el in dd02v}

    dd09l_el = root.find(".//DD09L")
    if dd09l_el is not None:
        out["dd09l"] = {el.tag.upper(): html.unescape((el.text or "").strip())
                        for el in dd09l_el}

    # Parts of a table this generator does not write. Say so instead of
    # shipping a table that silently lacks them.
    for tag, what in (("DD05M_TABLE", "foreign keys"),
                      ("DD08V_TABLE", "foreign keys"),
                      ("DD12V", "secondary indexes"),
                      ("DD35V_TALE", "search help assignments"),
                      ("DD36M", "search help assignments")):
        if root.find(f".//{tag}") is not None:
            print(f"  WARNING: {Path(xml_path).name} has <{tag}> ({what}) "
                  f"-- not supported, NOT part of the transport")

    dd03p_table = root.find(".//DD03P_TABLE")
    if dd03p_table is not None:
        for item in dd03p_table.findall("DD03P"):
            field = {el.tag.upper(): html.unescape((el.text or "").strip())
                     for el in item}
            if field.get("FIELDNAME"):
                out["fields"].append(field)
    return out


def collect_tabl_sources(src_dir: Path, obj_name: str, safe: str,
                         source_set_type: Type[dict]) -> dict[str, str]:
    """Collect table/structure metadata from abapGit's .tabl.xml file."""
    sources = source_set_type()
    tabl_xml = src_dir / f"{safe}.tabl.xml"
    sources.tabl_meta = parse_tabl_xml(tabl_xml)
    if not sources.tabl_meta.get("fields"):
        print(f"  WARNING: no <DD03P_TABLE> fields found in {tabl_xml.name}")
    return sources
