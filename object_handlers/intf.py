"""Interface source collection for abapGit transport generation."""

from pathlib import Path
from typing import Callable

from object_handlers.source_metadata import SeoSourceSet, parse_seo_xml

BuildReposKey = Callable[[str, str, str], str]


def collect_intf_sources(src_dir: Path, obj_name: str, safe: str,
                         build_repos_key: BuildReposKey) -> dict[str, str]:
    """Collect interface source files using abapGit's INTF file naming."""
    sources = SeoSourceSet()
    sources.seo_meta = parse_seo_xml(src_dir / f"{safe}.intf.xml",
                                     "VSEOINTERF")
    file_path = src_dir / f"{safe}.intf.abap"
    if file_path.exists():
        include_key = build_repos_key("INTF", obj_name, "IU")
        sources[include_key] = file_path.read_text(encoding="utf-8")
    return sources
