"""Checkpoint group (ACID) metadata collection."""

import html
from pathlib import Path
from typing import Type
from defusedxml import ElementTree as ET
from defusedxml.common import DefusedXmlException


def parse_acid_xml(xml_path: Path) -> dict:
    """Read abapGit's sole ACID field, ``<DESCRIPTION>``."""
    out = {"description": ""}
    if xml_path is None or not Path(xml_path).exists():
        return out
    try:
        root = ET.fromstring(Path(xml_path).read_text(
            encoding="utf-8", errors="replace"))
    except (ET.ParseError, DefusedXmlException) as exc:
        print(f"  WARNING: could not parse {Path(xml_path).name}: {exc}")
        return out
    description = root.find(".//DESCRIPTION")
    if description is not None and description.text is not None:
        out["description"] = html.unescape(description.text.strip())
    return out


def collect_acid_sources(src_dir: Path, obj_name: str, safe: str,
                         source_set_type: Type[dict]) -> dict[str, str]:
    """Collect metadata from an abapGit ``.acid.xml`` file."""
    sources = source_set_type()
    acid_xml = src_dir / f"{safe}.acid.xml"
    sources.acid_meta = parse_acid_xml(acid_xml)
    if not sources.acid_meta["description"]:
        print(f"  WARNING: no <DESCRIPTION> found in {acid_xml.name}; "
              "using the object name as the checkpoint-group description")
    return sources
