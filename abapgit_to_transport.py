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
from transport_request import (
    normalize_author,
    normalize_package,
    validate_transport_identity,
)
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
from object_handlers.sicf import sicf_node_guid, sicf_object_name
from object_handlers.source_metadata import master_language
from transport_object_scanner import (detect_object_type as _scan_object_types,
                                      unsupported_files)

# -- Compatibility generation facade -----------------------------------------

from transport_generation import (
    AcidSourceSet,
    AmsdSourceSet,
    AploSourceSet,
    ApisSourceSet,
    AqbgSourceSet,
    AqquSourceSet,
    AqsgSourceSet,
    AsfcSourceSet,
    AuthSourceSet,
    AvarSourceSet,
    AvasSourceSet,
    CharSourceSet,
    DevcSourceSet,
    EnquSourceSet,
    MsagSourceSet,
    SicfSourceSet,
    SourceSet,
    TablSourceSet,
    ViewSourceSet,
    _FUNCTION_RE,
    _collect_fm_blocks,
    _derive_task,
    _docut_key_fm,
    _extract_function_modules,
    _fix_cloned_fm_rows,
    _fm_for_block,
    _load_template_records,
    _make_rule,
    _map_function_modules,
    _pick_template,
    _set_fm_title,
    _skip_block,
    _skip_to_own_terminator,
    _template_function_modules,
    _write_dd04_field,
    collect_sources,
    detect_object_type,
    generate_transport,
    generate_transport_multi,
)
from transport_templates import (
    ENV_VAR as _TEMPLATE_ENV_VAR,
    STEP_COUNTERS,
    TEMPLATES,
    TemplateError,
    check_templates as _check_templates,
    configure_templates as _configure_templates,
    template_dir as _template_dir,
)


_configure_msag_helpers(
    parse_nametabs=_parse_nametabs,
    make_description=_make_description,
    find_block_by_action=_find_block_by_action,
    write_field_by_name=_write_field_by_name,
    blank_row=_blank_row,
    replace_rows_in_block=_replace_rows_in_block,
    write_raw_field_by_name=_write_raw_field_by_name,
)


_configure_metadata_helpers(
    parse_nametabs=_parse_nametabs,
    make_description=_make_description,
    write_field_by_name=_write_field_by_name,
    find_block_by_action=_find_block_by_action,
    blank_row=_blank_row,
    replace_rows_in_block=_replace_rows_in_block,
    write_raw_field_by_name=_write_raw_field_by_name,
)

_configure_query_helpers(
    parse_nametabs=_parse_nametabs,
    find_block_by_action=_find_block_by_action,
    blank_row=_blank_row,
    replace_rows_in_block=_replace_rows_in_block,
    write_field_by_name=_write_field_by_name,
    write_raw_field_by_name=_write_raw_field_by_name,
)

_configure_sicf_helpers(
    parse_nametabs=_parse_nametabs,
    find_block=_find_block,
    write_field_by_name=_write_field_by_name,
    write_dd04_field=_write_dd04_field,
    blank_row=_blank_row,
    replace_rows_in_block=_replace_rows_in_block,
    make_description=_make_description,
)

_configure_xslt_helpers(
    parse_nametabs=_parse_nametabs,
    find_block=_find_block,
    write_field_by_name=_write_field_by_name,
    blank_row=_blank_row,
    replace_rows_in_block=_replace_rows_in_block,
)


_configure_enhancement_helpers(
    build_repos_key=_build_repos_key,
    find_block=_find_block,
)


_configure_type_helpers(
    write_field_by_name=_write_field_by_name,
    make_description=_make_description,
)


_configure_tobj_helpers(
    parse_nametabs=_parse_nametabs,
    find_block=_find_block,
    find_block_by_action=_find_block_by_action,
    write_field_by_name=_write_field_by_name,
    write_dd04_field=_write_dd04_field,
    blank_row=_blank_row,
    replace_rows_in_block=_replace_rows_in_block,
    remove_block=_remove_block,
)


_configure_special_helpers(
    parse_nametabs=_parse_nametabs,
    find_block=_find_block,
    write_field_by_name=_write_field_by_name,
    write_raw_field_by_name=_write_raw_field_by_name,
    write_dd04_field=_write_dd04_field,
    blank_row=_blank_row,
    replace_rows_in_block=_replace_rows_in_block,
    make_description=_make_description,
    fix_msag_language_key=_fix_msag_language_key,
)

_configure_engine_helpers(
    _apply_dtel_row=_apply_dtel_row,
    _apply_rename_to_key=_apply_rename_to_key,
    _apply_tran_row=_apply_tran_row,
    _apply_ttyp_row=_apply_ttyp_row,
    _apply_type_row=_apply_type_row,
    _build_class_member_row=_build_class_member_row,
    _build_component_row=_build_component_row,
    _collect_fm_blocks=_collect_fm_blocks,
    _docut_key_fm=_docut_key_fm,
    _emit_repos_rows=_emit_repos_rows,
    _emit_source_block=_emit_source_block,
    _encode_source_lines=_encode_source_lines,
    _extract_function_modules=_extract_function_modules,
    _find_block=_find_block,
    _fix_cloned_fm_rows=_fix_cloned_fm_rows,
    _fix_dtel_ddlanguage_key=_fix_dtel_ddlanguage_key,
    _fix_tran_tstct_language_key=_fix_tran_tstct_language_key,
    _fix_ttyp_ddlanguage_key=_fix_ttyp_ddlanguage_key,
    _fix_type_ddlanguage_key=_fix_type_ddlanguage_key,
    _fm_for_block=_fm_for_block,
    _get_field_text=_get_field_text,
    _interface_pool_boilerplate=_interface_pool_boilerplate,
    _make_cm_block_records=_make_cm_block_records,
    _make_cm_h_record=_make_cm_h_record,
    _make_description=_make_description,
    _make_repos_block_records=_make_repos_block_records,
    _map_function_modules=_map_function_modules,
    _map_source_to_includes=_map_source_to_includes,
    _normalize_repos_key=_normalize_repos_key,
    _parse_class_members=_parse_class_members,
    _parse_interface_members=_parse_interface_members,
    _parse_nametabs=_parse_nametabs,
    _regenerate_acid_rows=_regenerate_acid_rows,
    _regenerate_amsd_rows=_regenerate_amsd_rows,
    _regenerate_apis_rows=_regenerate_apis_rows,
    _regenerate_aplo_rows=_regenerate_aplo_rows,
    _regenerate_aqbg_rows=_regenerate_aqbg_rows,
    _regenerate_aqqu_rows=_regenerate_aqqu_rows,
    _regenerate_aqsg_rows=_regenerate_aqsg_rows,
    _regenerate_asfc_rows=_regenerate_asfc_rows,
    _regenerate_auth_rows=_regenerate_auth_rows,
    _regenerate_avar_rows=_regenerate_avar_rows,
    _regenerate_avas_rows=_regenerate_avas_rows,
    _regenerate_char_rows=_regenerate_char_rows,
    _regenerate_doma_rows=_regenerate_doma_rows,
    _regenerate_enho_badi_data_blob=_regenerate_enho_badi_data_blob,
    _regenerate_enho_data_blob=_regenerate_enho_data_blob,
    _regenerate_enqu_rows=_regenerate_enqu_rows,
    _regenerate_msag_rows=_regenerate_msag_rows,
    _regenerate_shlp_rows=_regenerate_shlp_rows,
    _regenerate_sicf_rows=_regenerate_sicf_rows,
    _regenerate_tabl_rows=_regenerate_tabl_rows,
    _regenerate_tobj_rows=_regenerate_tobj_rows,
    _regenerate_tran_tstcp=_regenerate_tran_tstcp,
    _regenerate_view_rows=_regenerate_view_rows,
    _regenerate_xslt_rows=_regenerate_xslt_rows,
    _rename_a_record=_rename_a_record,
    _rename_h_key=_rename_h_key,
    _replace_block_rows=_replace_block_rows,
    _replace_in_record=_replace_in_record,
    _replace_in_row=_replace_in_row,
    _set_fm_title=_set_fm_title,
    _set_meta_ldb=_set_meta_ldb,
    _skip_block=_skip_block,
    _skip_to_own_terminator=_skip_to_own_terminator,
    _template_function_modules=_template_function_modules,
    _write_field_by_name=_write_field_by_name,
    regenerate_devc_rows=regenerate_devc_rows,
)

from transport_native_support import (
    configure_helpers as _configure_native_helpers,
    _CHAR_TYPES,
    A_SRCSYSTEM_OFF,
    A_AUTHOR_OFF,
    A_AUTHOR_LEN,
    A_MASTERLANG_OFF,
    _ENDCLASS_RE,
    _SECTION_RE,
    _CLASS_LOCAL_STUBS,
    _DDIC_SYSTEM_COLUMNS,
    _XSLT_LINE_CHARS,
    _XSLT_LINE_BYTES,
    _XSLT_ROW_HEAD,
    _XSLT_TABLE_HEAD,
    _CONSTANT_RE,
    _SECTION_EXPOSURE,
    _SEO_HEADER_DEFAULTS,
    _REQUEST_LEVEL_TABLES,

    _set_meta_subc,
    _split_definition_sections,
    _drop_object_index,
    _textpool_block,
    _apply_fm_interfaces,
    _row_with_long_values,
    _regenerate_adobe_form_rows,
    _write_typed_value,
    _key_columns,
    _fresh_row,
    _apply_author_to_metadata_rows,
    _table_blocks,
    _set_block_rows,
    _regenerate_table_content,
    _first,
    _table_content,
    _apply_xml_columns,
    _replace_xslt_source_table,
    _split_outside_literals,
    _abap_statements,
    _parse_seo_declarations,
    _seo_row,
    _apply_seo_header,
    _ensure_trdir_nametab,
    _set_request_entry_count,
    _header_nametab_blocks,
    _transport_object_name,
)

_configure_native_helpers(**{k: v for k, v in globals().copy().items() if not k.startswith("__") and k != "configure_helpers"})


# Shared dependencies for the native-import corrections in extracted modules.
import transport_record_renames as _native_transport_record_renames
_native_transport_record_renames.A_AUTHOR_LEN = A_AUTHOR_LEN
_native_transport_record_renames.A_AUTHOR_OFF = A_AUTHOR_OFF
_native_transport_record_renames.A_MASTERLANG_OFF = A_MASTERLANG_OFF
_native_transport_record_renames.A_SRCSYSTEM_OFF = A_SRCSYSTEM_OFF
import transport_source_blocks as _native_transport_source_blocks
_native_transport_source_blocks._CLASS_LOCAL_STUBS = _CLASS_LOCAL_STUBS
_native_transport_source_blocks._base36 = _base36
_native_transport_source_blocks._build_repos_key = _build_repos_key
_native_transport_source_blocks._class_pool_boilerplate = _class_pool_boilerplate
_native_transport_source_blocks._map_class_sources = _map_class_sources
_native_transport_source_blocks._split_class_source = _split_class_source
_native_transport_source_blocks._split_definition_sections = _split_definition_sections
import transport_generation as _native_transport_generation
_native_transport_generation._drop_object_index = _drop_object_index
_native_transport_generation._ensure_trdir_nametab = _ensure_trdir_nametab
_native_transport_generation._header_nametab_blocks = _header_nametab_blocks
_native_transport_generation._set_request_entry_count = _set_request_entry_count
import transport_regenerators.ddic as _native_transport_regenerators_ddic
_native_transport_regenerators_ddic._apply_xml_columns = _apply_xml_columns
_native_transport_regenerators_ddic._fix_dtel_ddlanguage_key = _fix_dtel_ddlanguage_key
import transport_regenerators.services as _native_transport_regenerators_services
_native_transport_regenerators_services.sicf_node_guid = sicf_node_guid
import transport_engine as _native_transport_engine
_native_transport_engine._apply_author_to_metadata_rows = _apply_author_to_metadata_rows
_native_transport_engine._apply_dtel_row = _apply_dtel_row
_native_transport_engine._apply_fm_interfaces = _apply_fm_interfaces
_native_transport_engine._apply_rename_to_key = _apply_rename_to_key
_native_transport_engine._apply_seo_header = _apply_seo_header
_native_transport_engine._apply_tran_row = _apply_tran_row
_native_transport_engine._apply_ttyp_row = _apply_ttyp_row
_native_transport_engine._apply_type_row = _apply_type_row
_native_transport_engine._build_class_member_row = _build_class_member_row
_native_transport_engine._build_component_row = _build_component_row
_native_transport_engine._build_repos_key = _build_repos_key
_native_transport_engine._collect_fm_blocks = _collect_fm_blocks
_native_transport_engine._docut_key_fm = _docut_key_fm
_native_transport_engine._emit_repos_rows = _emit_repos_rows
_native_transport_engine._emit_source_block = _emit_source_block
_native_transport_engine._extract_class_blocks = _extract_class_blocks
_native_transport_engine._extract_function_modules = _extract_function_modules
_native_transport_engine._find_block = _find_block
_native_transport_engine._fix_cloned_fm_rows = _fix_cloned_fm_rows
_native_transport_engine._fix_dtel_ddlanguage_key = _fix_dtel_ddlanguage_key
_native_transport_engine._fix_tran_tstct_language_key = _fix_tran_tstct_language_key
_native_transport_engine._fix_ttyp_ddlanguage_key = _fix_ttyp_ddlanguage_key
_native_transport_engine._fix_type_ddlanguage_key = _fix_type_ddlanguage_key
_native_transport_engine._fm_for_block = _fm_for_block
_native_transport_engine._get_field_text = _get_field_text
_native_transport_engine._interface_pool_boilerplate = _interface_pool_boilerplate
_native_transport_engine._make_cm_block_records = _make_cm_block_records
_native_transport_engine._make_cm_h_record = _make_cm_h_record
_native_transport_engine._make_description = _make_description
_native_transport_engine._make_repos_block_records = _make_repos_block_records
_native_transport_engine._map_function_modules = _map_function_modules
_native_transport_engine._map_source_to_includes = _map_source_to_includes
_native_transport_engine._normalize_repos_key = _normalize_repos_key
_native_transport_engine._parse_class_members = _parse_class_members
_native_transport_engine._parse_interface_members = _parse_interface_members
_native_transport_engine._parse_nametabs = _parse_nametabs
_native_transport_engine._regenerate_acid_rows = _regenerate_acid_rows
_native_transport_engine._regenerate_adobe_form_rows = _regenerate_adobe_form_rows
_native_transport_engine._regenerate_amsd_rows = _regenerate_amsd_rows
_native_transport_engine._regenerate_apis_rows = _regenerate_apis_rows
_native_transport_engine._regenerate_aplo_rows = _regenerate_aplo_rows
_native_transport_engine._regenerate_aqbg_rows = _regenerate_aqbg_rows
_native_transport_engine._regenerate_aqqu_rows = _regenerate_aqqu_rows
_native_transport_engine._regenerate_aqsg_rows = _regenerate_aqsg_rows
_native_transport_engine._regenerate_asfc_rows = _regenerate_asfc_rows
_native_transport_engine._regenerate_auth_rows = _regenerate_auth_rows
_native_transport_engine._regenerate_avar_rows = _regenerate_avar_rows
_native_transport_engine._regenerate_avas_rows = _regenerate_avas_rows
_native_transport_engine._regenerate_char_rows = _regenerate_char_rows
_native_transport_engine._regenerate_doma_rows = _regenerate_doma_rows
_native_transport_engine._regenerate_enho_badi_data_blob = _regenerate_enho_badi_data_blob
_native_transport_engine._regenerate_enho_data_blob = _regenerate_enho_data_blob
_native_transport_engine._regenerate_enqu_rows = _regenerate_enqu_rows
_native_transport_engine._regenerate_msag_rows = _regenerate_msag_rows
_native_transport_engine._regenerate_shlp_rows = _regenerate_shlp_rows
_native_transport_engine._regenerate_sicf_rows = _regenerate_sicf_rows
_native_transport_engine._regenerate_tabl_rows = _regenerate_tabl_rows
_native_transport_engine._regenerate_table_content = _regenerate_table_content
_native_transport_engine._regenerate_tobj_rows = _regenerate_tobj_rows
_native_transport_engine._regenerate_tran_tstcp = _regenerate_tran_tstcp
_native_transport_engine._regenerate_view_rows = _regenerate_view_rows
_native_transport_engine._regenerate_xslt_rows = _regenerate_xslt_rows
_native_transport_engine._rename_a_record = _rename_a_record
_native_transport_engine._rename_h_key = _rename_h_key
_native_transport_engine._replace_block_rows = _replace_block_rows
_native_transport_engine._replace_in_record = _replace_in_record
_native_transport_engine._replace_in_row = _replace_in_row
_native_transport_engine._set_fm_title = _set_fm_title
_native_transport_engine._set_meta_ldb = _set_meta_ldb
_native_transport_engine._set_meta_subc = _set_meta_subc
_native_transport_engine._skip_block = _skip_block
_native_transport_engine._skip_to_own_terminator = _skip_to_own_terminator
_native_transport_engine._table_content = _table_content
_native_transport_engine._template_function_modules = _template_function_modules
_native_transport_engine._textpool_block = _textpool_block
_native_transport_engine._write_field_by_name = _write_field_by_name
_native_transport_engine.regenerate_devc_rows = regenerate_devc_rows
import transport_members as _native_transport_members
_native_transport_members._extract_class_blocks = _extract_class_blocks
_native_transport_members._parse_seo_declarations = _parse_seo_declarations
import transport_cofile as _native_transport_cofile
_native_transport_cofile.STEP_COUNTERS = STEP_COUNTERS
import transport_regenerators.tobj as _native_transport_regenerators_tobj
_native_transport_regenerators_tobj._fresh_row = _fresh_row
import transport_regenerators.xslt as _native_transport_regenerators_xslt
_native_transport_regenerators_xslt._replace_xslt_source_table = _replace_xslt_source_table

# -- CLI --------------------------------------------------------------------

def main():
    # The generator prints UTF-8 characters (arrows, SAP texts); a cp1252
    # console would crash on them. Reconfigure when possible.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Generate SAP transport files from an abapGit repository")
    parser.add_argument("repo", type=Path, nargs="?",
                        help="Path to abapGit repository root (containing src/)")
    parser.add_argument("--templates", type=Path, default=None,
                        help="Template directory with templates.json (default: "
                             f"${_TEMPLATE_ENV_VAR}, else the bundled probes/)")
    parser.add_argument("--check-templates", action="store_true",
                        help="Validate the template directory and exit")
    parser.add_argument("--output", "-o", type=Path, default=None,
                        help="Output directory (default: repo/transport_output/)")
    parser.add_argument("--request", "-r", type=str, default=None,
                        help="Transport request number (required), e.g. DEVK900001")
    parser.add_argument("--sid", type=str, default=None,
                        help="SAP system ID (default: the request's first "
                             "three characters; must match them)")
    parser.add_argument("--object", type=str, default=None,
                        help="Transport only this object (default: all "
                             "detected objects in one transport)")
    parser.add_argument("--package", type=str, default=None,
                        help="ABAP package (DEVCLASS) the objects belong to, "
                             "e.g. /NAMESPACE/PACKAGE or ZPACKAGE. Without it the "
                             "template's package ships and the import MOVES "
                             "the objects into it.")
    parser.add_argument("--author", type=str, default=None,
                        help="TADIR author for generated objects (default: "
                             "preserve the template author)")
    parser.add_argument("--list", action="store_true",
                        help="List detected objects and exit")
    args = parser.parse_args()

    _configure_templates(args.templates)
    if args.check_templates:
        problems = _check_templates()
        for problem in problems:
            print(f"ERROR: {problem}")
        if not problems:
            print(f"Templates OK: {len(TEMPLATES)} in {_template_dir()}")
        return 2 if problems else 0
    if args.repo is None:
        parser.error("repo is required unless --check-templates is given")

    src_dir = args.repo / "src"
    if not src_dir.is_dir():
        print(f"ERROR: {src_dir} not found -- not an abapGit repo?")
        return 1

    objects = detect_object_type(src_dir)
    skipped = unsupported_files(src_dir)
    if skipped:
        print(f"Skipping {len(skipped)} file(s) of unsupported object types "
              f"(NOT part of the transport):")
        for path in skipped:
            print(f"  {path.relative_to(src_dir)}")
    if not objects:
        print(f"ERROR: no ABAP objects found in {src_dir}")
        return 1

    print(f"Found {len(objects)} objects in {args.repo.resolve().name}:")
    for obj in objects:
        print(f"  {obj['type']:5s}  {obj['name']}")

    if args.list:
        return 0

    # Default: transport ALL objects in one transport. --object picks a single
    # one instead.
    targets = objects
    if args.object:
        matches = [o for o in objects if o['name'].upper() == args.object.upper()]
        if not matches:
            print(f"ERROR: object {args.object} not found")
            return 1
        targets = [matches[0]]

    # Validate the identity before it reaches file names, transport records,
    # or release metadata. A request is always tied to exactly one SID.
    try:
        if not args.request:
            raise ValueError("--request is required, e.g. DEVK900001")
        # The SID defaults to the request's own system (its first three
        # characters); an explicit --sid must agree with it.
        new_request, sid = validate_transport_identity(
            args.request, args.sid or str(args.request).strip()[:3])
        package = normalize_package(args.package) if args.package else ""
        author = normalize_author(args.author) if args.author else ""
    except ValueError as exc:
        print(f"ERROR: {exc}")
        if args.package and (":" in args.package or "\\" in args.package):
            # Git Bash rewrites a leading /NAMESPACE/ into a Windows path
            print("Git Bash rewrites /NAMESPACE/... into C:/...  -- prefix the")
            print("command with MSYS_NO_PATHCONV=1 or use PowerShell.")
        return 2

    print(f"\nGenerating transport for {len(targets)} object(s):")
    for obj in targets:
        print(f"  {obj['type']:5s}  {obj['name']}")
    print(f"  Request: {new_request}")
    print(f"  SID:     {sid}")
    if package:
        print(f"  Package: {package}")
    else:
        print("  Package: (not set) WARNING - the template's package will be")
        print("           shipped and the import will MOVE the objects into")
        print("           it. Pass --package <DEVCLASS> to keep them put.")
    if author:
        print(f"  Author:  {author}")

    # Collect source files
    obj_tuples = []
    for obj in targets:
        object_dir = obj['xml'].parent if obj.get('xml') else src_dir
        sources = collect_sources(object_dir, obj['type'], obj['name'])
        ldb = _extract_ldb(obj.get('xml')) if obj['type'] == 'PROG' else ""
        if ldb:
            print(f"  LDB for {obj['name']}: {ldb}")
        print(f"  Sources for {obj['name']}: {list(sources.keys())}")
        name = _transport_object_name(obj['type'], obj['name'], sources)
        if name != obj['name']:
            print(f"  {obj['type']} object name: {name!r}")
        obj_tuples.append((obj['type'], name, sources, ldb))

    # Generate
    try:
        data_bytes, cofile_bytes = generate_transport_multi(
            obj_tuples, new_request, sid=sid,
            package=package,
            language=master_language(src_dir),
            author=author,
        )
    except TemplateError as exc:
        print(f"ERROR: {exc}")
        return 2

    out_dir = args.output or (args.repo / "transport_output")
    out_dir.mkdir(parents=True, exist_ok=True)

    # Build output filenames
    digits = new_request[len(sid) + 1:] if new_request.upper().startswith(sid.upper()) else new_request[4:]
    data_path = out_dir / f"R{digits}.{sid}"
    cofile_path = out_dir / f"K{digits}.{sid}"

    data_path.write_bytes(data_bytes)
    cofile_path.write_bytes(cofile_bytes)

    print(f"\nWrote:")
    print(f"  {data_path}   ({len(data_bytes):,} bytes)")
    print(f"  {cofile_path}   ({len(cofile_bytes):,} bytes)")
    print(f"\nImport via STMS: upload both files to /usr/sap/trans/ then add request {new_request}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
