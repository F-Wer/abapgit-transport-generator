"""ABAP Query user-group metadata extraction."""
from pathlib import Path
from defusedxml import ElementTree as ET
from defusedxml.common import DefusedXmlException

def collect_aqbg_sources(src_dir, obj_name, safe, source_set_type):
    sources = source_set_type(); sources.aqbg_meta = {}
    path = src_dir / f"{safe}.aqbg.xml"
    if path.exists():
        try:
            root = ET.fromstring(path.read_text(encoding="utf-8", errors="replace"))
            row = root.find(".//AQGDBBG")
            if row is not None:
                sources.aqbg_meta = {x.tag.upper():(x.text or "").strip() for x in row}
        except (ET.ParseError, DefusedXmlException): pass
    return sources
