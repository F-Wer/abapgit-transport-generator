"""CUS2 IMG attribute XML collection."""

import html
from pathlib import Path
from defusedxml import ElementTree as ET


def _row(node):
    return {child.tag.upper(): html.unescape((child.text or "").strip())
            for child in node if not list(child)}


def _rows(node):
    return [_row(row) for row in node if list(row)]


def collect_cus2_sources(src_dir, obj_name, safe, source_set_type):
    """Read abapGit's CUS2 header, titles, countries, and components."""
    sources = source_set_type()
    meta = {"header": {}, "titles": [], "countries": [], "components": []}
    path = Path(src_dir) / f"{safe}.cus2.xml"
    if path.exists():
        root = ET.fromstring(path.read_text(encoding="utf-8", errors="replace"))
        node = root.find(".//CUS2")
        if node is not None:
            for child in node:
                tag = child.tag.upper()
                if tag == "HEADER":
                    meta["header"] = _row(child)
                elif tag in ("TITLES", "COUNTRIES", "COMPONENTS"):
                    meta[tag.lower()] = _rows(child)
    sources.cus2_meta = meta
    return sources
