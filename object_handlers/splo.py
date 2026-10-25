"""SPLO (SAPscript page layout) XML collection."""

import html
from pathlib import Path
from defusedxml import ElementTree as ET


def _row(node):
    return {child.tag.upper(): html.unescape((child.text or "").strip())
            for child in node if not list(child)}


def collect_splo_sources(src_dir, obj_name, safe, source_set_type):
    """Read abapGit's TSPLD/TSPLT/TSP0P serialization."""
    sources = source_set_type()
    meta = {"header": {}, "texts": [], "output": {}}
    path = Path(src_dir) / f"{safe}.splo.xml"
    if path.exists():
        root = ET.fromstring(path.read_text(encoding="utf-8", errors="replace"))
        node = root.find(".//SPLO")
        if node is not None:
            for child in node:
                tag = child.tag.upper()
                if tag == "TSPLD":
                    meta["header"] = _row(child)
                elif tag == "TSPLT":
                    meta["texts"] = [_row(row) for row in child] if list(child) and list(child)[0].tag.upper() in ("ITEM", "TSPLT") else [_row(child)]
                elif tag == "TSP0P":
                    meta["output"] = _row(child)
    sources.splo_meta = meta
    return sources
