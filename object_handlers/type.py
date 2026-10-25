"""Type group source/metadata collection for abapGit transport generation."""

import html
import re
from pathlib import Path
from typing import Callable, Type

BuildReposKey = Callable[[str, str, str], str]
MakeTypePoolBoilerplate = Callable[[str], str]


def parse_type_xml(xml_path: Path) -> dict:
    """Read abapGit .type.xml metadata: the type group's short text."""
    if xml_path is None or not Path(xml_path).exists():
        return {}
    text = Path(xml_path).read_text(encoding="utf-8", errors="replace")
    match = re.search(r"<DDTEXT>(.*?)</DDTEXT>", text,
                      re.IGNORECASE | re.DOTALL)
    if match:
        return {"DDTEXT": html.unescape(match.group(1).strip())}
    if re.search(r"<DDTEXT\s*/>", text, re.IGNORECASE):
        return {"DDTEXT": ""}
    return {}


def collect_type_sources(src_dir: Path, obj_name: str, safe: str,
                         build_repos_key: BuildReposKey,
                         make_type_pool_boilerplate: MakeTypePoolBoilerplate,
                         source_set_type: Type[dict]) -> dict[str, str]:
    """Collect type group metadata and source from abapGit TYPE files."""
    if len(obj_name) > 5:
        raise ValueError(
            f"TYPE object name too long for DDTYPET-TYPEGROUP "
            f"({len(obj_name)} > 5 chars): {obj_name!r} -- SAP type "
            f"groups (TYPE-POOLS) are limited to 5-character names")
    sources = source_set_type()
    type_xml = src_dir / f"{safe}.type.xml"
    sources.type_meta = parse_type_xml(type_xml)
    if not type_xml.exists():
        print(f"  WARNING: no {type_xml.name} found")
    c_key = build_repos_key("TYPE", obj_name, "C")
    tt_key = build_repos_key("TYPE", obj_name, "TT")
    # A type group's declarations live in its '%_C<name>' program, behind
    # the TYPE-POOL statement; the '...TT' include stays empty (verified
    # against a real non-empty type group export, R3TR TYPE ZARCU). Putting
    # the body into TT instead ships a type group that declares nothing.
    type_abap = src_dir / f"{safe}.type.abap"
    body = type_abap.read_text(encoding="utf-8") if type_abap.exists() else ""
    if not re.search(r"^\s*TYPE-POOL\s", body, re.IGNORECASE | re.MULTILINE):
        body = make_type_pool_boilerplate(obj_name) + ("\n" + body if body else "")
    sources[c_key] = body
    sources[tt_key] = ""
    return sources
