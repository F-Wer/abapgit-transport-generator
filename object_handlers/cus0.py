"""CUS0 IMG activity XML collection."""

import html
from pathlib import Path
from defusedxml import ElementTree as ET


def _row(node):
    return {child.tag.upper(): html.unescape((child.text or "").strip())
            for child in node if not list(child)}


def collect_cus0_sources(src_dir, obj_name, safe, source_set_type):
    """Read abapGit's CUS0 header and text-table serialization."""
    sources = source_set_type()
    meta = {"header": {}, "texts": []}
    path = Path(src_dir) / f"{safe}.cus0.xml"
    if path.exists():
        root = ET.fromstring(path.read_text(encoding="utf-8", errors="replace"))
        node = root.find(".//CUS0")
        if node is not None:
            for child in node:
                tag = child.tag.upper()
                if tag == "HEADER":
                    meta["header"] = _row(child)
                elif tag == "TEXTS":
                    meta["texts"] = [_row(row) for row in child if list(row)]
    sources.cus0_meta = meta
    return sources
