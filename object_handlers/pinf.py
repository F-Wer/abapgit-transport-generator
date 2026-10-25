"""PINF package-interface XML collection."""
import html
from pathlib import Path
from defusedxml import ElementTree as ET


def collect_pinf_sources(src_dir, obj_name, safe, source_set_type):
    """Read abapGit's package-interface header and element collection."""
    sources = source_set_type()
    meta = {"attributes": {}, "elements": []}
    path = src_dir / f"{safe}.pinf.xml"
    if path.exists():
        root = ET.fromstring(path.read_text(encoding="utf-8", errors="replace"))
        node = root.find(".//PINF")
        if node is not None:
            attrs = node.find("ATTRIBUTES")
            if attrs is not None:
                meta["attributes"] = {
                    item.tag.upper(): html.unescape((item.text or "").strip())
                    for item in attrs if not list(item)
                }
            elements = node.find("ELEMENTS")
            if elements is not None:
                meta["elements"] = [
                    {item.tag.upper(): html.unescape((item.text or "").strip())
                     for item in row if not list(item)}
                    for row in elements
                ]
    sources.pinf_meta = meta
    return sources
