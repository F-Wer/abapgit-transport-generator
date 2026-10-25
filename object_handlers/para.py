"""PARA SPA/GPA-parameter XML collection."""

import html
from pathlib import Path
from defusedxml import ElementTree as ET


def collect_para_sources(src_dir, obj_name, safe, source_set_type):
    """Read abapGit's TPARA and TPARAT records from .para.xml."""
    sources = source_set_type()
    meta = {"tpara": {}, "tparat": {}}
    path = Path(src_dir) / f"{safe}.para.xml"
    if path.exists():
        root = ET.fromstring(path.read_text(encoding="utf-8", errors="replace"))
        node = root.find(".//PARA")
        if node is not None:
            for name, key in (("TPARA", "tpara"), ("TPARAT", "tparat")):
                section = node.find(name)
                if section is not None:
                    meta[key] = {
                        item.tag.upper(): html.unescape((item.text or "").strip())
                        for item in section if not list(item)
                    }
    sources.para_meta = meta
    return sources
