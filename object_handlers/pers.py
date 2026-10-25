"""PERS personalization-registry XML collection."""
import html
from pathlib import Path
from defusedxml import ElementTree as ET

def _row(node):
    return {c.tag.upper(): html.unescape((c.text or "").strip()) for c in node if not list(c)}

def collect_pers_sources(src_dir, obj_name, safe, source_set_type):
    sources = source_set_type(); meta = {"header": {}, "text": {}}
    path = Path(src_dir) / f"{safe}.pers.xml"
    if path.exists():
        root = ET.fromstring(path.read_text(encoding="utf-8", errors="replace")); node = root.find(".//PERS")
        if node is not None:
            for c in node:
                if c.tag.upper() == "PERS_REG": meta["header"] = _row(c)
                elif c.tag.upper() == "PERS_REG_TEXT": meta["text"] = _row(c)
    sources.pers_meta = meta
    return sources
