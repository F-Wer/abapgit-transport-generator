"""ABAP transformation metadata collection for transport generation."""

from pathlib import Path
from typing import Type
from defusedxml import ElementTree as ET
from defusedxml.common import DefusedXmlException


def parse_xslt_xml(xml_path) -> dict:
    """
    Parse a real .xslt.xml (ATTRIBUTES: XSLTDESC/LANGU/DESCRIPT) plus its
    sibling <name>.xslt.source.xml (the actual transformation body, read
    as raw text -- never re-serialized through an XML parser, so its exact
    original formatting/whitespace is preserved byte-for-byte, matching
    the "inject real source verbatim" discipline every source-carrying
    type in this project already follows for REPOS blocks).
    """
    result = {"xsltdesc": "", "langu": "", "descript": "", "source": ""}
    if not xml_path.exists():
        return result
    try:
        root = ET.fromstring(xml_path.read_text(encoding="utf-8"))
    except (ET.ParseError, DefusedXmlException):
        return result
    attrs = root.find(".//ATTRIBUTES")
    if attrs is not None:
        for tag, key in (("XSLTDESC", "xsltdesc"), ("LANGU", "langu"),
                         ("DESCRIPT", "descript")):
            el = attrs.find(tag)
            if el is not None and el.text:
                result[key] = el.text

    source_path = xml_path.with_name(
        xml_path.name[:-len(".xslt.xml")] + ".xslt.source.xml")
    if source_path.exists():
        result["source"] = source_path.read_text(encoding="utf-8")
    return result


def collect_xslt_sources(src_dir: Path, obj_name: str, safe: str,
                         source_set_type: Type[dict]) -> dict[str, str]:
    """Collect transformation metadata and source from abapGit XSLT files."""
    sources = source_set_type()
    xslt_xml = src_dir / f"{safe}.xslt.xml"
    sources.xslt_meta = parse_xslt_xml(xslt_xml)
    if not sources.xslt_meta.get("xsltdesc"):
        print(f"  WARNING: no <ATTRIBUTES> metadata found in {xslt_xml.name}")
    if not sources.xslt_meta.get("source"):
        print(f"  WARNING: no {safe}.xslt.source.xml found -- the "
              f"transformation source will not be rewritten (shipping "
              f"the template's own stale content)")
    return sources
