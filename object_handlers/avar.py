"""Activation-variant (AVAR) XML extraction."""
import html
from pathlib import Path
from typing import Type
from defusedxml import ElementTree as ET
from defusedxml.common import DefusedXmlException

def collect_avar_sources(src_dir: Path, obj_name: str, safe: str, source_set_type: Type[dict]) -> dict[str, str]:
    sources=source_set_type(); sources.avar_meta={"description":"","ids":[]}
    path=src_dir/f"{safe}.avar.xml"
    if not path.exists(): return sources
    try: root=ET.fromstring(path.read_text(encoding="utf-8",errors="replace"))
    except (ET.ParseError, DefusedXmlException) as exc: print(f"  WARNING: could not parse {path.name}: {exc}"); return sources
    sources.avar_meta["description"]=html.unescape((root.findtext('.//DESCRIPTION') or '').strip())
    ids=root.find('.//IDS')
    if ids is not None:
        for item in ids:
            row={x.tag.upper():html.unescape((x.text or '').strip()) for x in item if len(x)==0}
            if row: sources.avar_meta['ids'].append(row)
    return sources
