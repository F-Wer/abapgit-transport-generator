"""Data element metadata collection for abapGit transport generation."""

import html
import re
from pathlib import Path
from typing import Type


_DTEL_TAG_RE = re.compile(r"<([A-Za-z0-9_]+)\s*/>|<([A-Za-z0-9_]+)>(.*?)</\2>",
                          re.DOTALL)


def parse_dtel_xml(xml_path: Path) -> dict:
    """Read abapGit .dtel.xml metadata from the <DD04V> element."""
    if xml_path is None or not Path(xml_path).exists():
        return {}
    text = Path(xml_path).read_text(encoding="utf-8", errors="replace")
    match = re.search(r"<DD04V>(.*?)</DD04V>", text,
                      re.IGNORECASE | re.DOTALL)
    if not match:
        return {}
    fields = {}
    for tag in _DTEL_TAG_RE.finditer(match.group(1)):
        if tag.group(1):
            fields[tag.group(1).upper()] = ""
        else:
            fields[tag.group(2).upper()] = html.unescape(tag.group(3).strip())
    return fields


def collect_dtel_sources(src_dir: Path, obj_name: str, safe: str,
                         source_set_type: Type[dict]) -> dict[str, str]:
    """Collect data element metadata from abapGit's .dtel.xml file."""
    sources = source_set_type()
    dtel_xml = src_dir / f"{safe}.dtel.xml"
    sources.dtel_fields = parse_dtel_xml(dtel_xml)
    if not sources.dtel_fields:
        print(f"  WARNING: no <DD04V> metadata found in {dtel_xml.name}")
    return sources
