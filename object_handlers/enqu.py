"""Lock object metadata collection for abapGit transport generation."""

import html
from pathlib import Path
from typing import Type
from defusedxml import ElementTree as ET
from defusedxml.common import DefusedXmlException


def parse_enqu_xml(xml_path) -> dict:
    """
    Read the abapGit .enqu.xml metadata: the lock object header (<DD25V>),
    the base-table list (<DD26E_TABLE><DD26E>...), and the field list
    (<DD27P_TABLE><DD27P>...) -- the same wrapper-element-holds-a-list shape
    parse_view_xml already needed ElementTree for.

    Returns {viewname, ddlanguage, aggtype, roottab, ddtext, tables: [...],
    fields: [...]}. A tag not present in the XML is simply absent from the
    returned dicts -- callers (_regenerate_enqu_rows in
    abapgit_to_transport.py) decide what to do, per field. `tables`/
    `fields` are empty lists when their wrapper elements are absent or
    empty.

    Unlike VIEW's <DD25V>, ENQU's own real .enqu.xml samples (confirmed
    against 3 local files and abapGit's own LCL_OBJECT_ENQU source) never
    carry VIEWCLASS/CUSTOMAUTH/VIEWGRANT/GLOBALFLAG/APPLCLASS -- only
    VIEWNAME/DDLANGUAGE/AGGTYPE/ROOTTAB/DDTEXT -- so those tags are not even
    looked for here.
    """
    out = {"viewname": "", "ddlanguage": "", "aggtype": "", "roottab": "",
           "ddtext": "", "tables": [], "fields": []}
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
                          ("AGGTYPE", "aggtype"), ("ROOTTAB", "roottab"),
                          ("DDTEXT", "ddtext")):
            el = dd25v.find(tag)
            if el is not None and el.text is not None:
                out[key] = html.unescape(el.text.strip())

    dd26e_table = root.find(".//DD26E_TABLE")
    if dd26e_table is not None:
        for item in dd26e_table.findall("DD26E"):
            tbl = {}
            for tag in ("TABNAME", "TABPOS", "FORTABNAME", "ENQMODE"):
                el = item.find(tag)
                if el is not None and el.text is not None:
                    tbl[tag] = html.unescape(el.text.strip())
            if tbl.get("TABNAME"):
                out["tables"].append(tbl)

    dd27p_table = root.find(".//DD27P_TABLE")
    if dd27p_table is not None:
        for item in dd27p_table.findall("DD27P"):
            field = {}
            for tag in ("VIEWFIELD", "TABNAME", "FIELDNAME", "KEYFLAG",
                        "ENQMODE"):
                el = item.find(tag)
                if el is not None and el.text is not None:
                    field[tag] = html.unescape(el.text.strip())
            if field.get("VIEWFIELD"):
                out["fields"].append(field)
    return out


def collect_enqu_sources(src_dir: Path, obj_name: str, safe: str,
                         source_set_type: Type[dict]) -> dict[str, str]:
    """Collect lock object metadata from abapGit's .enqu.xml file."""
    sources = source_set_type()
    enqu_xml = src_dir / f"{safe}.enqu.xml"
    sources.enqu_meta = parse_enqu_xml(enqu_xml)
    if not sources.enqu_meta.get("fields"):
        print(f"  WARNING: no <DD27P_TABLE> fields found in {enqu_xml.name}")
    if not sources.enqu_meta.get("tables"):
        print(f"  WARNING: no <DD26E_TABLE> base tables found in "
              f"{enqu_xml.name}")
    return sources
