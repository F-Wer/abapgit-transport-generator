"""Archive-information-structure (ASFC) generic-table extraction."""

import html
from pathlib import Path
from typing import Type
from defusedxml import ElementTree as ET
from defusedxml.common import DefusedXmlException


_TABLES = ("AIND_STR1", "AIND_STR1T", "AIND_STR3", "AIND_STR4",
           "AIND_STR6", "AIND_STR7")


def parse_asfc_xml(path: Path) -> dict[str, list[dict[str, str]]]:
    """Read every ASFC table emitted by abapGit's generic serializer."""
    result: dict[str, list[dict[str, str]]] = {}
    if not path.exists():
        return result
    try:
        root = ET.fromstring(path.read_text(encoding="utf-8", errors="replace"))
    except (ET.ParseError, DefusedXmlException) as exc:
        print(f"  WARNING: could not parse {path.name}: {exc}")
        return result
    for table in _TABLES:
        node = root.find(f".//{table}")
        if node is None:
            continue
        def fields(element):
            return {child.tag.upper(): html.unescape((child.text or "").strip())
                    for child in element if len(child) == 0}
        direct = fields(node)
        rows = [direct] if direct else [fields(item) for item in node]
        if any(rows):
            result[table] = [row for row in rows if row]
    return result


def collect_asfc_sources(src_dir: Path, obj_name: str, safe: str,
                         source_set_type: Type[dict]) -> dict[str, str]:
    sources = source_set_type()
    sources.asfc_meta = parse_asfc_xml(src_dir / f"{safe}.asfc.xml")
    return sources
