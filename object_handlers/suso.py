"""SUSO authorization-object XML collection."""

import html
from pathlib import Path
from defusedxml import ElementTree as ET


def _row(node):
    return {child.tag.upper(): html.unescape((child.text or "").strip())
            for child in node if not list(child)}


def _rows(node):
    children = list(node)
    if not children:
        return []
    if all(not list(child) for child in children):
        return [_row(node)]
    return [_row(child) for child in children if list(child)]


def collect_suso_sources(src_dir, obj_name, safe, source_set_type):
    """Read the tables serialized by abapGit's SUSO object serializer."""
    sources = source_set_type()
    meta = {"tobj": {}, "tobjt": {}, "flags": {}, "tactz": [],
            "vordat": [], "vor": [], "abap_language_version": ""}
    path = Path(src_dir) / f"{safe}.suso.xml"
    if path.exists():
        root = ET.fromstring(path.read_text(encoding="utf-8", errors="replace"))
        node = root.find(".//SUSO")
        if node is not None:
            for child in node:
                tag = child.tag.upper()
                if tag == "TOBJ":
                    meta["tobj"] = _row(child)
                elif tag == "TOBJT":
                    meta["tobjt"] = _row(child)
                elif tag == "TOBJVORFLG":
                    meta["flags"] = _row(child)
                elif tag == "TACTZ":
                    meta["tactz"] = _rows(child)
                elif tag == "TOBJVORDAT":
                    meta["vordat"] = _rows(child)
                elif tag == "TOBJVOR":
                    meta["vor"] = _rows(child)
                elif tag == "ABAP_LANGUAGE_VERSION":
                    meta["abap_language_version"] = html.unescape((child.text or "").strip())
    sources.suso_meta = meta
    return sources
