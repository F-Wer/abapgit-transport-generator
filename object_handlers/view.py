"""Database view metadata collection for abapGit transport generation."""

import html
from pathlib import Path
from typing import Type
from defusedxml import ElementTree as ET
from defusedxml.common import DefusedXmlException


def parse_view_xml(xml_path) -> dict:
    """
    Read the abapGit .view.xml metadata: the view header (<DD25V>), the
    base-table list (<DD26V_TABLE><DD26V>...), and the view-field list
    (<DD27P_TABLE><DD27P>...). A real ElementTree parse (not a regex) --
    both wrapper elements hold a genuine list of child elements, the same
    table-of-structures shape MSAG's <T100> list / TABL's <DD03P_TABLE>
    already needed ElementTree for.

    Returns {viewname, ddlanguage, aggtype, applclass, roottab, ddtext,
    viewclass, customauth, viewgrant, globalflag, tables: [...],
    fields: [...]}. A tag not present in the XML is simply absent from the
    returned dicts -- callers (_regenerate_view_rows in
    abapgit_to_transport.py) decide what to do, per field. `tables`/
    `fields` are empty lists when their wrapper elements are absent or
    empty.
    """
    out = {"viewname": "", "ddlanguage": "", "aggtype": "", "applclass": "",
           "roottab": "", "ddtext": "", "viewclass": "", "customauth": "",
           "viewgrant": "", "globalflag": "", "tables": [], "fields": []}
    if xml_path is None or not Path(xml_path).exists():
        return out
    text = Path(xml_path).read_text(encoding="utf-8", errors="replace")
    try:
        root = ET.fromstring(text)
    except (ET.ParseError, DefusedXmlException) as exc:
        print(f"  WARNING: could not parse {Path(xml_path).name}: {exc}")
        return out

    dd25v = root.find(".//DD25V")
    if dd25v is not None:
        # every header column the XML carries, by column name
        out["dd25v"] = {el.tag.upper(): html.unescape((el.text or "").strip())
                        for el in dd25v}
        for tag, key in (("VIEWNAME", "viewname"), ("DDLANGUAGE", "ddlanguage"),
                          ("AGGTYPE", "aggtype"), ("APPLCLASS", "applclass"),
                          ("ROOTTAB", "roottab"), ("DDTEXT", "ddtext"),
                          ("VIEWCLASS", "viewclass"), ("CUSTOMAUTH", "customauth"),
                          ("VIEWGRANT", "viewgrant"), ("GLOBALFLAG", "globalflag")):
            el = dd25v.find(tag)
            if el is not None and el.text is not None:
                out[key] = html.unescape(el.text.strip())

    dd26v_table = root.find(".//DD26V_TABLE")
    if dd26v_table is not None:
        for item in dd26v_table.findall("DD26V"):
            tbl = {}
            for tag in ("TABNAME", "TABPOS", "FORTABNAME", "FORFIELD", "FORDIR"):
                el = item.find(tag)
                if el is not None and el.text is not None:
                    tbl[tag] = html.unescape(el.text.strip())
            if tbl.get("TABNAME"):
                out["tables"].append(tbl)

    dd27p_table = root.find(".//DD27P_TABLE")
    if dd27p_table is not None:
        for item in dd27p_table.findall("DD27P"):
            field = {}
            for tag in ("VIEWFIELD", "TABNAME", "FIELDNAME", "KEYFLAG", "RDONLY",
                        "SHLPORIGIN", "VALEXI", "LOGFLAG", "CHECKTABLE"):
                el = item.find(tag)
                if el is not None and el.text is not None:
                    field[tag] = html.unescape(el.text.strip())
            if field.get("VIEWFIELD"):
                out["fields"].append(field)
    return out


def collect_view_sources(src_dir: Path, obj_name: str, safe: str,
                         source_set_type: Type[dict]) -> dict[str, str]:
    """Collect DDIC view metadata from abapGit's .view.xml file."""
    sources = source_set_type()
    view_xml = src_dir / f"{safe}.view.xml"
    sources.view_meta = parse_view_xml(view_xml)
    if not sources.view_meta.get("fields"):
        print(f"  WARNING: no <DD27P_TABLE> fields found in {view_xml.name}")
    if not sources.view_meta.get("tables"):
        print(f"  WARNING: no <DD26V_TABLE> base tables found in "
              f"{view_xml.name}")
    return sources
