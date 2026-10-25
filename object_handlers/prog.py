"""Report/program source collection for abapGit transport generation."""

import re
from pathlib import Path
from typing import Callable

from object_handlers.source_metadata import TextSourceSet, parse_textpools

BuildReposKey = Callable[[str, str, str], str]


def collect_prog_sources(src_dir: Path, obj_name: str, safe: str,
                         _build_repos_key: BuildReposKey) -> dict[str, str]:
    """Collect one program's source, type and text pools."""
    sources = TextSourceSet()
    sources.textpools = parse_textpools(src_dir / f"{safe}.prog.xml", src_dir)
    xml_path = src_dir / f"{safe}.prog.xml"
    # program type: 1 executable, I include, M module pool, S subroutine pool
    match = (re.search(r"<SUBC>(\w)</SUBC>",
                       xml_path.read_text(encoding="utf-8-sig", errors="replace"))
             if xml_path.exists() else None)
    sources.prog_subc = match.group(1) if match else "1"
    main_file = src_dir / f"{safe}.prog.abap"
    if main_file.exists():
        sources[obj_name] = main_file.read_text(encoding="utf-8")
    return sources
