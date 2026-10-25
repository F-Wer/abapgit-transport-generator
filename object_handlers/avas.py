"""Attribute-value-assignment (AVAS) XML extraction."""
import html
from pathlib import Path
from typing import Type
from defusedxml import ElementTree as ET
from defusedxml.common import DefusedXmlException

def collect_avas_sources(src_dir: Path, obj_name: str, safe: str, source_set_type: Type[dict]) -> dict[str, str]:
    s=source_set_type();s.avas_meta={"header":{},"values":[]};p=src_dir/f"{safe}.avas.xml"
    if not p.exists(): return s
    try:r=ET.fromstring(p.read_text(encoding='utf-8',errors='replace'))
    except (ET.ParseError, DefusedXmlException) as e: print(f"  WARNING: could not parse {p.name}: {e}");return s
    n=r.find('.//AVAS')
    if n is None:return s
    h=n.find('HEADER')
    if h is not None:
        for x in h:
            if len(x)==0:s.avas_meta['header'][x.tag.upper()]=html.unescape((x.text or '').strip())
            else:
                for y in x:
                    if len(y)==0:s.avas_meta['header'][y.tag.upper()]=html.unescape((y.text or '').strip())
    v=n.find('VALUES')
    if v is not None:
        s.avas_meta['values']=[{x.tag.upper():html.unescape((x.text or '').strip()) for x in i if len(x)==0} for i in v]
    return s
