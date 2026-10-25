"""SUCU authorization-group XML collection."""

import html
from pathlib import Path
from defusedxml import ElementTree as ET


def _rows(section):
    return [{item.tag.upper(): html.unescape((item.text or "").strip())
             for item in row if not list(item)} for row in section]


def collect_sucu_sources(src_dir, obj_name, safe, source_set_type):
    """Read the generic abapGit table collections from .sucu.xml."""
    sources = source_set_type()
    meta = {"auth": [], "texts": []}
    path = Path(src_dir) / f"{safe}.sucu.xml"
    if path.exists():
        root = ET.fromstring(path.read_text(encoding="utf-8", errors="replace"))
        node = root.find(".//SUCU")
        if node is not None:
            auth = node.find("TBRG_AUTH")
            texts = node.find("TBRG_AUTHT")
            if auth is not None:
                meta["auth"] = _rows(auth)
            if texts is not None:
                meta["texts"] = _rows(texts)
    sources.sucu_meta = meta
    return sources
