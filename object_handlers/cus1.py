"""CUS1 IMG customizing-activity XML collection."""

import html
from pathlib import Path
from defusedxml import ElementTree as ET


def _row(node):
    return {child.tag.upper(): html.unescape((child.text or "").strip())
            for child in node if not list(child)}


def _rows(node):
    return [_row(row) for row in node if list(row)]


def collect_cus1_sources(src_dir, obj_name, safe, source_set_type):
    """Read abapGit's CUS1 activity graph."""
    sources = source_set_type()
    meta = {"header": {}, "exit": {}, "titles": [], "objects": [],
            "object_titles": []}
    path = Path(src_dir) / f"{safe}.cus1.xml"
    if path.exists():
        root = ET.fromstring(path.read_text(encoding="utf-8", errors="replace"))
        node = root.find(".//CUS1")
        if node is not None:
            for child in node:
                tag = child.tag.upper()
                if tag == "ACTIVITY_HEADER": meta["header"] = _row(child)
                elif tag == "ACTIVITY_CUSTOMER_EXIT": meta["exit"] = _row(child)
                elif tag == "ACTIVITY_TITLE": meta["titles"] = _rows(child)
                elif tag == "OBJECTS": meta["objects"] = _rows(child)
                elif tag == "OBJECTS_TITLE": meta["object_titles"] = _rows(child)
    sources.cus1_meta = meta
    return sources
