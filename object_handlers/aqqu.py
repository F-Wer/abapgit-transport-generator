"""ABAP Query (AQQU) XML extraction.

AQQU uses abapGit's generic serializer.  Each of its tables is serialized as
an internal-table XML node, so preserve every row (including the opaque
base64 ``AQGDB-CLUSTD`` payload) instead of assuming a one-row query.
"""

import html
from pathlib import Path
from typing import Any, Type
from defusedxml import ElementTree as ET
from defusedxml.common import DefusedXmlException


_TABLES = ("AQGQCAT", "AQGDB", "AQGTQ")


def _row(element: Any) -> dict[str, str]:
    return {
        child.tag.upper(): html.unescape((child.text or "").strip())
        for child in element if len(child) == 0
    }


def parse_aqqu_xml(xml_path: Path) -> dict[str, list[dict[str, str]]]:
    """Read generic abapGit table nodes, accepting direct and ``item`` rows."""
    result: dict[str, list[dict[str, str]]] = {}
    if xml_path is None or not Path(xml_path).exists():
        return result
    try:
        root = ET.fromstring(Path(xml_path).read_text(encoding="utf-8",
                                                       errors="replace"))
    except (ET.ParseError, DefusedXmlException) as exc:
        print(f"  WARNING: could not parse {Path(xml_path).name}: {exc}")
        return result
    for table in _TABLES:
        node = root.find(f".//{table}")
        if node is None:
            continue
        direct = _row(node)
        if direct:
            result[table] = [direct]
            continue
        rows = [_row(item) for item in node if _row(item)]
        if rows:
            result[table] = rows
    return result


def collect_aqqu_sources(src_dir: Path, obj_name: str, safe: str,
                         source_set_type: Type[dict]) -> dict[str, str]:
    sources = source_set_type()
    sources.aqqu_meta = parse_aqqu_xml(src_dir / f"{safe}.aqqu.xml")
    if not sources.aqqu_meta:
        print(f"  WARNING: no AQQU metadata found for {obj_name}")
    return sources
