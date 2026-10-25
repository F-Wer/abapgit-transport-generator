"""SPPF page-format XML collection."""

import html
from pathlib import Path
from defusedxml import ElementTree as ET


def collect_sppf_sources(src_dir, obj_name, safe, source_set_type):
    """Read generic abapGit TSP08 content from .sppf.xml."""
    sources = source_set_type()
    meta = {}
    path = Path(src_dir) / f"{safe}.sppf.xml"
    if path.exists():
        root = ET.fromstring(path.read_text(encoding="utf-8", errors="replace"))
        node = root.find(".//SPPF/TSP08")
        if node is not None:
            meta = {item.tag.upper(): html.unescape((item.text or "").strip())
                    for item in node if not list(item)}
    sources.sppf_meta = meta
    return sources
