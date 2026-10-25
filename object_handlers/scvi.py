"""SCVI screen-variant XML collection."""
import html
from pathlib import Path
from defusedxml import ElementTree as ET
def _row(n): return {c.tag.upper(): html.unescape((c.text or '').strip()) for c in n if not list(c)}
def _rows(n): return [_row(c) for c in n if list(c)]
def collect_scvi_sources(src_dir,obj_name,safe,source_set_type):
 s=source_set_type(); m={'header':{},'texts':[],'values':[],'guixt':[],'tcodes':[]}; p=Path(src_dir)/f'{safe}.scvi.xml'
 if p.exists():
  root=ET.fromstring(p.read_text(encoding='utf-8',errors='replace')); n=root.find('.//SCVI')
  if n is not None:
   for c in n:
    k=c.tag.upper();
    if k=='SHDSVCI':m['header']=_row(c)
    elif k in ('SHDSVTXCI','SHDSVFVCI','SHDGUIXT','SHDGXTCODE'):m[{'SHDSVTXCI':'texts','SHDSVFVCI':'values','SHDGUIXT':'guixt','SHDGXTCODE':'tcodes'}[k]]=_rows(c)
 s.scvi_meta=m; return s
