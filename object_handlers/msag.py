"""Message class metadata collection for abapGit transport generation."""

from pathlib import Path
from typing import Type
from defusedxml import ElementTree as ET
from defusedxml.common import DefusedXmlException


def parse_msag_xml(xml_path: Path) -> dict:
    """Read abapGit .msag.xml metadata: T100A header and T100 messages."""
    out = {"masterlang": "", "stext": "", "messages": []}
    if xml_path is None or not Path(xml_path).exists():
        return out
    text = Path(xml_path).read_text(encoding="utf-8", errors="replace")
    try:
        root = ET.fromstring(text)
    except (ET.ParseError, DefusedXmlException) as exc:
        print(f"  WARNING: could not parse {Path(xml_path).name}: {exc}")
        return out

    t100a = root.find(".//T100A")
    if t100a is not None:
        master_lang = t100a.find("MASTERLANG")
        short_text = t100a.find("STEXT")
        out["masterlang"] = ((master_lang.text or "").strip()
                             if master_lang is not None else "")
        out["stext"] = ((short_text.text or "").strip()
                        if short_text is not None else "")

    t100_wrapper = root.find(".//T100")
    if t100_wrapper is not None:
        for item in t100_wrapper.findall("T100"):
            msgnr_el = item.find("MSGNR")
            text_el = item.find("TEXT")
            msgnr = ((msgnr_el.text or "").strip()
                     if msgnr_el is not None else "")
            msg_text = (text_el.text or "") if text_el is not None else ""
            if msgnr:
                out["messages"].append((msgnr.rjust(3, "0"), msg_text))
    return out


def collect_msag_sources(src_dir: Path, obj_name: str, safe: str,
                         source_set_type: Type[dict]) -> dict[str, str]:
    """Collect message class metadata from abapGit's .msag.xml file."""
    sources = source_set_type()
    msag_xml = src_dir / f"{safe}.msag.xml"
    meta = parse_msag_xml(msag_xml)
    sources.msag_masterlang = meta["masterlang"]
    sources.msag_stext = meta["stext"]
    sources.msag_messages = meta["messages"]
    if not meta["messages"]:
        print(f"  WARNING: no messages found in {msag_xml.name}")
    return sources
