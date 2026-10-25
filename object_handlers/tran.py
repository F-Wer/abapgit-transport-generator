"""Transaction code metadata collection for abapGit transport generation."""

import html
import re
from pathlib import Path
from typing import Type


_TRAN_TAG_RE = re.compile(
    r"<([A-Za-z0-9_]+)\s*/>|<([A-Za-z0-9_]+)>([^<]*)</\2>")


def parse_tran_xml(xml_path: Path) -> dict:
    """Read abapGit .tran.xml metadata from TSTC-family sub-blocks."""
    out = {"TSTC": {}, "TSTCC": {}, "TSTCT": {}, "TSTCP": None}
    if xml_path is None or not Path(xml_path).exists():
        return out
    text = Path(xml_path).read_text(encoding="utf-8", errors="replace")
    for table in ("TSTC", "TSTCC", "TSTCT", "TSTCP"):
        match = re.search(rf"<{table}>(.*?)</{table}>", text,
                          re.IGNORECASE | re.DOTALL)
        if not match:
            continue
        fields = {}
        for tag in _TRAN_TAG_RE.finditer(match.group(1)):
            if tag.group(1):
                fields[tag.group(1).upper()] = ""
            else:
                fields[tag.group(2).upper()] = html.unescape(tag.group(3).strip())
        out[table] = fields
    return out


def collect_tran_sources(src_dir: Path, obj_name: str, safe: str,
                         source_set_type: Type[dict]) -> dict[str, str]:
    """Collect transaction metadata from abapGit's .tran.xml file."""
    sources = source_set_type()
    tran_xml = src_dir / f"{safe}.tran.xml"
    sources.tran_fields = parse_tran_xml(tran_xml)
    if not sources.tran_fields.get("TSTC"):
        print(f"  WARNING: no <TSTC> metadata found in {tran_xml.name}")
    return sources
