"""SUSC authorization-object-class XML collection."""

import html
from pathlib import Path
from defusedxml import ElementTree as ET


def collect_susc_sources(src_dir, obj_name, safe, source_set_type):
    """Read abapGit's TOBC and TOBCT payload from .susc.xml."""
    sources = source_set_type()
    meta = {"tobc": {}, "tobct": {}}
    path = Path(src_dir) / f"{safe}.susc.xml"
    if path.exists():
        root = ET.fromstring(path.read_text(encoding="utf-8", errors="replace"))
        node = root.find(".//SUSC")
        if node is not None:
            for name, key in (("TOBC", "tobc"), ("TOBCT", "tobct")):
                section = node.find(name)
                if section is not None:
                    meta[key] = {
                        item.tag.upper(): html.unescape((item.text or "").strip())
                        for item in section if not list(item)
                    }
    sources.susc_meta = meta
    return sources
