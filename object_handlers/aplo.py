"""Application-log object (APLO) XML extraction."""

import html
from pathlib import Path
from defusedxml import ElementTree as ET
from defusedxml.common import DefusedXmlException


def parse_aplo_xml(xml_path: Path) -> dict[str, list[dict[str, str]]]:
    """Extract each abapGit APLO table-shaped XML section by leaf fields."""
    out: dict[str, list[dict[str, str]]] = {}
    if xml_path is None or not Path(xml_path).exists():
        return out
    try:
        root = ET.fromstring(Path(xml_path).read_text(encoding="utf-8", errors="replace"))
    except (ET.ParseError, DefusedXmlException):
        return out
    for section in root.iter():
        direct = {x.tag.upper(): html.unescape((x.text or "").strip())
                  for x in section if len(x) == 0}
        if direct and section.tag.upper() in {"BALOBJ", "BALOBJT", "BALSUB", "BALSUBT"}:
            out.setdefault(section.tag.upper(), []).append(direct)
        rows = []
        for row in section:
            if len(row):
                rows.append({x.tag.upper(): html.unescape((x.text or "").strip()) for x in row if len(x) == 0})
        if rows:
            out[section.tag.upper()] = rows
    return out


def collect_aplo_sources(src_dir, obj_name, safe, source_set_type):
    sources = source_set_type()
    sources.aplo_meta = parse_aplo_xml(src_dir / f"{safe}.aplo.xml")
    return sources
