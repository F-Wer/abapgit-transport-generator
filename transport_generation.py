#!/usr/bin/env python3
"""
abapGit -> SAP Transport File Generator
=======================================
Takes an abapGit repository and generates valid SAP transport files
(cofile + data file) that can be imported via STMS.

Supports: ACID, APIS, APLO, PROG, CLAS, INTF, FUGR, DTEL, MSAG, TABL, TTYP, TRAN, TOBJ,
          ENHO, VIEW, DOMA, TYPE, ENQU, SHLP, XSLT, SICF, SFPF, SFPI, DEVC

Usage:
    python abapgit_to_transport.py <abapgit_repo> [--output <dir>] [--request <Knnnnnn>]
"""

import argparse
import base64
import binascii
import html
import re
import struct
import sys
from defusedxml import ElementTree as ET
from defusedxml.common import DefusedXmlException
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from sap_transport_writer import (
    Container, ContainerBlock, parse_container, build_container,
    compress_stream, block_checksum,
)
from sap_transport_writer import serialize_stream
from sap_transport_records import (
    iter_records, Record, parse_stream, Transport,
    u16,
)
from devc_helpers import regenerate_devc_rows
from transport_request import validate_transport_identity
from transport_record_helpers import (
    find_block as _find_block,
    parse_nametabs as _parse_nametabs,
    replace_block_rows as _replace_block_rows,
)
from transport_record_renames import (
    A_DEVCLASS_LEN,
    A_DEVCLASS_OFF,
    RenameRule,
    _CHAR_TYPES,
    apply_rename_to_key as _apply_rename_to_key,
    make_description as _make_description,
    normalize_repos_key as _normalize_repos_key,
    rename_a_record as _rename_a_record,
    rename_fm_in_key as _rename_fm_in_key,
    rename_h_key as _rename_h_key,
    rename_key_preserving_width as _rename_key_preserving_width,
    replace_bytes as _replace_bytes,
    replace_in_record as _replace_in_record,
    replace_in_row as _replace_in_row,
)
from transport_regenerators.common import (
    blank_row as _blank_row,
    find_block_by_action as _find_block_by_action,
    get_field_text as _get_field_text,
    remove_block as _remove_block,
    replace_rows_in_block as _replace_rows_in_block,
    write_field_by_name as _write_field_by_name,
    write_raw_field_by_name as _write_raw_field_by_name,
)
from transport_cofile import generate_cofile as _generate_cofile
from transport_assembly import (
    drop_task_and_renumber as _drop_task_and_renumber,
    serialize_records as _serialize_records,
    set_object_counter as _set_object_counter,
)
from transport_regenerators.ddic import (
    apply_dtel_row as _apply_dtel_row,
    configure_dtel_helpers as _configure_dtel_helpers,
    fix_dtel_ddlanguage_key as _fix_dtel_ddlanguage_key,
    regenerate_doma_rows as _regenerate_doma_rows,
    regenerate_enqu_rows as _regenerate_enqu_rows,
    regenerate_shlp_rows as _regenerate_shlp_rows,
    regenerate_tabl_rows as _regenerate_tabl_rows,
    apply_ttyp_row as _apply_ttyp_row,
    fix_ttyp_ddlanguage_key as _fix_ttyp_ddlanguage_key,
    regenerate_view_rows as _regenerate_view_rows,
)
from transport_regenerators.messages import (
    configure_msag_helpers as _configure_msag_helpers,
    fix_msag_language_key as _fix_msag_language_key,
    regenerate_msag_rows as _regenerate_msag_rows,
)
from transport_regenerators.metadata import (
    configure_metadata_helpers as _configure_metadata_helpers,
    regenerate_acid_rows as _regenerate_acid_rows,
    regenerate_apis_rows as _regenerate_apis_rows,
    regenerate_aplo_rows as _regenerate_aplo_rows,
    regenerate_amsd_rows as _regenerate_amsd_rows,
    regenerate_asfc_rows as _regenerate_asfc_rows,
    regenerate_auth_rows as _regenerate_auth_rows,
    regenerate_avar_rows as _regenerate_avar_rows,
    regenerate_avas_rows as _regenerate_avas_rows,
    regenerate_char_rows as _regenerate_char_rows,
)
from transport_regenerators.special import (
    configure_special_helpers as _configure_special_helpers,
    apply_tran_row as _apply_tran_row,
    fix_tran_tstct_language_key as _fix_tran_tstct_language_key,
    regenerate_tran_tstcp as _regenerate_tran_tstcp,
)
from transport_regenerators.services import (
    configure_sicf_helpers as _configure_sicf_helpers,
    regenerate_sicf_rows as _regenerate_sicf_rows,
)
from transport_regenerators.xslt import (
    _XSLT_CLUSTER_ENVELOPE,
    configure_xslt_helpers as _configure_xslt_helpers,
    decompress_xslt_cluster as _decompress_xslt_cluster,
    locate_xslt_chunks as _locate_xslt_chunks,
    read_xslt_chunked_text as _read_xslt_chunked_text,
    recompress_xslt_cluster as _recompress_xslt_cluster,
    regenerate_xslt_rows as _regenerate_xslt_rows,
    write_xslt_chunked_text as _write_xslt_chunked_text,
)
from transport_regenerators.enhancements import (
    apply_enho_badi_positional_replacements as _apply_enho_badi_positional_replacements,
    configure_enhancement_helpers as _configure_enhancement_helpers,
    locate_enho_bc_markers as _locate_enho_bc_markers,
    make_enho_master_include_source as _make_enho_master_include_source,
    read_bc_field as _read_bc_field,
    regenerate_enho_badi_data_blob as _regenerate_enho_badi_data_blob,
    regenerate_enho_data_blob as _regenerate_enho_data_blob,
    rewrite_bc_field_text as _rewrite_bc_field_text,
)
from transport_regenerators.type_groups import (
    apply_type_row as _apply_type_row,
    configure_type_helpers as _configure_type_helpers,
    fix_type_ddlanguage_key as _fix_type_ddlanguage_key,
    make_type_pool_boilerplate as _make_type_pool_boilerplate,
)
from transport_regenerators.tobj import (
    _TOBJ_NUMC_FIELDS,
    _TOBJ_OBJH_FIELDS,
    _TOBJ_OBJT_FIELDS,
    _TOBJ_OBJS_FIELDS,
    _TOBJ_TDDAT_FIELDS,
    _TOBJ_TVDIR_FIELDS,
    configure_tobj_helpers as _configure_tobj_helpers,
    regenerate_tobj_rows as _regenerate_tobj_rows,
    set_tobj_key as _set_tobj_key,
    tobj_objname_key as _tobj_objname_key,
    tobj_tabname_key as _tobj_tabname_key,
    tobj_write_row as _tobj_write_row,
)
from transport_regenerators.query import (
    configure_query_helpers as _configure_query_helpers,
    regenerate_aqbg_rows as _regenerate_aqbg_rows,
    regenerate_aqqu_rows as _regenerate_aqqu_rows,
    regenerate_aqsg_rows as _regenerate_aqsg_rows,
    write_aq_value as _write_aq_value,
)
from transport_engine import (
    configure_engine_helpers as _configure_engine_helpers,
    process_template_records as _process_template_records,
)
from transport_members import (
    parse_interface_members as _parse_interface_members,
    parse_class_members as _parse_class_members,
    put_field as _put_field,
    build_component_row as _build_component_row,
    build_class_member_row as _build_class_member_row,
)
from transport_source_blocks import (
    extract_ldb as _extract_ldb,
    set_meta_ldb as _set_meta_ldb,
    encode_source_lines as _encode_source_lines,
    build_repos_key as _build_repos_key,
    make_repos_block_records as _make_repos_block_records,
    extract_class_blocks as _extract_class_blocks,
    split_implementation_methods as _split_implementation_methods,
    base36 as _base36,
    split_class_source as _split_class_source,
    map_source_to_includes as _map_source_to_includes,
    map_class_sources as _map_class_sources,
    interface_pool_boilerplate as _interface_pool_boilerplate,
    class_pool_boilerplate as _class_pool_boilerplate,
    make_cm_h_record as _make_cm_h_record,
    make_cm_block_records as _make_cm_block_records,
    emit_repos_rows as _emit_repos_rows,
    emit_source_block as _emit_source_block,
)
from object_handlers.registry import CollectorContext, collect_object_sources
from transport_object_scanner import detect_object_type as _scan_object_types

# -- Template definitions ----------------------------------------------------

from transport_templates import MANIFEST_NAME, TEMPLATES, TemplateError, template_dir
from transport_native_support import _check_object_list, _set_request_text, request_text


def _pick_template(obj_type: str, obj_name: str, sources=None) -> str:
    """Pick the appropriate template key for the object.

    `sources` is optional (defaults preserve every prior call site's
    behavior) -- only ENHO uses it, to choose between the CLASENH and
    BADI_IMPL templates based on the repo's own .enho.xml <TOOL> value
    (the same class of decision INTF/INTF_NS already makes on namespace,
    just keyed on XML content instead of the object name)."""
    is_ns = "/" in obj_name
    if obj_type == "INTF" and is_ns:
        return "INTF_NS"
    if obj_type == "ENHO":
        enho_meta = getattr(sources, "enho_meta", None) or {}
        if enho_meta.get("tool") == "BADI_IMPL":
            return "ENHO_BADI"
        return "ENHO"
    if obj_type in TEMPLATES:
        return obj_type
    raise TemplateError(f"No template for type {obj_type} in "
                        f"{template_dir()}; add one to its {MANIFEST_NAME}")


# -- Object type detection ---------------------------------------------------

def detect_object_type(src_dir: Path) -> list[dict]:
    """Scan an abapGit src/ directory and return a list of objects found."""
    return _scan_object_types(src_dir)


# -- Record rewriting --------------------------------------------------------





# -- Generic record-block traversal helpers ----------------------------------

def _skip_block(records, i: int) -> int:
    """Advance past the remainder of a block (rows, COMMIT, E) so the whole
    block is dropped from the output. `i` must be past the H record."""
    while i < len(records):
        if records[i].rtype == "*" and records[i].payload == b"COMMIT":
            i += 1
            break
        i += 1
    if i < len(records) and records[i].rtype == "E":
        i += 1
    return i


def _skip_to_own_terminator(records, i: int) -> int:
    """
    Advance past the remainder of an 'N' or 'H' block to its OWN 'E'
    terminator (`i` must be just past the N/H record). Every N/H block is
    guaranteed by the format to end with exactly one 'E' record; this
    always stops there, whether or not a COMMIT marker happens to sit
    inside the block.

    Unlike _skip_block (which hunts forward for the next COMMIT marker),
    this is safe for a block that has NO COMMIT of its own -- e.g. a
    nametab ('N') block, which the format never gives one (verified: the
    CLAS donor template's ENHOBJ/SMODILOG/SMODISRC nametabs, and MSAG's own
    DOKIL/DOKHL/DOKTL nametabs, all end in a bare 'E' with no COMMIT
    anywhere between the last field-descriptor row and it -- the COMMIT
    _skip_block would eventually find belongs to a LATER, unrelated block,
    so using it to drop a nametab silently over-consumes everything in
    between). _skip_block remains correct where it is already used
    (TRDIRT/D020T/D021T, all ATAB *data* blocks each terminated by their
    own COMMIT) and is left alone; this is for N-record drops specifically.
    """
    while i < len(records) and records[i].rtype != "E":
        i += 1
    if i < len(records):
        i += 1
    return i


def _derive_task(request: str) -> str:
    """
    Derive a task number from a request number, mirroring the SAP convention
    every template (and a real single-object export)
    follows: a workbench request's first task is numbered request+1, same
    digit width (DEVK900888 -> DEVK900889).
    """
    m = re.match(r"^(.*?)(\d+)(\s*)$", request)
    if not m:
        raise ValueError(f"cannot derive a task number from {request!r}")
    prefix, digits, suffix = m.groups()
    incremented = str(int(digits) + 1).zfill(len(digits))
    return f"{prefix}{incremented}{suffix}"


def _make_rule(tmpl: dict, obj_name: str, new_request: str,
               new_task: str = "", old_task: str = "",
               fm_pairs: list = None) -> RenameRule:
    """Build the rename rule for one template -> one object."""
    return RenameRule(
        old_name=tmpl["object"],
        new_name=obj_name,
        old_request=tmpl["request"],
        new_request=new_request,
        old_task=old_task,
        new_task=new_task,
        old_descs=[d for d in [tmpl.get("description", "")]
                   + tmpl.get("descriptions", []) if d],
        new_desc=_make_description(obj_name),
        fm_pairs=fm_pairs or [],
    )


def _load_template_records(tmpl_key: str):
    """Load + decompress a template's data file. Returns (container, records)."""
    from sap_transport_writer import decompress_container
    tmpl = TEMPLATES[tmpl_key]
    container = parse_container(tmpl["data"].read_bytes())
    stream = decompress_container(container)
    return container, _drop_object_index(iter_records(stream))


# -- Function-group (FUGR) metadata -----------------------------------------

class SourceSet(dict):
    """A sources dict (include key -> source text) that may carry FUGR
    metadata read from the repo's .fugr.xml alongside the sources."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fugr_areat = ""                       # group short text (AREAT)
        self.fugr_functions = []                   # [(FUNCNAME, SHORT_TEXT)]
        self.fugr_interfaces = {}


class AcidSourceSet(dict):
    """An empty source map carrying checkpoint-group XML metadata."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.acid_meta = {"description": ""}


class ApisSourceSet(dict):
    """An empty source map carrying API release-state XML metadata."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apis_meta = {"header": {}, "states": []}


class AploSourceSet(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.aplo_meta = {}


class AqbgSourceSet(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs); self.aqbg_meta = {}


class AqquSourceSet(dict):
    """An empty source map carrying generic ABAP Query table rows."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.aqqu_meta = {}


class AqsgSourceSet(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.aqsg_meta = {}


class AsfcSourceSet(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.asfc_meta = {}


class AuthSourceSet(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.auth_meta = {}


class AvarSourceSet(dict):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs); self.avar_meta={"description":"","ids":[]}


class AvasSourceSet(dict):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs); self.avas_meta={"header":{},"values":[]}


class CharSourceSet(dict):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs); self.char_meta={}


class AmsdSourceSet(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.amsd_meta = {}


_FUNCTION_RE = re.compile(
    r"^\s*FUNCTION\s+([A-Za-z_~/][A-Za-z0-9_~/]*)\s*\.",
    re.IGNORECASE | re.MULTILINE)


def _extract_function_modules(sources) -> list:
    """
    The repo's function-module list -- derived by scanning the collected
    FUGR sources for `FUNCTION <name>.` statements (this is the
    authoritative FM list; the .fugr.xml FUNCTIONS list is only a
    cross-check). Scans in deterministic order (sorted include keys).
    `FUNCTION-POOL` and `ENDFUNCTION.` do not match. Namespaced FM names
    (/NAMESPACE/...) are kept whole.
    """
    fms = []
    for key in sorted(sources):
        for m in _FUNCTION_RE.finditer(sources[key]):
            name = m.group(1).upper()
            if name not in fms:
                fms.append(name)
    return fms


def _template_function_modules(records) -> list:
    """The template's own FM list: the TFDIR block keys (one H block per FM,
    key = FM name -- verified against the FUGR template)."""
    fms = []
    for rec in records:
        if (rec.rtype == "H" and
                rec.payload[8:38].decode("latin-1").rstrip() == "TFDIR"):
            key = rec.payload[48:].decode("latin-1").rstrip()
            if key and key not in fms:
                fms.append(key)
    return fms


def _map_function_modules(tmpl_fms: list, repo_fms: list):
    """
    Pair template FMs to repo FMs. The mapping rule (documented in
    docs/fugr-support.md):

      1. exact-name matches pair up first;
      2. remaining template FMs pair POSITIONALLY with the remaining repo
         FMs (in derivation order -- source scan order);
      3. template FMs with no repo partner are UNMAPPED -- their per-FM
         blocks are dropped (drop-unmatched rule);
      4. repo FMs with no template partner are SYNTHESIZED -- their per-FM
         blocks are cloned from the last mapped template FM.

    The bundled template has exactly one FM (names.function in its manifest), so rule 1
    never fires for it and the mapping collapses to: template FM -> the
    first repo FM; every further repo FM is synthesized.
    Returns (pairs, unmapped_template_fms, cloned_repo_fms).
    """
    pairs = []
    used = set()
    for tfm in tmpl_fms:
        if tfm in repo_fms and repo_fms.index(tfm) not in used:
            pairs.append((tfm, tfm))
            used.add(repo_fms.index(tfm))
    template_rest = [f for f in tmpl_fms
                     if f not in {p[0] for p in pairs}]
    repo_rest = [f for i, f in enumerate(repo_fms) if i not in used]
    n = min(len(template_rest), len(repo_rest))
    for i in range(n):
        pairs.append((template_rest[i], repo_rest[i]))
    unmapped = set(template_rest[n:])
    cloned = repo_rest[n:]
    return pairs, unmapped, cloned


def _docut_key_fm(key: str) -> Optional[str]:
    """
    The FM name packed in a DOCUT% delete key: `FU<FM><30><%>` / `FX...`
    (2-char prefix + 30-wide FM field + '%' wildcard -- measured on the
    template: 'FU' + a 30-character FM name + '%' is 33 chars). Group docs
    pack `RE<SAPL<group>>` and return None.
    """
    if len(key) >= 33 and key[:2] in ("FU", "FX") and key.endswith("%"):
        return key[2:32].rstrip()
    return None


def _fm_for_block(table: str, key: str, tmpl_fms: list) -> Optional[str]:
    """The template FM a block belongs to (keyed by the FM name in its H
    key), or None for group-level blocks. Table-specific key layouts:"""
    if table in ("TFDIR", "ENLFDIR"):
        return key if key in tmpl_fms else None
    if table == "FUPARAREF" and key.endswith("A*"):
        # FUNCNAME(30) + R3STATE('A') + '*' delete pattern
        fm = key[:30].rstrip()
        return fm if fm in tmpl_fms else None
    if table == "FUNCT" and key.endswith("*"):
        fm = key[1:31].rstrip()
        return fm if fm in tmpl_fms else None
    if table == "TFTIT":
        fm = key[1:].rstrip()
        return fm if fm in tmpl_fms else None
    if table == "RODIR" and key.startswith("FUNC"):
        fm = key[4:].rstrip()
        return fm if fm in tmpl_fms else None
    if table == "DOCUT%":
        fm = _docut_key_fm(key)
        return fm if fm and fm in tmpl_fms else None
    return None


def _collect_fm_blocks(records, tmpl_fms: list) -> dict:
    """Per template FM: the index ranges [start, end] (H .. E inclusive) of
    its per-FM blocks -- TFDIR, ENLFDIR, FUNCT sweep, FUPARAREF, TFTIT
    sweep + REPC row, RODIR, DOCUT% FU/FX. Used for cloning."""
    blocks = {f: [] for f in tmpl_fms}
    i = 0
    while i < len(records):
        rec = records[i]
        if rec.rtype == "H":
            table = rec.payload[8:38].decode("latin-1").rstrip()
            key = rec.payload[48:].decode("latin-1").rstrip()
            fm = _fm_for_block(table, key, tmpl_fms)
            if fm is not None:
                j = i
                while j < len(records) and records[j].rtype != "E":
                    j += 1
                blocks[fm].append((i, j))
                i = j + 1
                continue
        i += 1
    return blocks


# -- Message class (MSAG) metadata ------------------------------------------
#
# A message class has no ABAP source at all: abapGit serializes it purely as
# metadata in <name>.msag.xml (SAP/abap-file-formats schema, verified against
# abapGit's own zcl_abapgit_object_msag serializer and real .msag.xml exports):
#
#   <T100A><ARBGB/><MASTERLANG/><STEXT/></T100A>        -- class header
#   <T100><T100><SPRSL/><ARBGB/><MSGNR/><TEXT/></T100>...</T100>  -- messages
#
# (RESPUSER/LASTUSER/LDATE/LTIME/APPLCLASS are cleared before serialize and
# so are never present in real XML -- abapGit's importer regenerates them at
# deserialize time; this generator keeps the template's own values instead,
# matching the project's "everything else keeps the template's values"
# convention used for CLAS/INTF SEO rows.)
#
# There is no REPOS/ABAPREAD block to inject source into; the whole job is
# regenerating the T100 (message text, one row per message) and T100U
# (per-message usage flags) row SETS to match the repo's message list
# (arbitrary count, unlike the template's fixed 30), plus setting T100T /
# T100A's STEXT to the repo's class description. The 49-language delete
# sweeps (T100/T100T) and the per-table H-record keys are already renamed
# correctly by the generic ATAB/DLIB width-preserving pass in
# _process_template_records -- nothing MSAG-specific needed there.

class MsagSourceSet(dict):
    """An (always empty -- MSAG has no source files) sources dict that
    carries the metadata read from the repo's .msag.xml alongside it."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.msag_masterlang = ""          # T100A-MASTERLANG, e.g. "D"
        self.msag_stext = ""               # T100A-STEXT (class description)
        self.msag_messages = []            # [(MSGNR, TEXT), ...] in XML order


def _set_fm_title(row: Record, fields: list, fm_name: str,
                  short_text: str) -> Record:
    """Write TFTIT.STEXT for one FM row. The title comes from the repo's
    .fugr.xml (FUNCTIONS.SHORT_TEXT); without it a description is derived
    from the FM name -- the repo has no other FM title source (abapGit does
    not serialize TFTIT)."""
    return _write_field_by_name(row, fields, "STEXT",
                                short_text or _make_description(fm_name))


def _fix_cloned_fm_rows(recs: list, nametabs: dict, new_fm: str,
                        fm_short_texts: dict, fm_u_numbers: dict) -> list:
    """
    Post-process cloned per-FM blocks for a synthesized FM: TFTIT REPC row
    gets the FM's title, TFDIR row gets the FM's U-number in INCLUDE.
    """
    tftit = nametabs.get("TFTIT") or []
    tfdir = nametabs.get("TFDIR") or []
    out = []
    i = 0
    while i < len(recs):
        r = recs[i]
        if r.rtype == "H":
            table = r.payload[8:38].decode("latin-1").rstrip()
            action = r.payload[38:44].decode("latin-1")
            out.append(r)
            i += 1
            while i < len(recs) and recs[i].rtype != "E":
                row = recs[i]
                if row.rtype == " ":
                    if table == "TFTIT" and action == "00REPC":
                        row = _set_fm_title(
                            row, tftit, new_fm,
                            fm_short_texts.get(new_fm, ""))
                    elif table == "TFDIR":
                        n = fm_u_numbers.get(new_fm, 1)
                        row = _write_field_by_name(row, tfdir, "INCLUDE",
                                                   f"{n:02d}")
                out.append(row)
                i += 1
        else:
            out.append(r)
            i += 1
    return out


# -- DD04 row helper ---------------------------------------------------------
#
# This generic fixed-width field writer remains in the compatibility facade
# because sibling DDIC regenerators still use it. DTEL-specific logic lives in
# transport_regenerators.ddic and receives this helper by dependency injection.

def _write_dd04_field(row: Record, fields: list, fname: str,
                      value: str) -> Record:
    """
    Write one DD04L/DD04T field by name. NUMC ('N') fields are zero-padded
    (right-justified) to their declared character width instead of the
    generic space-padding _write_field_by_name uses for text -- matching
    SAP's own convention for LENG/DECIMALS/OUTPUTLEN/HEADLEN/SCRLEN1-3 (and
    exactly what abapGit's XML already carries: e.g. LENG='000200').
    """
    for name, _off, flen, ftype in fields or []:
        if name == fname and ftype == "N":
            chars = flen // 2
            digits = value.strip()
            value = digits.zfill(chars)[-chars:] if digits else "0" * chars
            break
    return _write_field_by_name(row, fields, fname, value)



_configure_dtel_helpers(
    _write_dd04_field,
    _make_description,
    parse_nametabs=_parse_nametabs,
    find_block_by_action=_find_block_by_action,
    write_field_by_name=_write_field_by_name,
    remove_block=_remove_block,
    blank_row=_blank_row,
    replace_rows_in_block=_replace_rows_in_block,
    fix_msag_language_key=_fix_msag_language_key,
)


# -- Table / structure (TABL) metadata ---------------------------------------

class TablSourceSet(dict):
    """An (always empty -- TABL has no source files) sources dict that
    carries the metadata read from the repo's .tabl.xml alongside it, the
    same pattern as MsagSourceSet/SourceSet's side-channel attributes."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.tabl_meta = {}          # see object_handlers.tabl.parse_tabl_xml


class ViewSourceSet(dict):
    """An (always empty -- VIEW has no source files) sources dict that
    carries the metadata read from the repo's .view.xml alongside it, the
    same pattern as TablSourceSet/MsagSourceSet."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.view_meta = {}          # see object_handlers.view.parse_view_xml





# -- Lock object (ENQU) metadata ---------------------------------------------
#
# A lock object has no ABAP source at all -- like VIEW, the whole object is
# DDIC metadata, serialized by abapGit as <name>.enqu.xml. SAP implements a
# lock object as a special kind of DDIC view internally: on the transport
# side an ENQU touches the SAME FOUR tables VIEW already regenerates --
# DD25L/DD25T/DD26S/DD27S -- confirmed via a direct nametab comparison
# against VIEW's own template (the VIEW template) before writing any of
# this code, per this project's standing rule: DD25L (31 fields), DD26S (8
# fields), and DD27S (18 fields) all have IDENTICAL field-name lists
# between the real ENQU object (the template lock object) and VIEW's own real object
# (the template view) -- including DD27S's ENQMODE column, which turns out to
# already exist in VIEW's own real DD27S nametab too (a working hypothesis
# in the task brief that DD27S has "2 more fields" than VIEW's did not
# survive the direct comparison -- corrected here, not left as an
# unverified assumption).
#
# What actually differs between a VIEW object and an ENQU object is VALUES,
# not table shape:
#   - DD25L.AGGTYPE='E' for a lock object (vs 'V' for VIEW's own real
#     object) -- this is the field that distinguishes them, NOT VIEWCLASS
#     (the task brief's own working hypothesis about which field carries
#     'C'/'E' was imprecise; VIEWCLASS is a genuinely different DD25L
#     column, confirmed directly against real bytes before writing this
#     comment).
#   - DD25L.VIEWCLASS/CUSTOMAUTH/VIEWGRANT/GLOBALFLAG are all BLANK for a
#     real ENQU object -- abapGit's own ENQU serializer (LCL_OBJECT_ENQU)
#     never writes these into <DD25V> at all (confirmed against every real
#     .enqu.xml sample found -- none carries these tags), matching the real
#     template lock object's own blank DD25L bytes exactly.
#   - DD26S has NO ENQMODE column at all (confirmed directly), even though
#     abapGit's own <DD26E> schema carries a per-base-table ENQMODE -- it is
#     parsed but has nowhere to go on the transport side, dropped with a
#     WARNING, same "no home in this real nametab" posture VIEW's own
#     SHLPORIGIN/VALEXI/LOGFLAG/CHECKTABLE finding already established.
#   - DD27S DOES have a real ENQMODE column, and abapGit's own <DD27P>
#     schema carries a per-field ENQMODE -- written straight through.
#
# THE DD27S "GENERIC LOCK ARGUMENT" FINDING (decoded byte-by-byte before
# writing any regeneration code -- see build_enqu_template.py for the full
# byte dump): the real template lock object's own DD27S carries 3 rows for what
# is really 2 key fields on its one base table (MANDT, PERNR):
#   row 1: VIEWFIELD=MANDT FIELDNAME=MANDT KEYFLAG=X          ENQMODE=' '
#   row 2: VIEWFIELD=PERNR FIELDNAME=PERNR KEYFLAG=X          ENQMODE=' '
#   row 3: VIEWFIELD=PERNR FIELDNAME=*     KEYFLAG=' ' (blank) ENQMODE='E'
# Row 3 is SAP's "generic lock argument" mechanism (the "Generic" checkbox
# in SE11's lock object field maintenance) -- a literal FIELDNAME='*' row
# paired with the same VIEWFIELD as its normal row. This turns out to be a
# genuine, real DD27P XML convention, not ENQU-specific: `gh search code`
# found a real VIEW's own .view.xml (halomoan/ZMM's zv_ekkona.view.xml)
# with a <DD27P><VIEWFIELD>*</VIEWFIELD><FIELDNAME>*</FIELDNAME>
# <TABNAME>NAST</TABNAME></DD27P> element -- the same DD27P_TABLE schema
# VIEW and ENQU share, independently confirming a literal '*' FIELDNAME
# value round-trips through abapGit's XML. No real .enqu.xml sample with a
# generic-flagged key field was found anywhere (every real sample surveyed
# -- 3 local, from ABAP-SDK-for-Azure -- has simple, non-generic key fields
# only, with ENQMODE populated uniformly on every row). So this generator
# treats every <DD27P> element the same way, generically (one DD27S row
# per XML element, whatever FIELDNAME/ENQMODE it carries) rather than
# inventing a "generic flag" heuristic -- this correctly reproduces the
# real object's own 3-row shape when the repo's .enqu.xml supplies a
# literal FIELDNAME=* entry (verified in the round-trip test built from
# the template lock object's own content), but whether abapGit's ENQU serializer
# really emits FIELDNAME=* for a generic-flagged field (vs. some other
# shape) is inferred from the VIEW analogy, not confirmed against a real
# ENQU sample -- documented as a limitation, not silently assumed.


class EnquSourceSet(dict):
    """An (always empty -- ENQU has no source files) sources dict that
    carries the metadata read from the repo's .enqu.xml alongside it, the
    same pattern as ViewSourceSet/TablSourceSet."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.enqu_meta = {}          # see object_handlers.enqu.parse_enqu_xml




# -- ICF service (SICF) metadata ---------------------------------------------
#
# An ICF service node has no ABAP source at all -- like DOMA/VIEW/ENQU/SHLP,
# the whole object is DDIC-style tree metadata, serialized by abapGit as
# <name>.sicf.xml. On the transport side a SICF object touches (at most) six
# tables -- ICFSERVICE (the node itself, 83 fields), ICFDOCU (description
# text), ICFHANDLER (handler-class assignment, arbitrary count), ICFVIRHOST
# (virtual-host assignment), ICFAPPLCUST (app-specific customizing string),
# and SOTR_USEU (OTR long-text usage tracking) -- confirmed via a direct
# nametab scan of the real reference object (the SICF template) before writing any
# of this code, per this project's standing rule; see build_sicf_template.py
# for the full byte-level reconnaissance.
#
# THE COMPOUND OBJECT NAME (read build_sicf_template.py's module docstring
# for the full derivation): a SICF object's R3TR/E071/TADIR name is not a
# plain identifier. It is a FIXED 40-CHARACTER COMPOUND KEY:
#
#     OBJ_NAME = ICF_NAME (15 chars, space-padded) + ICFPARGUID (25 chars,
#                stripped, no separator)
#
# -- verified byte-for-byte against the real SICF template's own C/E071
# records and independently cross-checked against every one of the 8 real
# local .sicf.xml filenames found on this machine (every one is exactly a
# 40-char stem: name padded/truncated to 15, then a 25-char hash with no
# separator). Confirmed against abapGit's own zcl_abapgit_object_sicf
# .clas.abap SERIALIZE method (fetched from GitHub): the filename is built
# as `cv_item_part_of_filename(15) & get_hash_from_object(...)` -- the first
# 15 characters are ICF_NAME, the remaining 25 a hash tied to the node's URL
# that is, in practice, the SAME value SAP itself stores as ICFPARGUID for a
# node at that URL (both abapGit and SAP's own cl_icf_tree=>service_from_url
# derive it from the identical URL-path resolution).
#
# Practical consequence: THE OBJECT NAME IS THE REPO'S FILENAME, VERBATIM
# (same convention every other type in this project already uses -- see
# detect_object_type) -- and its own 15/25 split IS the source of both
# ICF_NAME and ICFPARGUID. ICFPARGUID never appears in the abapGit XML at
# all: confirmed against all 8 real .sicf.xml samples (none carries it) AND
# against abapGit's own SERIALIZE method, which explicitly CLEARs
# ICFPARGUID (both ICFSERVICE and ICFDOCU) and ICFNODGUID before writing the
# XML, "to ensure portability across systems". So this generator recovers
# ICFPARGUID from the filename's own 15/25 split instead of leaving it
# blank or guessing.
#
# ICFNODGUID (this node's OWN newly-assigned guid -- relevant only to any
# CHILD nodes it might have) has no representation anywhere: not in the
# XML, not in the filename (which encodes the PARENT's hash, not this
# node's own). It is left at the template's own real (arbitrary) value --
# the same "no home in the schema, template value kept, documented
# limitation" posture VIEW/ENQU already established for ROLLNAME. So are
# every other admin/bookkeeping field with no XML equivalent (ICF_CUSER/
# ICF_MUSER/ICF_CDATE/ICF_MDATE/ICF_TIME/ICF_AUTHRC/HTTPCDE*/ICFBITMAP/
# ICF_CCLNT/ICF_MCLNT/...) -- matches DOMA's own posture for DD01L's admin
# fields.
#
# ICFVIRHOST / ICFAPPLCUST: never regenerated. Confirmed via BOTH the real
# reference object (0 rows for each, even though the H-block/nametab is
# genuinely present in its own section) AND abapGit's fetched SERIALIZE
# source (it writes exactly URL/ICFSERVICE/ICFDOCU/ICFHANDLER_TABLE/SOTS/
# SOTS_USE into the XML -- no ICFVIRHOST/ICFAPPLCUST tag exists in abapGit's
# schema at all). These two tables ship exactly as the template's own real
# 0-row blocks.
#
# SOTR_USEU: abapGit serializes OTR long-text usage as <SOTS>/<SOTS_USE> (a
# SHARED cross-object-type OTR helper, zcl_abapgit_sots_handler -- the same
# infrastructure the ENHO/BADI_IMPL round's own SOTR note refers to). None
# of the 8 real local .sicf.xml samples use OTR-based long text (all use
# the plain ICFDOCU short-text table instead), and the ENHO/BADI_IMPL round
# already established the precedent of not regenerating this content (see
# object_handlers/enho.py's parse_enho_xml docstring: "SOTR is left as
# template boilerplate").
# Followed here identically -- no SICF-specific SOTS/SOTS_USE parsing code.
#
# ICFHANDLER: the real reference object has none, so its own section
# carries only a 0-row '00DELL' delete-sweep block for this table -- no
# '00REP '/'00REPC' insert-shape block exists anywhere to clone rows from.
# When the repo's own .sicf.xml DOES carry <ICFHANDLER_TABLE> entries (two
# of the 8 real local samples do -- an OData service and a custom HTTP
# handler), this generator PROMOTES that DELL block to '00REPC' and
# populates it -- the exact same "flip a delete-sweep block to an insert
# block on the same table, in the same object, when the template offers no
# other example" move TOBJ's own OBJT regeneration already established
# (see _regenerate_tobj_rows). The key text itself needs no change (it is
# already the correct compound name, verified during the generic per-record
# rename pass that runs before this function).


class SicfSourceSet(dict):
    """An (always empty -- SICF has no source files) sources dict that
    carries the metadata read from the repo's .sicf.xml alongside it, the
    same pattern as EnquSourceSet/ViewSourceSet."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sicf_meta = {}          # see object_handlers.sicf.parse_sicf_xml


class DevcSourceSet(dict):
    """An empty sources dict carrying metadata read from a repo .devc.xml."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.devc_meta = {}          # see devc_helpers.parse_devc_xml




# -- Table type (TTYP) metadata ----------------------------------------------
#
# A table type has no ABAP source at all -- abapGit serializes it entirely as
# XML (<DD40V>, the abap-file-formats TTYP schema; confirmed against ~100
# real .ttyp.xml files pulled from several local abapGit-managed repos,
# including the exact objects the probe template's real content was spliced
# from -- a real project's .ttyp.xml matches the
# template's own DD40T text field-for-field). On the transport side a TTYP
# touches exactly two tables the same way DTEL touches DD04L/DD04T: DD40L
# (the header row: row-type reference, kind, access mode, key definition)
# and DD40T (one row per language: the description). Mechanically this makes
# TTYP the same shape of "simplest" addition DTEL was -- two rows to
# populate from a parsed XML dict, via the same nametab-driven field writer.
#
# The row-type reference (DD40L-ROWTYPE) is itself a dependency on another
# object (a DTEL/TABL/built-in type) this generator does not ship -- the same
# category of out-of-scope dependency already accepted for CLAS/INTF/FUGR's
# own DDIC references and for DTEL's own DOMNAME. The reference is carried
# through correctly; the referenced type itself is not.

# DD40L fields taken from the repo's <DD40V> when present. Observed across
# ~100 real .ttyp.xml files (three ROWKIND shapes: 'S' structure reference,
# 'R' interface/class reference with DATATYPE=REF + REFTYPE, 'E' elementary
# type with an explicit DATATYPE/LENG; plus TTYPKIND='R'+RANGE_CTYP for a
# ranges table type, alongside ROWKIND='S'/DATATYPE='STRU'). None of the
# real files surveyed ever carry DD40L's TYPELEN -- it is a pure DDIC-derived
# field (the referenced row type's own byte length, which abapGit cannot
# know without also serializing that type's definition), so it is always
# blanked here rather than left at the template's stale value; unlike
# DTEL's DATATYPE/LENG/OUTPUTLEN blanking (Opus review finding D3, genuinely
# unconfirmed against a real import) this is not a per-object judgment call
# -- every TTYP object's TYPELEN is equally absent from the schema, so no
# per-generation WARNING is printed for it (see docs/ttyp-support.md).


# -- Transaction code (TRAN) metadata ----------------------------------------
#
# A transaction code has no ABAP source at all -- abapGit serializes it
# entirely as XML (<asx:values> wrapping <TSTC>/<TSTCC>/<TSTCT>/<TSTCP>, the
# abap-file-formats TRAN schema; confirmed against real abapGit-managed
# repos on GitHub, e.g. tricktresor/cute and DevEpos/abap-db-browser). On
# the transport side, the real reference object's own 269-record section
# additionally carries TCDCOUPLES, TSTCA, TSTC_SM, TSTC_SRT and the SU24
# authorization-proposal tables (USOBT/USOBX/USOB_SM/USOTT) plus generic
# enhancement/doc housekeeping (ENHOBJ, SMODILOG, SMODISRC, EUDB,
# RSMPTEXTS, D347T) -- none of these has any abapGit-sourced content (the
# SU24 tables are large, customizing-owned, and never serialized by
# abapGit at all), so build_tran_template.py drops all of them at template-
# build time rather than shipping them as renamed stale content -- the same
# "template block with no matching source, drop it" bucket CLAS's dynpro
# content and DTEL's SHLPNAME/ENTITYTAB fields are already in. Only
# TSTC/TSTCC/TSTCT/TSTCP survive in the template.
#
# Unlike DTEL/MSAG/TABL/TTYP, no nametab needed borrowing from a donor or an
# earlier object in the reference stream: the TRAN template's own section
# defines TSTC/TSTCC/TSTCT/TSTCP's nametabs itself (verified directly,
# out/explore_tran4.py) -- each as a self-contained [gsr:, N, field-rows, E]
# block immediately followed by its own [H, rows, COMMIT, E] data block.

# TSTC: TCODE is renamed for free by the generic per-row rename (like
# ROLLNAME/TYPENAME for DTEL/TTYP). PGMNA/DYPNO (report-transaction only)
# and CINFO are new content per object. MENUE/ARBGB have no abapGit source
# at all (not part of the <TSTC> schema in any real .tran.xml surveyed) --
# blanked rather than left at the template's own stale value, matching the
# project's "never leave stale per-object template content" convention.


# -- Public transport generation ------------------------------------------------

def generate_transport(obj_type: str, obj_name: str, sources: dict[str, str],
                        new_request: str, new_task: str = "",
                        sid: str = "",
                        package: str = "",
                        language: str = "", author: str = "") -> tuple[bytes, bytes]:
    """
    Generate a transport (data file bytes, cofile bytes) for a single ABAP
    object. Thin wrapper around generate_transport_multi.
    """
    return generate_transport_multi(
        [(obj_type, obj_name, sources, "")], new_request, new_task, sid,
        package, language, author)


def generate_transport_multi(objects, new_request: str, new_task: str = "",
                             sid: str = "",
                             package: str = "",
                             language: str = "", author: str = "") -> tuple[bytes, bytes]:
    """
    Generate a transport (data file bytes, cofile bytes) containing ALL the
    given objects. `objects` is a list of (obj_type, obj_name, sources).

    The first object's template provides the request-level skeleton (E070,
    E070C, E070A, TADIR nametab) and the single request-level E07T row --
    a real multi-object export has exactly one E07T row per language, so the
    further objects' E07T rows are dropped. Every further object contributes:
      - its E071 entry (renamed, renumbered to its position)
      - its whole object section (first C record up to the stream's Z record),
        including its own nametabs, data blocks, and injected sources
    """
    base_type, base_name, base_sources, base_ldb = objects[0]
    tmpl_key = _pick_template(base_type, base_name, base_sources)
    tmpl = TEMPLATES[tmpl_key]

    container, base_records = _load_template_records(tmpl_key)
    # Every template carries a CORR/RELE task row in E071 (AS4POS=1) ahead of
    # its object row (AS4POS=2, LOCKFLAG='X') -- a genuine SAP single-object
    # release always has this shape (verified byte-for-byte against a real,
    # independently-exported single-object transport). For a single-object
    # result we keep that row (renamed below) instead of dropping it: R3trans
    # HALTs on import ("... exists already with different contents.
    # E071=1/file=2") if a request ends up with only one E071 row. Multi-
    # object merges drop it in _drop_task_and_renumber below, matching a real
    # multi-object export, which has no CORR/RELE row at all.
    task = new_task or _derive_task(new_request)
    base_rule = _make_rule(tmpl, base_name, new_request,
                           new_task=task, old_task=_derive_task(tmpl["request"]))
    base_rule.language = language
    base_processed = _process_template_records(
        base_records, base_type, base_name, base_sources, base_rule,
        base_ldb, package, author)

    for pos, (o_type, o_name, o_sources, o_ldb) in enumerate(objects[1:], start=3):
        t_key = _pick_template(o_type, o_name, o_sources)
        t = TEMPLATES[t_key]
        _, raw = _load_template_records(t_key)
        rule = _make_rule(t, o_name, new_request)
        rule.language = language
        processed = _process_template_records(
            raw, o_type, o_name, o_sources, rule, o_ldb, package, author)

        # The object's whole section: first C record up to (exclusive) the
        # stream's Z record. New REPOS blocks for includes the template
        # didn't have were inserted before Z, so they come along.
        c_idx = next(i for i, r in enumerate(processed) if r.rtype == "C")
        z_idx = next(i for i in range(len(processed) - 1, -1, -1)
                     if processed[i].rtype == "Z")
        section = processed[c_idx:z_idx]
        section[0] = _set_object_counter(section[0], pos)
        # Some templates declare their object's table layouts in the request
        # header (before the first C record) instead of inline at first use.
        # Those nametabs must travel with the section, or R3trans HALTs with
        # "no nametab transported for table ..." -- re-declare them right
        # behind the object's C/A records, where a real export puts them.
        nametabs = _header_nametab_blocks(processed[:c_idx])
        at = 2 if len(section) > 1 and section[1].rtype == "A" else 1
        section[at:at] = nametabs

        # E071 object entry (2nd row of the template's E071 block).
        # Must be renamed FIELD BY FIELD via the template's own E071
        # nametab, not by a length-preserving byte replace: a plain
        # replace shifts every field after OBJ_NAME by the name-length
        # delta, landing garbage ('X') in OBJFUNC/LANG/GENNUM/ACTIVITY
        # (or inside OBJ_NAME itself when the new name is shorter) --
        # found by Opus review across 33/37 rows in a real multi-object
        # merge, invisible to test_transport.py since row length itself
        # is still correct. See _replace_in_row's docstring for the same
        # failure mode this mirrors (SEOCLASSTX).
        blk = _find_block(raw, "E071")
        if blk is None or not blk[1]:
            raise ValueError(f"{t_key} template has no E071 object row")
        e071_fields = _parse_nametabs(raw).get("E071")
        if not e071_fields:
            raise ValueError(f"{t_key} template has no E071 nametab")
        # The object row is the last one: a workbench-request template has
        # its CORR/RELE task row in front of it, a transport-of-copies
        # template (the native probes) has the object row only.
        obj_row = raw[blk[1][-1]]
        if len(obj_row.payload) != e071_fields[-1][1] + e071_fields[-1][2]:
            raise ValueError(f"{t_key} E071 object row does not match its "
                              f"own nametab's row width")
        new_row = _replace_in_row(obj_row, rule, e071_fields)
        new_row = _set_object_counter(new_row, pos)
        base_blk = _find_block(base_processed, "E071")
        if len(new_row.payload) != len(base_processed[base_blk[1][0]].payload):
            raise ValueError(
                f"{t_key} template's E071 row layout differs from the base "
                f"template's ({tmpl_key}) -- cannot merge into one request")
        base_processed.insert(base_blk[2], new_row)

        # Object section, before the stream's Z record
        z = next(i for i in range(len(base_processed) - 1, -1, -1)
                 if base_processed[i].rtype == "Z")
        base_processed[z:z] = section
        print(f"  Merged {o_type} {o_name} (position {pos}, "
              f"{len(section)} records)")

    # Multi-object merges: drop the inherited template task row and renumber
    # from 000001 like a real multi-object export (verified against a real export, which
    # has N straight object rows, no CORR/RELE row). Single-object output
    # keeps the task row instead -- see the comment above where it is renamed.
    if len(objects) >= 2:
        _drop_task_and_renumber(base_processed)

    _ensure_trdir_nametab(base_processed)
    _set_request_text(base_processed, request_text([o[1] for o in objects]), language)
    _check_object_list(base_processed, [(o[0], o[1]) for o in objects])
    _set_request_entry_count(base_processed)
    data_bytes = _serialize_records(base_processed, container)

    # Cofile: same format for any object count -- only the two object-count
    # counters in the header line differ (verified against a real 2-object
    # export). The request number lives only in the filename, the object list
    # is the E071 block in the data file.
    cofile_bytes = _generate_cofile(tmpl["cofile"].read_bytes(),
                                    [o[0] for o in objects])

    return data_bytes, cofile_bytes


# -- Source file collection -------------------------------------------------

def collect_sources(src_dir: Path, obj_type: str, obj_name: str) -> dict[str, str]:
    """
    Collect all source files for an object from the abapGit repo.
    Returns a dict mapping include name -> ABAP source text.
    """
    context = CollectorContext(
        acid_source_set_type=AcidSourceSet,
        apis_source_set_type=ApisSourceSet,
        aplo_source_set_type=AploSourceSet,
        aqbg_source_set_type=AqbgSourceSet,
        aqqu_source_set_type=AqquSourceSet,
        aqsg_source_set_type=AqsgSourceSet,
        asfc_source_set_type=AsfcSourceSet,
        auth_source_set_type=AuthSourceSet,
        avar_source_set_type=AvarSourceSet,
        avas_source_set_type=AvasSourceSet,
        char_source_set_type=CharSourceSet,
        amsd_source_set_type=AmsdSourceSet,
        build_repos_key=_build_repos_key,
        make_enho_master_include_source=_make_enho_master_include_source,
        make_type_pool_boilerplate=_make_type_pool_boilerplate,
        devc_source_set_type=DevcSourceSet,
        enqu_source_set_type=EnquSourceSet,
        msag_source_set_type=MsagSourceSet,
        sicf_source_set_type=SicfSourceSet,
        source_set_type=SourceSet,
        tabl_source_set_type=TablSourceSet,
        view_source_set_type=ViewSourceSet,
    )
    return collect_object_sources(src_dir, obj_type, obj_name, context)
