"""Adobe print form metadata collection for transport generation.

Real .sfpf.xml / .sfpi.xml schema confirmed against abapGit's OWN
canonical round-trip test fixture (github.com/abapGit-tests/SFPF_SFPI,
src/zdemo_form.sfpf.xml + zdemo_form.sfpi.xml -- the project's official
test repo for this exact object-type pair, found via
`gh api "search/code?q=extension:sfpf.xml"`, not a guess).

The schema has TWO very different kinds of content:
  1. A handful of FLAT scalar fields directly inside <asx:values> --
     .sfpf.xml: VERSION/TYPE/INTERFACE (the bound SFPI's plain object
     name, e.g. <INTERFACE>ZDEMO_FORM</INTERFACE>)/OFFLINEHANDLER/
     DATAPROVIDER/FRTYPE/CNTSET/FNTEMB, plus a short-text wrapper
     (<CONTEXTT><FPCONTEXTT>NAME/STATE/LANGUAGE/ID/TEXT</FPCONTEXTT>
     </CONTEXTT>, the same per-object description convention MSAG/DOMA/
     TYPE/SHLP already use); .sfpi.xml: VERSION/TYPE plus the analogous
     <INTERFACET><FPINTERFACET>.../TEXT</FPINTERFACET></INTERFACET>.
  2. Two/one `href="#oN"` REFERENCES (.sfpf.xml: <CONTEXT>, <LAYOUT>;
     .sfpi.xml: <INTERFACE>) into a COMPLETELY SEPARATE <asx:heap>
     section holding serialized ABAP OBJECT INSTANCES -- CL_FP_CONTEXT/
     CL_FP_STRUCTURE/CL_FP_DATA/CL_FP_CONDITION node trees (the form's
     field-mapping definition), CL_FP_LAYOUT (translation type/cache
     info/layout type/form tech -- the form's *.xdp visual layout is a
     SEPARATE file, <safe>.sfpf.xdp, not inline here), and
     CL_FP_INTERFACE_DATA/CL_FP_PARAMETERS/CL_FP_CODING/CL_FP_GLOBAL_
     DEFINITIONS (the interface's actual parameter list + ABAP coding).
     This is NOT simple row data -- on the transport side it maps to
     FPCONTEXT.CONTEXT / FPLAYOUT.LAYOUT / FPLAYOUT.LAYOUTM /
     FPINTERFACE.INTERFACE, all declared as RAW/cluster-reference ('R'
     type) fields in the real nametab (confirmed directly against
     the reference export's own bytes), the same class of "serialized object
     cluster, not a fixed-width row" content ENHO's RAW long-value
     records already established this project cannot regenerate from an
     XML field list. See docs/sfpf-sfpi-support.md ("What is NOT
     implemented") for the full reasoning, including why the REAL
     reference object (the reference export's transformation and interface) demonstrates
     NO transport-side row content at all for ANY of the six FP* tables
     (FPCONTEXT/FPCONTEXTT/FPLAYOUT/FPLAYOUTT/FPINTERFACE/FPINTERFACET
     are every one of them a 0-row '00DELL' delete-sweep, never a
     '00REPC'/'00REP ' fill block) -- so this generator does not attempt
     row-level regeneration for ANY of them this round, not even the
     flat scalar fields under (1): there is no real transport-side row
     to verify the field-to-byte-offset mapping against, and TRAN's
     TSTCP precedent (_blank_row + '00DELL'->'00REP ' action flip) that
     would otherwise apply here runs into an unresolved risk unique to
     this object type -- FPCONTEXT and FPLAYOUT each carry their OWN
     0-row delete-sweep TWICE (once early, once in a later "trailer"
     group alongside ENHOBJ/SMODILOG/SMODISRC's own second occurrence),
     and flipping only the first to a fill row risks the second, later
     delete-sweep silently wiping the just-inserted content on import --
     a genuinely blocking correctness question this project has never
     had a live SAP import test to resolve for ANY round, so it is
     reported rather than guessed past (per the task brief's own
     standing instruction).

Native exports prove that the RAW values are the same ABAP XML
serialization that abapGit stores.  The collector therefore keeps the
serialized context/layout graphs and XDP payload for the row writer.
"""

import html
import re
from pathlib import Path
from typing import Type


def parse_sfpf_xml(xml_path) -> dict:
    """
    Read the abapGit .sfpf.xml metadata. See the module comment above for
    the full schema and why this generator does not regenerate any FP*
    table content from it.

    Returns {"header": {tag: value, ...} (flat scalars actually present --
    VERSION/TYPE/INTERFACE/OFFLINEHANDLER/DATAPROVIDER/FRTYPE/CNTSET/
    FNTEMB), "context_text": the <FPCONTEXTT><TEXT> value if present (else
    None), "has_context_object": bool (a <CONTEXT href=...> reference is
    present), "has_layout_object": bool (a <LAYOUT href=...> reference is
    present)}.
    """
    out = {"header": {}, "context_text": None,
           "has_context_object": False, "has_layout_object": False,
           "context_xml": "", "layout_xml": "", "xdp": b""}
    if xml_path is None or not Path(xml_path).exists():
        return out
    text = Path(xml_path).read_text(encoding="utf-8", errors="replace")
    values_m = re.search(r"<asx:values>(.*?)</asx:values>", text, re.DOTALL)
    if not values_m:
        return out
    values = values_m.group(1)
    for tag in ("VERSION", "TYPE", "INTERFACE", "OFFLINEHANDLER",
                "DATAPROVIDER", "FRTYPE", "CNTSET", "FNTEMB"):
        m = re.search(rf"<{tag}>([^<]*)</{tag}>", values, re.IGNORECASE)
        if m:
            out["header"][tag] = html.unescape(m.group(1).strip())
        elif re.search(rf"<{tag}\s*/>", values, re.IGNORECASE):
            out["header"][tag] = ""
    ctxtt_m = re.search(r"<FPCONTEXTT>(.*?)</FPCONTEXTT>", values, re.DOTALL)
    if ctxtt_m:
        text_m = re.search(r"<TEXT>([^<]*)</TEXT>", ctxtt_m.group(1))
        if text_m:
            out["context_text"] = html.unescape(text_m.group(1).strip())
    out["has_context_object"] = bool(
        re.search(r"<CONTEXT\s+href=", values, re.IGNORECASE))
    out["has_layout_object"] = bool(
        re.search(r"<LAYOUT\s+href=", values, re.IGNORECASE))
    # A transport stores the two heap roots separately.  Keep the original
    # heap (including references between nodes) and select one root in each
    # raw value; SAP's deserializer follows that root and ignores the other.
    abap_m = re.search(r"(<asx:abap\b[^>]*>.*?</asx:abap>)", text,
                       re.DOTALL | re.IGNORECASE)
    heap_m = re.search(r"(<asx:heap\b[^>]*>.*?</asx:heap>)", text,
                       re.DOTALL | re.IGNORECASE)
    if abap_m and heap_m:
        start = abap_m.group(1).split("<asx:values", 1)[0]
        for tag, key in (("CONTEXT", "context_xml"), ("LAYOUT", "layout_xml")):
            root = re.search(rf"(<{tag}\b[^>]*/>)", values, re.IGNORECASE)
            if root:
                out[key] = ('<?xml version="1.0" encoding="utf-8"?>' + start
                            + "<asx:values>" + root.group(1) + "</asx:values>"
                            + heap_m.group(1) + "</asx:abap>")
    xdp_path = Path(xml_path).with_suffix(".xdp")
    if xdp_path.exists():
        out["xdp"] = xdp_path.read_bytes()
    return out


def collect_sfpf_sources(src_dir: Path, obj_name: str, safe: str,
                         source_set_type: Type[dict]) -> dict[str, str]:
    """Collect Adobe print form metadata from abapGit's .sfpf.xml file."""
    sources = source_set_type()
    sfpf_xml = src_dir / f"{safe}.sfpf.xml"
    sources.sfpf_meta = parse_sfpf_xml(sfpf_xml)
    if not sfpf_xml.exists():
        print(f"  WARNING: no {sfpf_xml.name} found")
    elif not sources.sfpf_meta.get("header"):
        print(f"  WARNING: no <asx:values> metadata found in "
              f"{sfpf_xml.name}")
    if sources.sfpf_meta.get("has_layout_object") and not sources.sfpf_meta.get("xdp"):
        print(f"  WARNING: {sfpf_xml.name} declares <LAYOUT>, but its "
              f"companion {sfpf_xml.with_suffix('.xdp').name} is missing")
    return sources
