"""ICF service metadata collection for abapGit transport generation."""

import html
from pathlib import Path
from typing import Type
from defusedxml import ElementTree as ET
from defusedxml.common import DefusedXmlException

from transport_templates import ICF_NODES_NAME, icf_nodes


def parse_sicf_xml(xml_path) -> dict:
    """
    Read the abapGit .sicf.xml metadata: <URL>, the service header
    (<ICFSERVICE>: ICF_NAME/ORIG_NAME/ICFALTNME/ICFALTNME_ORIG), the
    description (<ICFDOCU>: ICF_NAME/ICF_LANGU/ICF_DOCU), and the handler
    list (<ICFHANDLER_TABLE><ICFHANDLER>: ICF_NAME/ICFORDER/ICFTYP/
    ICFHANDLER).

    Returns {url, icf_name, orig_name, icfaltnme, icfaltnme_orig,
    ddlanguage, ddtext, handlers: [...]}. A tag not present in the XML is
    simply absent from the returned dict -- the caller (_regenerate_sicf_rows
    in abapgit_to_transport.py) decides what to do, per field, same
    convention every other *_xml parser in this file uses.

    Schema confirmed against all 8 real local .sicf.xml files found on this
    machine (two unrelated projects) plus abapGit's own
    zcl_abapgit_object_sicf.clas.abap source (fetched from GitHub) -- not
    guessed from memory, per this project's standing rule. ICFPARGUID/
    ICFNODGUID are deliberately NOT looked for here: neither ever appears
    in a real .sicf.xml (abapGit's SERIALIZE method explicitly CLEARs both
    before writing the XML).
    """
    out = {"url": "", "icf_name": "", "orig_name": "", "icfaltnme": "",
           "icfaltnme_orig": "", "ddlanguage": "", "ddtext": "",
           "handlers": []}
    if xml_path is None or not Path(xml_path).exists():
        return out
    text = Path(xml_path).read_text(encoding="utf-8", errors="replace")
    try:
        root = ET.fromstring(text)
    except (ET.ParseError, DefusedXmlException) as exc:
        print(f"  WARNING: could not parse {Path(xml_path).name}: {exc}")
        return out

    url_el = root.find(".//URL")
    if url_el is not None and url_el.text is not None:
        out["url"] = html.unescape(url_el.text.strip())

    icfservice = root.find(".//ICFSERVICE")
    # Every serialized column: abapGit omits initial fields, so a column
    # missing here is initial on the source system.
    out["icfservice"] = {
        child.tag: html.unescape((child.text or "").strip())
        for child in (icfservice if icfservice is not None else [])
    }
    if icfservice is not None:
        for tag, key in (("ICF_NAME", "icf_name"), ("ORIG_NAME", "orig_name"),
                          ("ICFALTNME", "icfaltnme"),
                          ("ICFALTNME_ORIG", "icfaltnme_orig")):
            el = icfservice.find(tag)
            if el is not None and el.text is not None:
                out[key] = html.unescape(el.text.strip())

    icfdocu = root.find(".//ICFDOCU")
    if icfdocu is not None:
        for tag, key in (("ICF_LANGU", "ddlanguage"), ("ICF_DOCU", "ddtext")):
            el = icfdocu.find(tag)
            if el is not None and el.text is not None:
                out[key] = html.unescape(el.text.strip())

    handler_table = root.find(".//ICFHANDLER_TABLE")
    if handler_table is not None:
        for item in handler_table.findall("ICFHANDLER"):
            handler = {}
            for tag in ("ICFORDER", "ICFTYP", "ICFHANDLER"):
                el = item.find(tag)
                if el is not None and el.text is not None:
                    handler[tag] = html.unescape(el.text.strip())
            if handler.get("ICFHANDLER"):
                out["handlers"].append(handler)
    return out


_HEX = frozenset("0123456789ABCDEF")
_BASE36 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def sicf_object_name(file_object_name: str, meta: dict) -> str:
    """
    The transport object name of an ICF service: ICF_NAME (15 characters,
    space-padded) + the parent node's GUID (25).

    The file name does not say it. abapGit names the file <ICF_NAME><25
    characters of a hash of the service URL> -- lowercase hex, stable across
    systems, and NOT a node GUID; written into ICFPARGUID it yields a
    service hanging below a node that does not exist. The parent is the
    node at the XML's <URL> (abapGit stores the PARENT's URL there). Only a
    25-character part that cannot be a hex hash is taken as a GUID as is.
    """
    name = (meta.get("icf_name") or file_object_name[:15]).strip().upper()
    hash_part = file_object_name[15:].strip().upper()
    if len(hash_part) == 25 and not set(hash_part) <= _HEX:
        return name.ljust(15) + hash_part
    parent_url = (meta.get("url") or "").strip().rstrip("/").lower()
    nodes = icf_nodes()
    if not meta.get("url") or parent_url not in nodes:
        raise ValueError(
            f"SICF {name}: cannot determine the parent ICF node. Its "
            f".sicf.xml gives the parent URL {meta.get('url')!r}, which is "
            f"not in {ICF_NODES_NAME} of the template directory. Add the "
            f"node's ICFNODGUID from table ICFSERVICE of the target system "
            f"(known: {', '.join(sorted(k for k in nodes if k)) or 'none'}).")
    return name.ljust(15) + nodes[parent_url]


def sicf_node_guid(object_name: str) -> str:
    """A node GUID for the service itself: 25 characters 0-9A-Z, derived
    from the object name so re-generating the same service yields the same
    node, and two services never share one."""
    import hashlib
    number = int.from_bytes(hashlib.sha256(
        object_name.encode("utf-8")).digest(), "big")
    out = ""
    for _ in range(25):
        number, digit = divmod(number, 36)
        out += _BASE36[digit]
    return out


def collect_sicf_sources(src_dir: Path, obj_name: str, safe: str,
                         source_set_type: Type[dict]) -> dict[str, str]:
    """Collect ICF service metadata from abapGit's .sicf.xml file."""
    sources = source_set_type()
    sicf_xml = src_dir / f"{safe}.sicf.xml"
    sources.sicf_meta = parse_sicf_xml(sicf_xml)
    if not sources.sicf_meta.get("icf_name"):
        print(f"  WARNING: no <ICFSERVICE> metadata found in {sicf_xml.name}")
    return sources
