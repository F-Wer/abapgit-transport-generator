"""Class source collection for abapGit transport generation."""

from pathlib import Path
from typing import Callable

from object_handlers.source_metadata import (SeoSourceSet, parse_seo_xml,
                                         parse_textpools)

BuildReposKey = Callable[[str, str, str], str]


def collect_clas_sources(src_dir: Path, obj_name: str, safe: str,
                         build_repos_key: BuildReposKey) -> dict[str, str]:
    """Collect class pool source files using abapGit's CLAS file naming."""
    sources = SeoSourceSet()
    sources.seo_meta = parse_seo_xml(src_dir / f"{safe}.clas.xml",
                                     "VSEOCLASS")
    sources.textpools = parse_textpools(src_dir / f"{safe}.clas.xml", src_dir)
    for suffix, include_suffix in [
        (".clas.abap", "CU"),          # split into CU/CI/CM### later
        (".clas.locals_def.abap", "CCDEF"),
        (".clas.locals_imp.abap", "CCIMP"),
        (".clas.macros.abap", "CCMAC"),
        (".clas.testclasses.abap", "CCAU"),   # CT is SAP's dummy include
    ]:
        file_path = src_dir / f"{safe}{suffix}"
        if file_path.exists():
            if include_suffix == "CU":
                # Keyed by the plain object name; class mapping splits it into
                # the CU/CI/CM### include contents later.
                sources[obj_name] = file_path.read_text(encoding="utf-8")
            else:
                include_key = build_repos_key("CLAS", obj_name, include_suffix)
                sources[include_key] = file_path.read_text(encoding="utf-8")
    return sources
