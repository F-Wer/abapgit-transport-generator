"""AMSD logical-database-schema XML extraction.

AMSD is serialized by abapGit as one dynamic ``<AMSD>`` workbench object.
This helper deliberately exposes its leaf fields without inventing a schema;
the transport writer can map only names present in the captured nametabs.
"""

import html
from pathlib import Path
from defusedxml import ElementTree as ET
from defusedxml.common import DefusedXmlException


def parse_amsd_xml(xml_path: Path) -> dict[str, str]:
    """Return uppercase leaf-element values from abapGit's ``<AMSD>`` node."""
    if xml_path is None or not Path(xml_path).exists():
        return {}
    try:
        root = ET.fromstring(Path(xml_path).read_text(encoding="utf-8", errors="replace"))
    except (ET.ParseError, DefusedXmlException) as exc:
        print(f"  WARNING: could not parse {Path(xml_path).name}: {exc}")
        return {}
    node = root.find(".//AMSD")
    if node is None:
        return {}
    return {leaf.tag.upper(): html.unescape((leaf.text or "").strip())
            for leaf in node.iter() if leaf is not node and len(leaf) == 0}


def collect_amsd_sources(src_dir, obj_name, safe, source_set_type):
    sources = source_set_type()
    sources.amsd_meta = parse_amsd_xml(src_dir / f"{safe}.amsd.xml")
    return sources
