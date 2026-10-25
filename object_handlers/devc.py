"""Development package metadata collection for transport generation."""

from pathlib import Path
from typing import Type

from devc_helpers import parse_devc_xml


def collect_devc_sources(src_dir: Path, obj_name: str, safe: str,
                         source_set_type: Type[dict]) -> dict[str, str]:
    """Collect development package metadata from abapGit's .devc.xml file."""
    sources = source_set_type()
    devc_xml = src_dir / f"{safe}.devc.xml"
    sources.devc_meta = parse_devc_xml(devc_xml)
    if not devc_xml.exists():
        print(f"  WARNING: no {devc_xml.name} found")
    elif not sources.devc_meta.get("description"):
        print(f"  WARNING: no TDEVCT description found in {devc_xml.name}")
    print(f"  DEVC metadata from .devc.xml: "
          f"description={sources.devc_meta.get('description')!r}")
    return sources
