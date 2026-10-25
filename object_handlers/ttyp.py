"""Table type metadata collection for abapGit transport generation."""

import html
import re
from pathlib import Path
from typing import Type


_TTYP_TAG_RE = re.compile(r"<([A-Za-z0-9_]+)\s*/>|<([A-Za-z0-9_]+)>(.*?)</\2>",
                          re.DOTALL)


def parse_ttyp_xml(xml_path: Path) -> dict:
    """Read abapGit .ttyp.xml metadata from the <DD40V> element."""
    if xml_path is None or not Path(xml_path).exists():
        return {}
    text = Path(xml_path).read_text(encoding="utf-8", errors="replace")
    match = re.search(r"<DD40V>(.*?)</DD40V>", text,
                      re.IGNORECASE | re.DOTALL)
    if not match:
        return {}
    fields = {}
    for tag in _TTYP_TAG_RE.finditer(match.group(1)):
        if tag.group(1):
            fields[tag.group(1).upper()] = ""
        else:
            fields[tag.group(2).upper()] = html.unescape(tag.group(3).strip())
    return fields


def collect_ttyp_sources(src_dir: Path, obj_name: str, safe: str,
                         source_set_type: Type[dict]) -> dict[str, str]:
    """Collect table type metadata from abapGit's .ttyp.xml file."""
    sources = source_set_type()
    ttyp_xml = src_dir / f"{safe}.ttyp.xml"
    sources.ttyp_fields = parse_ttyp_xml(ttyp_xml)
    if not sources.ttyp_fields:
        print(f"  WARNING: no <DD40V> metadata found in {ttyp_xml.name}")
    return sources
