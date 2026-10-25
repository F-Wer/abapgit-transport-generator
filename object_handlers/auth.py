"""Authorization-field (AUTH) XML extraction."""
import html
from pathlib import Path
from typing import Type
from defusedxml import ElementTree as ET
from defusedxml.common import DefusedXmlException

def collect_auth_sources(src_dir: Path, obj_name: str, safe: str,
                         source_set_type: Type[dict]) -> dict[str, str]:
    sources = source_set_type(); sources.auth_meta = {}
    path = src_dir / f"{safe}.auth.xml"
    if path.exists():
        try:
            node = ET.fromstring(path.read_text(encoding="utf-8", errors="replace")).find(".//AUTHX")
            if node is not None:
                sources.auth_meta = {x.tag.upper(): html.unescape((x.text or "").strip()) for x in node if len(x) == 0}
        except (ET.ParseError, DefusedXmlException) as exc:
            print(f"  WARNING: could not parse {path.name}: {exc}")
    return sources
