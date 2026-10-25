"""PRAG (ABAP pragma) metadata collection."""

import html
from pathlib import Path
from defusedxml import ElementTree as ET


def collect_prag_sources(src_dir, obj_name, safe, source_set_type):
    sources = source_set_type()
    path = src_dir / f"{safe}.prag.xml"
    meta = {}
    if path.exists():
        try:
            root = ET.fromstring(path.read_text(encoding="utf-8", errors="replace"))
            node = root.find(".//PRAG")
            if node is not None:
                meta = {child.tag.upper(): html.unescape((child.text or "").strip())
                        for child in node if not list(child)}
        except ET.ParseError as exc:
            print(f"  WARNING: could not parse {path.name}: {exc}")
    sources.prag_meta = meta
    return sources
