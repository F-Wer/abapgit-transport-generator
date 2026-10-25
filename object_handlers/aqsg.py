"""ABAP Query functional-area (AQSG) XML extraction."""

from pathlib import Path
from typing import Type

def collect_aqsg_sources(src_dir: Path, obj_name: str, safe: str,
                         source_set_type: Type[dict]) -> dict[str, str]:
    """Read AQSG's generic tables; its XML shape matches AQQU's serializer."""
    sources = source_set_type()
    # AQSG uses AQGSCAT/AQGDB rather than AQQU's AQGQCAT/AQGDB/AQGTQ.
    # Parse the small generic table shape locally so no type-specific fields
    # are lost from the cluster row.
    from defusedxml import ElementTree as ET
    import html
    path = src_dir / f"{safe}.aqsg.xml"
    sources.aqsg_meta = {}
    if not path.exists():
        return sources
    try:
        root = ET.fromstring(path.read_text(encoding="utf-8", errors="replace"))
    except ET.ParseError as exc:
        print(f"  WARNING: could not parse {path.name}: {exc}")
        return sources
    for table in ("AQGSCAT", "AQGDB"):
        node = root.find(f".//{table}")
        if node is None:
            continue
        direct = {child.tag.upper(): html.unescape((child.text or "").strip())
                  for child in node if len(child) == 0}
        rows = [direct] if direct else [
            {child.tag.upper(): html.unescape((child.text or "").strip())
             for child in item if len(child) == 0}
            for item in node]
        sources.aqsg_meta[table] = [row for row in rows if row]
    return sources
