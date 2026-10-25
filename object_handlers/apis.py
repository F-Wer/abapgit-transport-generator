"""API release-state (APIS) metadata collection."""

import html
from pathlib import Path
from typing import Any, Type
from defusedxml import ElementTree as ET
from defusedxml.common import DefusedXmlException


def _fields(element: Any) -> dict[str, str]:
    return {child.tag.upper(): html.unescape((child.text or "").strip())
            for child in element if len(child) == 0}


def parse_apis_xml(xml_path: Path) -> dict:
    """Read abapGit's APIS header and release-state table."""
    out = {"header": {}, "states": []}
    if xml_path is None or not Path(xml_path).exists():
        return out
    try:
        root = ET.fromstring(Path(xml_path).read_text(encoding="utf-8", errors="replace"))
    except (ET.ParseError, DefusedXmlException) as exc:
        print(f"  WARNING: could not parse {Path(xml_path).name}: {exc}")
        return out
    apis = root.find(".//APIS")
    if apis is None:
        return out
    out["header"] = _fields(apis)
    states = apis.find("API_STATES")
    if states is not None:
        out["states"] = [_fields(row) for row in states if len(row)]
    return out


def collect_apis_sources(src_dir: Path, obj_name: str, safe: str,
                         source_set_type: Type[dict]) -> dict[str, str]:
    sources = source_set_type()
    xml_path = src_dir / f"{safe}.apis.xml"
    sources.apis_meta = parse_apis_xml(xml_path)
    if not sources.apis_meta["header"]:
        print(f"  WARNING: no <APIS> metadata found in {xml_path.name}")
    return sources
