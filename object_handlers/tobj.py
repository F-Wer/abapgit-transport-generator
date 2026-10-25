"""Table maintenance generator metadata collection for transport generation."""

from pathlib import Path
from typing import Type
from defusedxml import ElementTree as ET
from defusedxml.common import DefusedXmlException


def _parse_tobj_flat(element) -> dict:
    if element is None:
        return {}
    fields = {}
    for child in element:
        fields[child.tag.upper()] = (child.text or "").strip()
    return fields


def parse_tobj_xml(xml_path: Path) -> dict:
    """Read abapGit .tobj.xml metadata for OBJH/OBJT/OBJS/TDDAT/TVDIR."""
    out = {"objh": {}, "objt": {}, "objs_rows": [],
           "tddat": None, "tvdir": {}}
    if xml_path is None or not Path(xml_path).exists():
        return out
    text = Path(xml_path).read_text(encoding="utf-8", errors="replace")
    try:
        root = ET.fromstring(text)
    except (ET.ParseError, DefusedXmlException) as exc:
        print(f"  WARNING: could not parse {Path(xml_path).name}: {exc}")
        return out

    out["objh"] = _parse_tobj_flat(root.find(".//OBJH"))
    out["objt"] = _parse_tobj_flat(root.find(".//OBJT"))

    objs_wrapper = root.find(".//OBJS")
    if objs_wrapper is not None:
        for item in objs_wrapper.findall("OBJS"):
            row = _parse_tobj_flat(item)
            if row.get("OBJECTNAME") or row.get("TABNAME"):
                out["objs_rows"].append(row)

    tobj_wrapper = root.find(".//TOBJ")
    if tobj_wrapper is not None:
        tddat_el = tobj_wrapper.find("TDDAT")
        if tddat_el is not None:
            out["tddat"] = _parse_tobj_flat(tddat_el)
        out["tvdir"] = _parse_tobj_flat(tobj_wrapper.find("TVDIR"))
    return out


def collect_tobj_sources(src_dir: Path, obj_name: str, safe: str,
                         source_set_type: Type[dict]) -> dict[str, str]:
    """Collect table maintenance generator metadata from .tobj.xml."""
    sources = source_set_type()
    tobj_xml = src_dir / f"{safe}.tobj.xml"
    sources.tobj_meta = parse_tobj_xml(tobj_xml)
    if not sources.tobj_meta.get("objh"):
        print(f"  WARNING: no <OBJH> metadata found in {tobj_xml.name}")
    return sources
