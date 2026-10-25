"""Domain metadata collection for abapGit transport generation."""

import html
from pathlib import Path
from typing import Type
from defusedxml import ElementTree as ET
from defusedxml.common import DefusedXmlException


def parse_doma_xml(xml_path: Path) -> dict:
    """Read abapGit .doma.xml metadata from DD01V and DD07V_TAB."""
    out = {"header": {}, "values": []}
    if xml_path is None or not Path(xml_path).exists():
        return out
    text = Path(xml_path).read_text(encoding="utf-8", errors="replace")
    try:
        root = ET.fromstring(text)
    except (ET.ParseError, DefusedXmlException) as exc:
        print(f"  WARNING: could not parse {Path(xml_path).name}: {exc}")
        return out

    dd01v = root.find(".//DD01V")
    if dd01v is not None:
        for element in dd01v:
            tag = element.tag.upper()
            if tag == "DOMNAME":
                continue
            out["header"][tag] = html.unescape((element.text or "").strip())

    dd07v_tab = root.find(".//DD07V_TAB")
    if dd07v_tab is not None:
        for item in dd07v_tab.findall("DD07V"):
            entry = {}
            for element in item:
                tag = element.tag.upper()
                if tag == "DOMNAME":
                    continue
                entry[tag] = html.unescape((element.text or "").strip())
            if entry.get("VALPOS"):
                out["values"].append(entry)
    return out


def collect_doma_sources(src_dir: Path, obj_name: str, safe: str,
                         source_set_type: Type[dict]) -> dict[str, str]:
    """Collect domain metadata from abapGit's .doma.xml file."""
    sources = source_set_type()
    doma_xml = src_dir / f"{safe}.doma.xml"
    sources.doma_meta = parse_doma_xml(doma_xml)
    if not sources.doma_meta.get("header"):
        print(f"  WARNING: no <DD01V> metadata found in {doma_xml.name}")
    return sources
