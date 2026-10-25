"""Classification attribute (CHAR) XML extraction."""
import html
from pathlib import Path
from typing import Type
from defusedxml import ElementTree as ET
from defusedxml.common import DefusedXmlException

TABLES=("CLS_ATTRIBUTE","CLS_ATTRIBUTET","CLS_ATTR_VALUE","CLS_ATTR_VALUET")
def collect_char_sources(src_dir: Path,obj_name: str,safe: str,source_set_type: Type[dict]) -> dict[str,str]:
 s=source_set_type();s.char_meta={};p=src_dir/f"{safe}.char.xml"
 if not p.exists(): return s
 try:r=ET.fromstring(p.read_text(encoding='utf-8',errors='replace'))
 except (ET.ParseError, DefusedXmlException):return s
 for table in TABLES:
  n=r.find(f'.//{table}')
  if n is None:continue
  direct={x.tag.upper():html.unescape((x.text or '').strip()) for x in n if len(x)==0}
  rows=[direct] if direct else [{x.tag.upper():html.unescape((x.text or '').strip()) for x in i if len(x)==0} for i in n]
  s.char_meta[table]=[x for x in rows if x]
 return s
