"""NROB number-range-object XML collection."""

import html
from pathlib import Path
from defusedxml import ElementTree as ET


def collect_nrob_sources(src_dir, obj_name, safe, source_set_type):
    """Read abapGit's TNRO/TNROT payload from a .nrob.xml file."""
    sources = source_set_type()
    meta = {"attributes": {}, "text": {}}
    path = Path(src_dir) / f"{safe}.nrob.xml"
    if path.exists():
        root = ET.fromstring(path.read_text(encoding="utf-8", errors="replace"))
        node = root.find(".//NROB")
        if node is not None:
            for name, key in (("ATTRIBUTES", "attributes"), ("TEXT", "text")):
                section = node.find(name)
                if section is not None:
                    meta[key] = {
                        item.tag.upper(): html.unescape((item.text or "").strip())
                        for item in section if not list(item)
                    }
    sources.nrob_meta = meta
    return sources
