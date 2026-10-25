"""Enhancement implementation metadata/source collection for transport generation."""

import html
from pathlib import Path
from typing import Callable, Type
from defusedxml import ElementTree as ET
from defusedxml.common import DefusedXmlException

BuildReposKey = Callable[[str, str, str], str]
MakeMasterIncludeSource = Callable[[str, dict], str]


def parse_enho_xml(xml_path) -> dict:
    """
    Read the abapGit .enho.xml metadata. Two TOOL values are supported,
    real content for both confirmed against a genuine independently-
    exported transport the user delivered 2026-08-25 (see
    DOMA_VIEW_TYPE_ENHO_BADI_PROGRESS.md):

    TOOL=CLASENH (class enhancement -- adds a new method to an existing
    class): <TOOL>, <SHORTTEXT>, <CLASS>, and <TAB_METHODS> (a list of new
    methods, each with its own METHKEY/METH_HEADER/METH_PARAM). Returns
    "methods": [...] -- each method dict is {"name", "descript", "exposure",
    "state", "editorder", "mtddecltyp", "params": [...]}, each param dict
    is {"sconame", "descript", "editorder", "parpasstyp", "typtype",
    "type"}.

    TOOL=BADI_IMPL (a BAdI implementation -- declarative, no ABAP source at
    all): <TOOL>, <SHORTTEXT>, <SPOT_NAME>, and <IMPL/ENH_BADI_IMPL_DATA>
    (BADI_NAME/IMPL_NAME/IMPL_CLASS/ACTIVE/IMPL_SHORTTEXT, plus
    FILTER_ROOT -- a list of {root, filters: [{name, id}]} -- and
    FILTER_VALUES -- a list of {id, name, type, compare, char_value,
    numeric_value}). Returns "badi": {...} with these fields; "methods" is
    always empty for this TOOL. <FILTERS> (the flattened disjunct/conjunct
    view of the same filter data FILTER_ROOT/FILTER_VALUES already carry)
    and <SOTR>/<SOTR_USE> (the long-text infrastructure behind
    IMPL_SHORTTEXT) are read by abapGit but NOT parsed here -- see
    _regenerate_enho_badi_data_blob's docstring (in abapgit_to_transport.py)
    for why FILTERS is redundant and SOTR is left as template boilerplate.

    Any other TOOL value populates tool/shorttext only -- the generator's
    TEMPLATES only cover CLASENH and BADI_IMPL, so a third TOOL simply gets
    no field-level content rewritten (documented limitation).
    """
    out = {"tool": "", "shorttext": "", "class": "", "methods": [],
           "badi": {}}
    if xml_path is None or not Path(xml_path).exists():
        return out
    text = Path(xml_path).read_text(encoding="utf-8", errors="replace")
    try:
        root = ET.fromstring(text)
    except (ET.ParseError, DefusedXmlException) as exc:
        print(f"  WARNING: could not parse {Path(xml_path).name}: {exc}")
        return out

    for tag, key in (("TOOL", "tool"), ("SHORTTEXT", "shorttext"),
                     ("CLASS", "class")):
        el = root.find(f".//{tag}")
        if el is not None and el.text is not None:
            out[key] = html.unescape(el.text.strip())

    for meth_data in root.findall(".//TAB_METHODS/ENHNEWMETH_DATA"):
        header = meth_data.find("METH_HEADER")
        if header is None:
            continue
        method = {"name": "", "descript": "", "exposure": "", "state": "",
                  "editorder": "", "mtddecltyp": "", "params": []}
        cmpname_el = header.find("CMPNAME")
        if cmpname_el is not None and cmpname_el.text:
            method["name"] = html.unescape(cmpname_el.text.strip())
        for tag, key in (("DESCRIPT", "descript"), ("EXPOSURE", "exposure"),
                         ("STATE", "state"), ("EDITORDER", "editorder"),
                         ("MTDDECLTYP", "mtddecltyp")):
            el = header.find(tag)
            if el is not None and el.text is not None:
                method[key] = html.unescape(el.text.strip())

        param_wrapper = meth_data.find("METH_PARAM")
        if param_wrapper is not None:
            for p in param_wrapper.findall("ENHMETHPARAM"):
                param = {"sconame": "", "descript": "", "editorder": "",
                        "parpasstyp": "", "typtype": "", "type": ""}
                for tag, key in (("SCONAME", "sconame"), ("DESCRIPT", "descript"),
                                 ("EDITORDER", "editorder"),
                                 ("PARPASSTYP", "parpasstyp"),
                                 ("TYPTYPE", "typtype"), ("TYPE", "type")):
                    el = p.find(tag)
                    if el is not None and el.text is not None:
                        param[key] = html.unescape(el.text.strip())
                method["params"].append(param)
        if method["name"]:
            out["methods"].append(method)

    impl_data = root.find(".//IMPL/ENH_BADI_IMPL_DATA")
    if impl_data is not None:
        badi = {"spot_name": "", "badi_name": "", "impl_name": "",
                "impl_class": "", "active": "", "impl_shorttext": "",
                "filter_root": [], "filter_values": []}
        for tag, key in (("SPOT_NAME", "spot_name"), ("BADI_NAME", "badi_name"),
                         ("IMPL_NAME", "impl_name"), ("IMPL_CLASS", "impl_class"),
                         ("ACTIVE", "active"),
                         ("IMPL_SHORTTEXT", "impl_shorttext")):
            el = impl_data.find(tag)
            if el is not None and el.text is not None:
                badi[key] = html.unescape(el.text.strip())

        for root_el in impl_data.findall("FILTER_ROOT/ENH_BADIIMPL_FILTER_ROOT"):
            root_id_el = root_el.find("ROOT")
            entry = {"root": (html.unescape(root_id_el.text.strip())
                              if root_id_el is not None and root_id_el.text
                              else ""), "filters": []}
            for f in root_el.findall("FILTERS/ENH_BADIIMPL_FILTER_ID"):
                name_el, id_el = f.find("FILTER_NAME"), f.find("ID")
                entry["filters"].append({
                    "name": (html.unescape(name_el.text.strip())
                             if name_el is not None and name_el.text else ""),
                    "id": (html.unescape(id_el.text.strip())
                          if id_el is not None and id_el.text else ""),
                })
            badi["filter_root"].append(entry)

        for v in impl_data.findall("FILTER_VALUES/ENH_BADIIMPL_FILTER_VALUE"):
            value = {"id": "", "filter_name": "", "filter_type": "",
                     "compare": "", "char_value1": "", "numeric_value1": ""}
            for tag, key in (("ID", "id"), ("FILTER_NAME", "filter_name"),
                             ("FILTER_TYPE", "filter_type"),
                             ("COMPARE", "compare"),
                             ("FILTER_CHAR_VALUE1", "char_value1"),
                             ("FILTER_NUMERIC_VALUE1", "numeric_value1")):
                el = v.find(tag)
                if el is not None and el.text is not None:
                    value[key] = html.unescape(el.text.strip())
            badi["filter_values"].append(value)

        out["badi"] = badi
    return out


def collect_enho_sources(src_dir: Path, obj_name: str, safe: str,
                         build_repos_key: BuildReposKey,
                         make_master_include_source: MakeMasterIncludeSource,
                         source_set_type: Type[dict]) -> dict[str, str]:
    """Collect enhancement implementation metadata and method sources."""
    sources = source_set_type()
    enho_xml = src_dir / f"{safe}.enho.xml"
    sources.enho_meta = parse_enho_xml(enho_xml)
    tool = sources.enho_meta.get("tool")
    if tool == "BADI_IMPL":
        if not sources.enho_meta.get("badi"):
            print(f"  WARNING: no <IMPL/ENH_BADI_IMPL_DATA> metadata "
                  f"found in {enho_xml.name}")
    elif not sources.enho_meta.get("methods"):
        print(f"  WARNING: no <TAB_METHODS> metadata found in "
              f"{enho_xml.name} (TOOL={tool!r} -- only CLASENH and "
              f"BADI_IMPL are supported)")
    else:
        master_key = build_repos_key("ENHO", obj_name, "E")
        sources[master_key] = make_master_include_source(
            obj_name, sources.enho_meta)
        for index, method in enumerate(sources.enho_meta["methods"], start=1):
            method_name = method.get("name", "")
            if not method_name:
                continue
            file_path = src_dir / f"{safe}.enho.em_{method_name.lower()}.abap"
            include_key = build_repos_key("ENHO", obj_name, f"EM{index:03d}")
            if file_path.exists():
                sources[include_key] = file_path.read_text(encoding="utf-8")
            else:
                print(f"  WARNING: no {file_path.name} found for method "
                      f"{method_name!r} -- its REPOS block cannot be shipped")
    return sources
