#!/usr/bin/env python3
"""DEVC (development package) metadata parsing and row regeneration."""

def parse_devc_xml(xml_path):
    """
    Parse abapGit's .devc.xml for package metadata.

    Returns the serialised package fields that can be represented safely in
    TDEVC/TDEVCT.  abapGit normally serialises only ``<DEVC><CTEXT>``; fields
    beyond that are deliberately not guessed from the probe package.
    """
    from defusedxml import ElementTree as ET
    from defusedxml.common import DefusedXmlException
    from pathlib import Path
    import html

    out = {"description": "", "TDEVC": {}, "TDEVCT": {}}
    if xml_path is None or not Path(xml_path).exists():
        return out

    text = Path(xml_path).read_text(encoding="utf-8", errors="replace")
    try:
        root = ET.fromstring(text)
    except (ET.ParseError, DefusedXmlException):
        return out

    # The standard abapGit serializer has a DEVC element.  Accept the table
    # names too so a fuller future serializer remains forwards compatible.
    for tag, target in (("DEVC", "TDEVC"), ("TDEVC", "TDEVC"),
                        ("TDEVCT", "TDEVCT")):
        node = root.find(f".//{tag}")
        if node is None:
            continue
        for el in node:
            if list(el):
                continue
            value = html.unescape((el.text or "").strip())
            if value:
                out[target][el.tag.upper()] = value

    # CTEXT is the normal serializer field; DDTEXT appeared in the original
    # experimental handler and remains accepted for backwards compatibility.
    out["description"] = (out["TDEVCT"].get("CTEXT")
                          or out["TDEVC"].get("CTEXT")
                          or out["TDEVCT"].get("DDTEXT")
                          or "")

    return out


def regenerate_devc_rows(records, obj_name, devc_meta):
    """
    Regenerate the package's two data rows without retaining donor metadata.

    The importable package contract in a native package export is TDEVC plus TDEVCT.
    Values omitted by abapGit are emitted as initial values; the few package
    defaults below are SAP's local-package defaults, not copied from the
    probe's SAP namespace package.
    """
    from abapgit_to_transport import _regenerate_table_content

    header = dict(devc_meta.get("TDEVC") or {})
    header.update({"DEVCLASS": obj_name, "KORRFLAG": "X",
                   "DLVUNIT": header.get("DLVUNIT") or "HOME",
                   "NAMESPACE": header.get("NAMESPACE") or "/0CUST/"})
    text = dict(devc_meta.get("TDEVCT") or {})
    text.update({"DEVCLASS": obj_name, "SPRAS": text.get("SPRAS") or "E",
                 "CTEXT": devc_meta.get("description") or ""})
    result = _regenerate_table_content(
        records, obj_name, {"TDEVC": [header], "TDEVCT": [text]})
    print(f"  DEVC {obj_name}: regenerated TDEVC/TDEVCT from .devc.xml")
    return result
