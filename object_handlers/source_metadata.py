"""Shared helpers for source-code object collectors (CLAS/INTF)."""

import html
import re
from pathlib import Path


class TextSourceSet(dict):
    """Include sources plus the program's text pools read from the object's
    abapGit XML: {language: [(ID, KEY, ENTRY, LENGTH), ...]}."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.textpools = {}


class SeoSourceSet(TextSourceSet):
    """Include sources plus the class/interface header fields (VSEOCLASS /
    VSEOINTERF) read from the object's abapGit XML."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.seo_meta = {}


def _tpool_items(block: str) -> list:
    items = []
    for item in re.finditer(r"<item>(.*?)</item>", block, re.DOTALL):
        fields = {m.group(1).upper(): html.unescape(m.group(2))
                  for m in re.finditer(r"<(\w+)>([^<]*)</\1>", item.group(1))}
        if not fields.get("ID"):
            continue
        entry = fields.get("ENTRY", "")
        length = int(fields.get("LENGTH") or 0) or len(entry)
        items.append((fields["ID"], fields.get("KEY", ""), entry, length))
    return items


def master_language(src_dir: Path) -> str:
    """The repo's master language from .abapgit.xml (searched upwards from
    the object's folder); 'E' when there is none."""
    for folder in [src_dir, *src_dir.parents][:6]:
        config = folder / ".abapgit.xml"
        if config.exists():
            m = re.search(r"<MASTER_LANGUAGE>(\w)</MASTER_LANGUAGE>",
                          config.read_text(encoding="utf-8-sig",
                                           errors="replace"))
            if m:
                return m.group(1)
    return "E"


def parse_textpools(xml_path: Path, src_dir: Path) -> dict:
    """Read <TPOOL> (master language) and <I18N_TPOOL> (translations) of an
    abapGit object XML as {language: [(ID, KEY, ENTRY, LENGTH), ...]}."""
    if not xml_path.exists():
        return {}
    text = xml_path.read_text(encoding="utf-8-sig", errors="replace")
    pools = {}
    i18n = re.search(r"<I18N_TPOOL>(.*)</I18N_TPOOL>", text, re.DOTALL)
    if i18n:
        for lang in re.finditer(
                r"<LANGUAGE>(\w)</LANGUAGE>\s*<TEXTPOOL>(.*?)</TEXTPOOL>",
                i18n.group(1), re.DOTALL):
            pools[lang.group(1)] = _tpool_items(lang.group(2))
        text = text[:i18n.start()] + text[i18n.end():]
    main = re.search(r"<TPOOL>(.*?)</TPOOL>", text, re.DOTALL)
    if main:
        pools[master_language(src_dir)] = _tpool_items(main.group(1))
    return {lang: items for lang, items in pools.items() if items}


def parse_seo_xml(xml_path: Path, node: str) -> dict:
    """Return the flat fields of <VSEOCLASS>/<VSEOINTERF> as {TAG: text}."""
    if not xml_path.exists():
        return {}
    text = xml_path.read_text(encoding="utf-8-sig", errors="replace")
    block = re.search(rf"<{node}>(.*?)</{node}>", text, re.DOTALL)
    if not block:
        return {}
    return {m.group(1).upper(): html.unescape(m.group(2)).strip()
            for m in re.finditer(r"<(\w+)>([^<]*)</\1>", block.group(1))}
