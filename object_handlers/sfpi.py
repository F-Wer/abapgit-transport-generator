"""Adobe form interface metadata collection for transport generation.

See object_handlers/sfpf.py for the transport representation.  The
interface graph is preserved as the ABAP XML serialized by abapGit.
"""

import html
import re
from pathlib import Path
from typing import Type


def parse_sfpi_xml(xml_path) -> dict:
    """
    Read the abapGit .sfpi.xml metadata. See object_handlers/sfpf.py's
    module docstring for the full schema and why this generator does not
    regenerate any FP* table content from it.

    Returns {"header": {tag: value, ...} (flat scalars actually present --
    VERSION/TYPE), "interface_text": the <FPINTERFACET><TEXT> value if
    present (else None), "has_interface_object": bool (an
    <INTERFACE href=...> reference is present -- the parameter list +
    ABAP coding, CL_FP_INTERFACE_DATA)}.
    """
    out = {"header": {}, "interface_text": None,
           "has_interface_object": False, "interface_xml": ""}
    if xml_path is None or not Path(xml_path).exists():
        return out
    text = Path(xml_path).read_text(encoding="utf-8", errors="replace")
    values_m = re.search(r"<asx:values>(.*?)</asx:values>", text, re.DOTALL)
    if not values_m:
        return out
    values = values_m.group(1)
    for tag in ("VERSION", "TYPE"):
        m = re.search(rf"<{tag}>([^<]*)</{tag}>", values, re.IGNORECASE)
        if m:
            out["header"][tag] = html.unescape(m.group(1).strip())
        elif re.search(rf"<{tag}\s*/>", values, re.IGNORECASE):
            out["header"][tag] = ""
    intt_m = re.search(r"<FPINTERFACET>(.*?)</FPINTERFACET>", values, re.DOTALL)
    if intt_m:
        text_m = re.search(r"<TEXT>([^<]*)</TEXT>", intt_m.group(1))
        if text_m:
            out["interface_text"] = html.unescape(text_m.group(1).strip())
    out["has_interface_object"] = bool(
        re.search(r"<INTERFACE\s+href=", values, re.IGNORECASE))
    abap_m = re.search(r"(<asx:abap\b[^>]*>.*?</asx:abap>)", text,
                       re.DOTALL | re.IGNORECASE)
    heap_m = re.search(r"(<asx:heap\b[^>]*>.*?</asx:heap>)", text,
                       re.DOTALL | re.IGNORECASE)
    root = re.search(r"(<INTERFACE\b[^>]*/>)", values, re.IGNORECASE)
    if abap_m and heap_m and root:
        start = abap_m.group(1).split("<asx:values", 1)[0]
        out["interface_xml"] = ('<?xml version="1.0" encoding="utf-8"?>' + start
                                 + "<asx:values>" + root.group(1) + "</asx:values>"
                                 + heap_m.group(1) + "</asx:abap>")
    return out


def collect_sfpi_sources(src_dir: Path, obj_name: str, safe: str,
                         source_set_type: Type[dict]) -> dict[str, str]:
    """Collect Adobe form interface metadata from abapGit's .sfpi.xml file."""
    sources = source_set_type()
    sfpi_xml = src_dir / f"{safe}.sfpi.xml"
    sources.sfpi_meta = parse_sfpi_xml(sfpi_xml)
    if not sfpi_xml.exists():
        print(f"  WARNING: no {sfpi_xml.name} found")
    elif not sources.sfpi_meta.get("header"):
        print(f"  WARNING: no <asx:values> metadata found in "
              f"{sfpi_xml.name}")
    return sources
