"""OTGR object-type-group XML collection."""
import html
from pathlib import Path
from defusedxml import ElementTree as ET

def collect_otgr_sources(src_dir, obj_name, safe, source_set_type):
    sources = source_set_type(); meta = {"header": {}, "texts": [], "elements": [], "parents": []}
    path = src_dir / f"{safe}.otgr.xml"
    if path.exists():
        root = ET.fromstring(path.read_text(encoding="utf-8", errors="replace"))
        node = root.find(".//OTGR")
        if node is not None:
            for child in node:
                tag = child.tag.upper()
                if tag == "CLS_TYPE_GROUP":
                    meta["header"] = {x.tag.upper(): html.unescape((x.text or "").strip()) for x in child if not list(x)}
                elif tag in ("TEXTS", "ELEMENTS"):
                    key = tag.lower()
                    meta[key] = [{x.tag.upper(): html.unescape((x.text or "").strip()) for x in row if not list(x)} for row in child]
        parents = root.find(".//PARENTS")
        if parents is not None:
            meta["parents"] = [{x.tag.upper(): html.unescape((x.text or "").strip()) for x in row if not list(x)} for row in parents]
    sources.otgr_meta = meta
    return sources
