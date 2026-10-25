"""DDIC object regeneration helpers.

This module contains the data-element-specific regeneration code extracted from
the compatibility facade. The facade injects shared row-writing helpers after
it has initialized, avoiding a reverse import back into the CLI module.
"""

from collections.abc import Callable

from sap_transport_records import Record


_write_dd04_field_impl: Callable | None = None
_make_description_impl: Callable | None = None
_helpers: dict[str, Callable] = {}


def configure_dtel_helpers(
    write_dd04_field: Callable,
    make_description: Callable,
    **helpers: Callable,
) -> None:
    """Configure shared facade helpers needed by the DDIC implementations."""
    global _write_dd04_field_impl, _make_description_impl
    _write_dd04_field_impl = write_dd04_field
    _make_description_impl = make_description
    _helpers.update(helpers)


def _write_dd04_field(row: Record, fields: list, fname: str, value: str) -> Record:
    if _write_dd04_field_impl is None:
        raise RuntimeError("DTEL helpers have not been configured")
    return _write_dd04_field_impl(row, fields, fname, value)


def _make_description(obj_name: str) -> str:
    if _make_description_impl is None:
        raise RuntimeError("DTEL helpers have not been configured")
    return _make_description_impl(obj_name)


def _helper(name: str) -> Callable:
    try:
        return _helpers[name]
    except KeyError as exc:
        raise RuntimeError(f"DDIC helper {name!r} has not been configured") from exc


def _parse_nametabs(*args, **kwargs):
    return _helper("parse_nametabs")(*args, **kwargs)


def _find_block_by_action(*args, **kwargs):
    return _helper("find_block_by_action")(*args, **kwargs)


def _write_field_by_name(*args, **kwargs):
    return _helper("write_field_by_name")(*args, **kwargs)


def _remove_block(*args, **kwargs):
    return _helper("remove_block")(*args, **kwargs)


def _blank_row(*args, **kwargs):
    return _helper("blank_row")(*args, **kwargs)


def _replace_rows_in_block(*args, **kwargs):
    return _helper("replace_rows_in_block")(*args, **kwargs)


def _fix_msag_language_key(*args, **kwargs):
    return _helper("fix_msag_language_key")(*args, **kwargs)


# DD04L fields taken from the repo's <DD04V> when present. DATATYPE/LENG/
# DECIMALS/OUTPUTLEN are only serialized by abapGit when they are NOT simply
# derivable from DOMNAME (verified against several real abapGit-managed
# repos: a plain domain reference like DOMNAME=XFELD ships with no
# DATATYPE/LENG/DECIMALS at all) -- when a domain is set and the repo does
# not carry these, the template's stale values are blanked rather than
# shipped, on the theory that the target's DDIC activation (G-phase)
# re-derives them from the domain, the same way CLAS relies on the class
# builder to regenerate method signatures from the CU source.
#
# CAUTION (Opus review finding D3, 2026-08-15): this theory is NOT settled.
# The template's own DD04L row -- genuine R3trans export content for a
# plain domain-referencing element -- carries DATATYPE/LENG/OUTPUTLEN fully
# populated alongside DOMNAME, even though abapGit's own XML for the same
# kind of object omits them. abapGit's deserializer goes through an
# explicit DDIF_DTEL_PUT + activate call; R3trans just writes the row
# directly. "abapGit doesn't need to ship it" does not prove "a plain
# R3trans import doesn't need it" -- this project's own standing rule has
# been "the real export is always right," and the real export disagrees
# with the blanking choice made here. Blanking is the best available
# default without shipping a DOMA lookup (out of scope), but is UNVERIFIED
# against a real import -- _apply_dtel_row prints a warning whenever it
# blanks these fields so a user knows to check the imported result.
_DTEL_DD04L_FIELDS = ("DOMNAME", "DATATYPE", "LENG", "DECIMALS", "OUTPUTLEN",
                      "HEADLEN", "SCRLEN1", "SCRLEN2", "SCRLEN3",
                      "REFKIND", "REFTYPE", "LOWERCASE", "SIGNFLAG",
                      "CONVEXIT", "DTELMASTER")
_DTEL_DD04L_DERIVED = ("DATATYPE", "LENG", "DECIMALS", "OUTPUTLEN")

# DD04T: the master language's texts travel directly in <DD04V> (abapGit
# skips writing a separate <DD04_TEXTS> entry for the master language).
# Additional (non-master) languages are NOT implemented in this round -- see
# docs/dtel-support.md.
_DTEL_DD04T_FIELDS = ("DDLANGUAGE", "DDTEXT", "REPTEXT",
                      "SCRTEXT_S", "SCRTEXT_M", "SCRTEXT_L")

# Text fields that fall back to a name-derived description (_make_description)
# when the repo's .dtel.xml doesn't carry them, instead of leaking the
# template's own stale text (e.g. the reference object's German "Eindeutige
# ID") into an unrelated generated object.
_DTEL_DD04T_TEXT_FALLBACK = ("DDTEXT", "REPTEXT",
                             "SCRTEXT_S", "SCRTEXT_M", "SCRTEXT_L")



def apply_dtel_row(row: Record, table: str, fields: list,
                    dtel_fields: dict, obj_name: str = "") -> Record:
    """
    Overwrite a DD04L or DD04T row's domain/type/text fields from the repo's
    .dtel.xml. Called AFTER the generic per-row rename (ROLLNAME, request
    number) has already run -- this fills in content that is genuinely new
    per object, not a renamed template value. Fields the repo's XML doesn't
    carry either keep the template's value (harmless boilerplate, e.g.
    VERSION-like admin fields) or, for the DOMNAME / DATATYPE-LENG-DECIMALS-
    OUTPUTLEN pair, are blanked according to whichever side the repo's XML
    actually specifies (see _DTEL_DD04L_DERIVED) -- a data element is either
    domain-referencing (DOMNAME set) or a direct/built-in type (DATATYPE
    set), never a stale mix of one object's domain with another's explicit
    type. Text fields (DD04T) missing from the XML fall back to a name-
    derived description instead of the template's own stale text (see
    _DTEL_DD04T_TEXT_FALLBACK).
    """
    if table == "DD04L":
        mapping = _DTEL_DD04L_FIELDS
    elif table == "DD04T":
        mapping = _DTEL_DD04T_FIELDS
    else:
        return row
    # A domain-typed data element ships without DATATYPE/LENG/...: DDIC
    has_domain = bool(dtel_fields.get("DOMNAME"))
    has_direct_type = bool(dtel_fields.get("DATATYPE"))
    # activation derives them from the domain (confirmed by test imports).
    for fname in mapping:
        if fname in _DTEL_DD04T_TEXT_FALLBACK:
            # A self-closing tag (<REPTEXT/>, D6) parses to "" -- treat that
            # the same as the tag being absent (fall back to a name-derived
            # description) rather than shipping empty label text, which is
            # no more useful than the template's stale one.
            value = dtel_fields.get(fname)
            row = _write_dd04_field(
                row, fields, fname, value or _make_description(obj_name))
        elif fname in dtel_fields:
            # Not a text-fallback field: an explicit empty value (e.g. a
            # self-closed flag like <LOWERCASE/>) is meaningful and written
            # as-is (clears the template's stale flag), unlike text fields.
            row = _write_dd04_field(row, fields, fname, dtel_fields[fname])
        elif fname == "DOMNAME" and has_direct_type:
            # Explicit type given, no domain reference -> clear the
            # template's stale DOMNAME rather than leave a domain assigned
            # to what should be a direct-type element (D2).
            row = _write_dd04_field(row, fields, fname, "")
        elif fname in _DTEL_DD04L_DERIVED and (has_domain or has_direct_type):
            # Type is resolved one way or the other (domain or explicit),
            # but this particular field (typically OUTPUTLEN, which none of
            # the real .dtel.xml samples surveyed ever carry even alongside
            # an explicit DATATYPE/LENG) isn't in the XML -- blank it rather
            # than leave the template's unrelated stale value (D2).
            row = _write_dd04_field(row, fields, fname, "")
    return row


def fix_dtel_ddlanguage_key(h_rec: Record, new_lang: str) -> Record:
    """
    DD04T's H-record key packs ROLLNAME + DDLANGUAGE(1) + '*' (verified
    against the template: '<name, 30 chars>D*'). The generic
    rename only touches the ROLLNAME portion, so the language character
    would otherwise still read the template's original language -- a
    '00REP ' action's implicit delete-then-insert would then target a
    different (usually nonexistent, but on an overwrite import possibly
    stale) row than the one actually being inserted. Overwrite just that
    one character (same width, no re-padding needed) with the repo's own
    DDLANGUAGE from the .dtel.xml.
    """
    if not new_lang:
        return h_rec
    key_area = h_rec.payload[48:]
    text = key_area.decode("latin-1")
    star = text.rfind("*")
    if star < 1:
        return h_rec
    lang_char = text[star - 1]
    # SPRAS (language key) values are a single uppercase ASCII letter
    # (verified: 'D'/'E' in the reference exports) -- guard against
    # mis-locating the language position in a key shaped differently than
    # expected (e.g. an unpadded 30-char ROLLNAME abutting the '*' with no
    # language byte at all), which would otherwise silently corrupt an
    # unrelated character instead of the intended language code.
    if not ("A" <= lang_char <= "Z"):
        return h_rec
    text = text[:star - 1] + new_lang[0] + text[star:]
    payload = bytearray(h_rec.payload)
    payload[48:] = text.encode("latin-1")
    return Record(offset=h_rec.offset, rtype=h_rec.rtype,
                  payload=bytes(payload), fragments=h_rec.fragments)




def regenerate_tabl_rows(records: list, obj_name: str, tabl_meta: dict) -> list:
    """
    Regenerate DD02L (header)/DD02T (description)/DD03L (field list, one row
    per repo field -- arbitrary count, like MSAG's T100) from the repo's
    .tabl.xml. Mirrors _regenerate_msag_rows's shape: a post-pass over an
    already-renamed record list, called once at the end of
    _process_template_records.

    Also handles DD09L (technical settings -- buffering, table category):
    the template this generator ships (see TEMPLATES["TABL"]) was spliced
    from a real transparent table and so carries its own
    DD09L block natively. When the repo's .tabl.xml has a <DD09L> element
    (a real transparent table), that block's TABKAT/TABART/BUFALLOW/
    AS4LOCAL are overwritten from the repo's values -- the same "overwrite
    what the XML provides, leave the rest at the template's own value"
    convention DD02L uses. When the repo's .tabl.xml has NO <DD09L> element
    at all (the structure case, TABCLASS=INTTAB) the whole block is DROPPED
    from the output -- a real structure export genuinely carries no DD09L
    block (confirmed: abap2xlsx's zexcel_s_rtf.tabl.xml), so shipping the
    template's own (donor-object) technical settings for an object that
    isn't a transparent table would be actively wrong, not just unused.
    See docs/tabl-support.md.
    """
    nametabs = _parse_nametabs(records)
    language = (tabl_meta.get("ddlanguage") or tabl_meta.get("masterlang")
                or "D")[:1] or "D"
    ddtext = tabl_meta.get("ddtext") or _make_description(obj_name)
    fields = tabl_meta.get("fields") or []

    # --- DD02L: single row, the table header (see _apply_xml_columns for
    # why XML-absent columns are reset rather than left at the template's
    # values). ---
    dd02v = dict(tabl_meta.get("dd02v") or {})
    dd02v.setdefault("MASTERLANG", language)
    dd02l_fields = nametabs.get("DD02L")
    dd02l_blk = _find_block_by_action(records, "DD02L", "00REP ")
    if dd02l_blk is not None and dd02l_fields:
        for ridx in dd02l_blk[1]:
            records[ridx] = _apply_xml_columns(
                records[ridx], dd02l_fields, dd02v, keep=("TABNAME",))
    elif dd02l_fields is None:
        print("  WARNING: template has no DD02L nametab -- "
              "table header cannot be regenerated")

    # --- DD09L: single row, technical settings (table category, data
    # class, buffering). Populated when the repo's .tabl.xml carries a
    # <DD09L> element (a real transparent table); dropped ENTIRELY (H
    # through E, not just its rows) when it doesn't -- see the
    # drop-unmatched reasoning in the function docstring and in
    # _remove_block's own docstring. ---
    dd09l_meta = tabl_meta.get("dd09l") or {}
    dd09l_fields = nametabs.get("DD09L")
    dd09l_blk = _find_block_by_action(records, "DD09L", "00REP ")
    if dd09l_blk is not None:
        if dd09l_meta and dd09l_fields:
            for ridx in dd09l_blk[1]:
                records[ridx] = _apply_xml_columns(
                    records[ridx], dd09l_fields, dd09l_meta, keep=("TABNAME",))
            print(f"  TABL DD09L for {obj_name}: TABKAT="
                  f"{dd09l_meta.get('TABKAT', '')!r} TABART="
                  f"{dd09l_meta.get('TABART', '')!r} BUFALLOW="
                  f"{dd09l_meta.get('BUFALLOW', '')!r}")
        else:
            _remove_block(records, dd09l_blk)
            print(f"  TABL DD09L for {obj_name}: dropped -- repo's "
                  f".tabl.xml has no <DD09L> (not a transparent table, or "
                  f"abapGit didn't serialize one)")

    # --- DD02T: single row, language + description text. The H-key packs
    # TABNAME(padded)+DDLANGUAGE+'*' -- the exact same shape as DTEL's
    # DD04T key, so _fix_dtel_ddlanguage_key (fully generic despite the
    # name: it only looks at "name padded to field width, then one
    # language byte, then '*'") is reused here rather than reimplemented. ---
    dd02t_fields = nametabs.get("DD02T")
    dd02t_blk = _find_block_by_action(records, "DD02T", "00REP ")
    if dd02t_blk is not None and dd02t_fields:
        for ridx in dd02t_blk[1]:
            row = _write_field_by_name(records[ridx], dd02t_fields,
                                       "DDLANGUAGE", language)
            row = _write_field_by_name(row, dd02t_fields, "DDTEXT", ddtext)
            records[ridx] = row
        records[dd02t_blk[0]] = _fix_dtel_ddlanguage_key(
            records[dd02t_blk[0]], language)

    # --- DD03L: one '00REP ' row per repo field. Rows with no usable type
    # information (neither ROLLNAME nor DATATYPE -- e.g. a nested-structure
    # .INCLUDE, COMPTYPE='S', which this generator does not support, see
    # docs/tabl-support.md) are dropped with a warning, matching the
    # project's drop-unmatched rule. ---
    dd03l_fields = nametabs.get("DD03L")
    dd03l_blk = _find_block_by_action(records, "DD03L", "00REP ")
    if dd03l_blk is not None and dd03l_fields:
        donor = records[dd03l_blk[1][0]] if dd03l_blk[1] else None
        new_rows = []
        position = 0
        any_type_blanked = False
        for f in fields:
            if not (f.get("ROLLNAME") or f.get("DATATYPE")
                    or f.get("PRECFIELD")):
                print(f"  WARNING: skipping field {f['FIELDNAME']} -- "
                      f"no ROLLNAME, DATATYPE or PRECFIELD, cannot "
                      f"determine type")
                continue
            position += 1
            row = (Record(offset=0, rtype=" ", payload=donor.payload, fragments=1)
                   if donor is not None else _blank_row(dd03l_fields))
            # Every DD03P column by name: includes (.INCLUDE + PRECFIELD),
            # reference fields of amounts/quantities (REFTABLE/REFFIELD),
            # check tables etc. all live in columns of this one row.
            values = dict(f)
            values.setdefault("ADMINFIELD", "0")
            values["POSITION"] = str(position)
            row = _apply_xml_columns(row, dd03l_fields, values,
                                     keep=("TABNAME",))
            if f.get("ROLLNAME") and not (f.get("INTLEN") or f.get("LENG")
                                          or f.get("DECIMALS")):
                any_type_blanked = True
            new_rows.append(row)
        _replace_rows_in_block(records, dd03l_blk, new_rows)
        print(f"  TABL fields for {obj_name}: {len(new_rows)} "
              f"(was {len(dd03l_blk[1])} in the template)")
    elif fields:
        print("  WARNING: template has no DD03L REPC block -- "
              "fields cannot be regenerated")

    return records


# -- Database view (VIEW) metadata -------------------------------------------
#
# A DDIC database view has no ABAP source at all -- like TABL, the whole
# object is DDIC metadata, serialized by abapGit as <name>.view.xml. Schema
# confirmed against several real .view.xml files: six single-base-table
# views with no join at all (ABAP-SDK-for-Azure's zadf_v_config.view.xml
# and five siblings, all VIEWCLASS='C', <DD26V_TABLE> with exactly one
# <DD26V> whose TABPOS='0001') and two genuine multi-base-table joins
# pulled via `gh search code` (rayatus/sapinterfacemonitor's
# zvintfmonitor.view.xml, a 4-table join; abapGit-tests/DDIC_integration's
# zag_view_help.view.xml, a 2-table VIEWCLASS='H' help view) -- both confirm
# <DD26V> carries FORTABNAME/FORFIELD/FORDIR for every non-root base table.
#
# On the transport side, a VIEW object touches (at minimum) four tables:
#
# - DD25L -- the header row: view name, AGGTYPE, ROOTTAB, VIEWCLASS,
#   CUSTOMAUTH, GLOBALFLAG, etc.
# - DD25T -- one row per language: the view's short description.
# - DD26S -- one row per base table: TABNAME, TABPOS, and (for every table
#   beyond the root) the join condition's own FORTABNAME/FORFIELD/FORDIR.
# - DD27S -- one row per view field: VIEWFIELD/TABNAME/FIELDNAME/KEYFLAG/
#   RDONLY.
#
# Real multi-base-table .view.xml samples also carry a <DD28J_TABLE>
# (design-time join-condition detail: LTAB/LFIELD/OPERATOR/RTAB/RFIELD/
# SOURCE/FRKTAB/FRKFIELD/FRKDIR) -- but the real transport-side reference
# object this generator's template was spliced from (a
# genuine 7-table join) carries NO DD28J block anywhere in its own section,
# confirmed by a stream-wide scan of the WHOLE reference transport, not
# just the object's own slice (see build_view_template.py). DD26S's own
# FORTABNAME/FORFIELD/FORDIR already describe the join adequately for
# DDIC activation; DD28J appears to be design-time-only metadata SAP
# regenerates from DD26S, not something R3trans actually transports. Not
# implemented -- same "no real transport-side reference data" reasoning as
# TABL's DD05M/DD08V (see docs/tabl-support.md) and docs/view-support.md.


class ViewSourceSet(dict):
    """An (always empty -- VIEW has no source files) sources dict that
    carries the metadata read from the repo's .view.xml alongside it, the
    same pattern as TablSourceSet/MsagSourceSet."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.view_meta = {}          # see object_handlers.view.parse_view_xml




def regenerate_view_rows(records: list, obj_name: str, view_meta: dict) -> list:
    """
    Regenerate DD25L (header)/DD25T (description)/DD26S (base-table list,
    arbitrary count)/DD27S (view-field list, arbitrary count) from the
    repo's .view.xml. Mirrors _regenerate_tabl_rows's shape -- a post-pass
    over an already-renamed record list, called once at the end of
    _process_template_records.

    DD29L, DDTYPES, and SFW_VIEWFIELD are deliberately NOT touched here:
    their only per-object content is the view's own name (CONDNAME/
    VIEWNAME/TYPENAME, all equal to the object's own R3TR name, unlike
    TOBJ's split OBJECTNAME -- confirmed directly against the real
    template view object before writing this function), which the
    generic per-record substring rename already handles for free -- same
    "already worked for free" mechanism TABL's own TABNAME rename uses
    (see docs/tabl-support.md), verified here rather than assumed.
    """
    nametabs = _parse_nametabs(records)
    language = (view_meta.get("ddlanguage") or "D")[:1] or "D"
    ddtext = view_meta.get("ddtext") or _make_description(obj_name)
    tables = view_meta.get("tables") or []
    fields = view_meta.get("fields") or []

    # --- DD25L: single row, header fields present in the XML overwrite the
    # template's own -- fields the XML doesn't carry (AUTHCLASS, buffering-
    # like flags, AS4USER/AS4DATE/AS4TIME, ...) keep the template's value,
    # the same "leave it" default TABL's DD02L / MSAG's T100A convention
    # already established. ---
    dd25l_fields = nametabs.get("DD25L")
    dd25l_blk = _find_block_by_action(records, "DD25L", "00REP ")
    if dd25l_blk is not None and dd25l_fields:
        for ridx in dd25l_blk[1]:
            row = records[ridx]
            # XML-absent columns are initial (see _apply_xml_columns) --
            # e.g. the template view's CUSTOMAUTH must not ship
            row = _apply_xml_columns(row, dd25l_fields,
                                     view_meta.get("dd25v") or {},
                                     keep=("VIEWNAME",))
            records[ridx] = row
    elif dd25l_fields is None:
        print("  WARNING: template has no DD25L nametab -- "
              "view header cannot be regenerated")

    # --- DD25T: single row, language + description text. The H-key packs
    # DDLANGUAGE(1) FIRST, then VIEWNAME(padded), with NO trailing '*'
    # marker dependency -- the OPPOSITE arrangement from DTEL's DD04T/
    # TABL's DD02T (NAME + LANG + '*'), and the SAME shape MSAG's
    # T100/T100T and TRAN's TSTCT have. Verified directly against the real
    # object's own DD25T H-record (payload[48] == 'D', immediately before
    # the view name) before reusing _fix_msag_language_key, per the
    # task brief's explicit warning not to assume _fix_dtel_ddlanguage_key's
    # shape applies here just because DD25T "looks like" DD02T/DD04T. ---
    dd25t_fields = nametabs.get("DD25T")
    dd25t_blk = _find_block_by_action(records, "DD25T", "00REP ")
    if dd25t_blk is not None and dd25t_fields:
        for ridx in dd25t_blk[1]:
            row = _write_field_by_name(records[ridx], dd25t_fields,
                                       "DDLANGUAGE", language)
            row = _write_field_by_name(row, dd25t_fields, "DDTEXT", ddtext)
            records[ridx] = row
        records[dd25t_blk[0]] = _fix_msag_language_key(
            records[dd25t_blk[0]], language)

    # --- DD26S: one '00REP ' row per repo base table (<DD26V>), arbitrary
    # count -- the same "synthesize N rows from a list via the nametab-
    # aware by-name writer" pattern TABL's DD03L / MSAG's T100 use, not
    # plain byte replacement. TABPOS prefers the XML's own <TABPOS> value
    # (abapGit always serializes it explicitly) and falls back to
    # sequential order only when missing. ---
    dd26s_fields = nametabs.get("DD26S")
    dd26s_blk = _find_block_by_action(records, "DD26S", "00REP ")
    if dd26s_blk is not None and dd26s_fields:
        donor = records[dd26s_blk[1][0]] if dd26s_blk[1] else None
        new_rows = []
        for idx, t in enumerate(tables, start=1):
            row = (Record(offset=0, rtype=" ", payload=donor.payload, fragments=1)
                   if donor is not None else _blank_row(dd26s_fields))
            row = _write_field_by_name(row, dd26s_fields, "TABNAME",
                                       t.get("TABNAME", ""))
            row = _write_dd04_field(row, dd26s_fields, "TABPOS",
                                    t.get("TABPOS") or str(idx))
            row = _write_field_by_name(row, dd26s_fields, "FORTABNAME",
                                       t.get("FORTABNAME", ""))
            row = _write_field_by_name(row, dd26s_fields, "FORFIELD",
                                       t.get("FORFIELD", ""))
            row = _write_field_by_name(row, dd26s_fields, "FORDIR",
                                       t.get("FORDIR", ""))
            new_rows.append(row)
        _replace_rows_in_block(records, dd26s_blk, new_rows)
        print(f"  VIEW base tables for {obj_name}: {len(new_rows)} "
              f"(was {len(dd26s_blk[1])} in the template)")
    elif tables:
        print("  WARNING: template has no DD26S REPC block -- "
              "base tables cannot be regenerated")

    # --- DD27S: one '00REP ' row per repo view field (<DD27P>), arbitrary
    # count. ROLLNAME has no home in the .view.xml schema (abapGit never
    # serializes it for DD27P -- confirmed against every real sample
    # surveyed, including the two genuine multi-table joins) and is
    # explicitly ZEROED rather than left at the cloned donor row's own
    # (unrelated field's) stale value -- the same choice TABL's DD03L made
    # for its own type fields (see docs/tabl-support.md's "bug caught by
    # decoding actual bytes"); unconfirmed whether DDIC activation
    # re-derives it from the base table's own data element. SHLPORIGIN/
    # VALEXI/LOGFLAG/CHECKTABLE are parsed from the XML but have NO home
    # in the real DD27S nametab this template carries (confirmed:
    # the template view's own DD27S rows carry none of these columns)
    # -- dropped, not guessed at. ---
    dd27s_fields = nametabs.get("DD27S")
    dd27s_blk = _find_block_by_action(records, "DD27S", "00REP ")
    if dd27s_blk is not None and dd27s_fields:
        donor = records[dd27s_blk[1][0]] if dd27s_blk[1] else None
        unmapped = {"SHLPORIGIN", "VALEXI", "LOGFLAG", "CHECKTABLE"} & {
            k for f in fields for k in f}
        if unmapped:
            print(f"  WARNING: VIEW fields for {obj_name} specify "
                  f"{sorted(unmapped)} -- no matching column in this "
                  f"template's own DD27S nametab, dropped (see "
                  f"docs/view-support.md)")
        new_rows = []
        for idx, f in enumerate(fields, start=1):
            row = (Record(offset=0, rtype=" ", payload=donor.payload, fragments=1)
                   if donor is not None else _blank_row(dd27s_fields))
            row = _write_dd04_field(row, dd27s_fields, "OBJPOS", str(idx))
            row = _write_field_by_name(row, dd27s_fields, "VIEWFIELD",
                                       f.get("VIEWFIELD", ""))
            row = _write_field_by_name(row, dd27s_fields, "TABNAME",
                                       f.get("TABNAME", ""))
            row = _write_field_by_name(row, dd27s_fields, "FIELDNAME",
                                       f.get("FIELDNAME", ""))
            row = _write_field_by_name(row, dd27s_fields, "KEYFLAG",
                                       f.get("KEYFLAG", ""))
            row = _write_field_by_name(row, dd27s_fields, "RDONLY",
                                       f.get("RDONLY", ""))
            row = _write_field_by_name(row, dd27s_fields, "ROLLNAME", "")
            new_rows.append(row)
        _replace_rows_in_block(records, dd27s_blk, new_rows)
        print(f"  VIEW fields for {obj_name}: {len(new_rows)} "
              f"(was {len(dd27s_blk[1])} in the template)")
    elif fields:
        print("  WARNING: template has no DD27S REPC block -- "
              "fields cannot be regenerated")

    return records


def regenerate_enqu_rows(records: list, obj_name: str, enqu_meta: dict) -> list:
    """
    Regenerate DD25L (header)/DD25T (description)/DD26S (base-table list,
    arbitrary count)/DD27S (field list, arbitrary count, incl. ENQMODE)
    from the repo's .enqu.xml. Mirrors _regenerate_view_rows's shape almost
    exactly -- same table set, same nametab-driven by-name field writer --
    with the differences documented in the "Lock object (ENQU) metadata"
    section above: no VIEWCLASS/CUSTOMAUTH/VIEWGRANT/GLOBALFLAG writes (no
    XML source for them), DD26E's own ENQMODE has no home in DD26S
    (dropped with a WARNING), and DD27S's ENQMODE IS written (a genuine
    column this table has that isn't touched by VIEW's own code).
    """
    nametabs = _parse_nametabs(records)
    language = (enqu_meta.get("ddlanguage") or "D")[:1] or "D"
    ddtext = enqu_meta.get("ddtext") or _make_description(obj_name)
    tables = enqu_meta.get("tables") or []
    fields = enqu_meta.get("fields") or []

    # --- DD25L: single row. Only AGGTYPE/ROOTTAB are ever present in a
    # real .enqu.xml (see _parse_enqu_xml) -- VIEWCLASS/CUSTOMAUTH/
    # VIEWGRANT/GLOBALFLAG/APPLCLASS keep the template's own (blank) value,
    # matching the real template lock object's own bytes. ---
    dd25l_fields = nametabs.get("DD25L")
    dd25l_blk = _find_block_by_action(records, "DD25L", "00REP ")
    if dd25l_blk is not None and dd25l_fields:
        for ridx in dd25l_blk[1]:
            row = records[ridx]
            # XML-absent columns are initial (see _apply_xml_columns) --
            # e.g. the template view's CUSTOMAUTH must not ship
            row = _apply_xml_columns(row, dd25l_fields,
                                     enqu_meta.get("dd25v") or {},
                                     keep=("VIEWNAME",))
            records[ridx] = row
    elif dd25l_fields is None:
        print("  WARNING: template has no DD25L nametab -- "
              "lock object header cannot be regenerated")

    # --- DD25T: single row, language + description text. Same H-key shape
    # as VIEW's own DD25T (DDLANGUAGE(1) FIRST, then VIEWNAME padded, no
    # trailing '*' marker dependency) -- confirmed directly against the
    # real template lock object's own DD25T H-record bytes (payload[48] == 'D',
    # immediately before the object name) before reusing _fix_msag_language_key,
    # not assumed just because DD25T is the same table VIEW uses. ---
    dd25t_fields = nametabs.get("DD25T")
    dd25t_blk = _find_block_by_action(records, "DD25T", "00REP ")
    if dd25t_blk is not None and dd25t_fields:
        for ridx in dd25t_blk[1]:
            row = _write_field_by_name(records[ridx], dd25t_fields,
                                       "DDLANGUAGE", language)
            row = _write_field_by_name(row, dd25t_fields, "DDTEXT", ddtext)
            records[ridx] = row
        records[dd25t_blk[0]] = _fix_msag_language_key(
            records[dd25t_blk[0]], language)

    # --- DD26S: one '00REP ' row per repo base table (<DD26E>), arbitrary
    # count. FORFIELD/FORDIR are never present in ENQU's own <DD26E> schema
    # (unlike VIEW's <DD26V>) so they are always written blank -- the same
    # "field absent from this object type's XML schema" posture as
    # AGGTYPE/ROOTTAB being the only DD25L columns ENQU ever supplies.
    # DD26E's own ENQMODE has NO column in DD26S at all (confirmed
    # directly) -- parsed but dropped with a WARNING, never guessed at. ---
    dd26s_fields = nametabs.get("DD26S")
    dd26s_blk = _find_block_by_action(records, "DD26S", "00REP ")
    if dd26s_blk is not None and dd26s_fields:
        donor = records[dd26s_blk[1][0]] if dd26s_blk[1] else None
        new_rows = []
        for idx, t in enumerate(tables, start=1):
            row = (Record(offset=0, rtype=" ", payload=donor.payload, fragments=1)
                   if donor is not None else _blank_row(dd26s_fields))
            row = _write_field_by_name(row, dd26s_fields, "TABNAME",
                                       t.get("TABNAME", ""))
            row = _write_dd04_field(row, dd26s_fields, "TABPOS",
                                    t.get("TABPOS") or str(idx))
            row = _write_field_by_name(row, dd26s_fields, "FORTABNAME",
                                       t.get("FORTABNAME", ""))
            row = _write_field_by_name(row, dd26s_fields, "FORFIELD", "")
            row = _write_field_by_name(row, dd26s_fields, "FORDIR", "")
            new_rows.append(row)
        _replace_rows_in_block(records, dd26s_blk, new_rows)
        print(f"  ENQU base tables for {obj_name}: {len(new_rows)} "
              f"(was {len(dd26s_blk[1])} in the template)")
    elif tables:
        print("  WARNING: template has no DD26S REPC block -- "
              "base tables cannot be regenerated")

    # --- DD27S: one '00REP ' row per repo field (<DD27P>), arbitrary
    # count, INCLUDING a literal FIELDNAME='*' "generic lock argument" row
    # when the repo's XML supplies one (see the "GENERIC LOCK ARGUMENT"
    # finding above) -- no special-casing, every XML element becomes one
    # row via the same by-name writer. ROLLNAME is zeroed, same reasoning
    # as VIEW's own DD27S (no ROLLNAME tag in any real .enqu.xml/.view.xml
    # sample surveyed). ---
    dd27s_fields = nametabs.get("DD27S")
    dd27s_blk = _find_block_by_action(records, "DD27S", "00REP ")
    if dd27s_blk is not None and dd27s_fields:
        donor = records[dd27s_blk[1][0]] if dd27s_blk[1] else None
        # DD27S is not a 1:1 image of abapGit's <DD27P> list. A base table's
        # lock mode (<DD26E><ENQMODE>) has no DD26S column; it is stored in
        # an extra DD27S row per base table: FIELDNAME='*', KEYFLAG blank,
        # VIEWFIELD/ROLLNAME of that table's last lock argument, ENQMODE =
        # the mode -- while the lock argument rows themselves carry a blank
        # ENQMODE (real lock objects). Without
        # that row the activation reports "No lock mode was defined for
        # base table" and the lock object locks nothing.
        physical = [dict(f, ENQMODE=f.get("ENQMODE", "")
                         if f.get("FIELDNAME") == "*" else "")
                    for f in fields]
        with_mode_row = {f.get("TABNAME") for f in fields
                         if f.get("FIELDNAME") == "*"}
        for t in tables:
            args = [f for f in fields if f.get("TABNAME") == t.get("TABNAME")
                    and f.get("FIELDNAME") != "*"]
            if (t.get("ENQMODE") and args
                    and t.get("TABNAME") not in with_mode_row):
                physical.append({"VIEWFIELD": args[-1].get("VIEWFIELD", ""),
                                 "TABNAME": t["TABNAME"], "FIELDNAME": "*",
                                 "ROLLNAME": args[-1].get("ROLLNAME", ""),
                                 "ENQMODE": t["ENQMODE"]})
        new_rows = []
        for idx, f in enumerate(physical, start=1):
            row = (Record(offset=0, rtype=" ", payload=donor.payload, fragments=1)
                   if donor is not None else _blank_row(dd27s_fields))
            row = _write_dd04_field(row, dd27s_fields, "OBJPOS", str(idx))
            row = _write_field_by_name(row, dd27s_fields, "VIEWFIELD",
                                       f.get("VIEWFIELD", ""))
            row = _write_field_by_name(row, dd27s_fields, "TABNAME",
                                       f.get("TABNAME", ""))
            row = _write_field_by_name(row, dd27s_fields, "FIELDNAME",
                                       f.get("FIELDNAME", ""))
            row = _write_field_by_name(row, dd27s_fields, "KEYFLAG",
                                       f.get("KEYFLAG", ""))
            row = _write_field_by_name(row, dd27s_fields, "ENQMODE",
                                       f.get("ENQMODE", ""))
            row = _write_field_by_name(row, dd27s_fields, "ROLLNAME",
                                       f.get("ROLLNAME", ""))
            new_rows.append(row)
        _replace_rows_in_block(records, dd27s_blk, new_rows)
        print(f"  ENQU fields for {obj_name}: {len(new_rows)} "
              f"(was {len(dd27s_blk[1])} in the template)")
    elif fields:
        print("  WARNING: template has no DD27S REPC block -- "
              "fields cannot be regenerated")

    return records


_DOMA_DD01L_FIELDS = ("DATATYPE", "LENG", "OUTPUTLEN", "DECIMALS",
                      "LOWERCASE", "SIGNFLAG", "LANGFLAG", "VALEXI",
                      "ENTITYTAB", "CONVEXIT", "MASK", "MASKLEN",
                      "ACTFLAG", "APPLCLASS")

# DD01T: the master language's text travels directly in <DD01V><DDTEXT>
# (abapGit does not serialize a separate per-language DD01T block -- same
# convention DTEL's DD04T/master-language DDTEXT already established).
_DOMA_DD01T_TEXT_FALLBACK = "DDTEXT"


def regenerate_doma_rows(records: list, obj_name: str, doma_meta: dict) -> list:
    """
    Regenerate DD01L (header)/DD01T (description) from the repo's <DD01V>,
    and DD07L/DD07T (fixed-value list, arbitrary count) from <DD07V_TAB> --
    a post-pass over an already-renamed record list, called once at the end
    of _process_template_records, mirroring _regenerate_tabl_rows's shape.
    """
    nametabs = _parse_nametabs(records)
    header = doma_meta.get("header") or {}
    values = doma_meta.get("values") or []
    language = (header.get("DDLANGUAGE") or "D")[:1] or "D"
    ddtext = header.get(_DOMA_DD01T_TEXT_FALLBACK) or _make_description(obj_name)

    # --- DD01L: single row. Every field in _DOMA_DD01L_FIELDS is ALWAYS
    # written, blanked when the XML doesn't carry it -- not "write if
    # present, else leave the template's value". Caught as a real bug
    # during development: a plain typed domain's .doma.xml has no VALEXI
    # (and abapGit omits the tag entirely rather than self-closing it), but
    # leaving the template's own VALEXI='X' stale shipped a DDIC-
    # inconsistent object (fixed-value flag set, zero DD07L/DD07T rows --
    # see the DD07L/DD07T drop logic below) -- the same class of one-
    # directional-blanking bug DTEL's D2 finding already caught for
    # DOMNAME/DATATYPE. Every field in this list is a genuine domain-
    # defining flag/value abapGit always states explicitly when true and
    # omits (not self-closes) when false/unset, never an admin/bookkeeping
    # field with no XML equivalent (those -- AS4USER/AS4DATE/AUTHCLASS/
    # DOMMASTER/... -- are deliberately left at the template's own value,
    # same convention TABL's DD02L uses). ---
    dd01l_fields = nametabs.get("DD01L")
    dd01l_blk = _find_block_by_action(records, "DD01L", "00REP ")
    if dd01l_blk is not None and dd01l_fields:
        for ridx in dd01l_blk[1]:
            row = records[ridx]
            for fname in _DOMA_DD01L_FIELDS:
                row = _write_dd04_field(row, dd01l_fields, fname,
                                        header.get(fname, ""))
            records[ridx] = row
    elif dd01l_fields is None:
        print("  WARNING: template has no DD01L nametab -- "
              "domain header cannot be regenerated")

    # --- DD01T: single row, language + description text. Same H-key shape
    # as DTEL's DD04T (DOMNAME padded + DDLANGUAGE + '*'). ---
    dd01t_fields = nametabs.get("DD01T")
    dd01t_blk = _find_block_by_action(records, "DD01T", "00REP ")
    if dd01t_blk is not None and dd01t_fields:
        for ridx in dd01t_blk[1]:
            row = _write_field_by_name(records[ridx], dd01t_fields,
                                       "DDLANGUAGE", language)
            row = _write_field_by_name(row, dd01t_fields, "DDTEXT", ddtext)
            records[ridx] = row
        records[dd01t_blk[0]] = fix_dtel_ddlanguage_key(
            records[dd01t_blk[0]], language)

    # --- DD07L/DD07T: one '00REP ' row per repo fixed-value/range entry
    # each (arbitrary count, like MSAG's T100), parallel to each other by
    # VALPOS -- verified directly against the real export (3 DD07L rows, 3
    # matching DD07T rows). When the repo's .doma.xml has NO <DD07V_TAB> at
    # all (VALEXI not set -- a plain typed domain), both blocks are DROPPED
    # ENTIRELY rather than shipped as empty '00REP ' blocks -- the same
    # "drop unmatched content" choice TABL's DD09L already established (see
    # _regenerate_tabl_rows / _remove_block's own docstring): this
    # generator has no real-import ground truth for what a genuine SAP
    # export of a non-fixed-value domain does with these two blocks, and an
    # empty-but-present REPC block is less obviously faithful than not
    # shipping it at all. DD07T's H-key packs the same DOMNAME+DDLANGUAGE+
    # '*' shape as DD01T. ---
    dd07l_blk = _find_block_by_action(records, "DD07L", "00REP ")
    dd07t_blk = _find_block_by_action(records, "DD07T", "00REP ")
    if not values:
        if dd07l_blk is not None:
            _remove_block(records, dd07l_blk)
        if dd07t_blk is not None:
            # Re-locate: DD07T sits after DD07L in the template, so
            # removing DD07L above shifted every later record's index --
            # the dd07t_blk captured before that removal is now stale.
            dd07t_blk = _find_block_by_action(records, "DD07T", "00REP ")
            if dd07t_blk is not None:
                _remove_block(records, dd07t_blk)
        print(f"  DOMA fixed values for {obj_name}: dropped DD07L/DD07T -- "
              f"repo's .doma.xml has no <DD07V_TAB> (not a fixed-value "
              f"domain, or abapGit didn't serialize one)")
    else:
        dd07l_fields = nametabs.get("DD07L")
        if dd07l_blk is not None and dd07l_fields:
            donor = records[dd07l_blk[1][0]] if dd07l_blk[1] else None
            new_rows = []
            for entry in values:
                row = (Record(offset=0, rtype=" ", payload=donor.payload, fragments=1)
                       if donor is not None else _blank_row(dd07l_fields))
                row = _write_field_by_name(row, dd07l_fields, "DOMNAME", obj_name)
                row = _write_dd04_field(row, dd07l_fields, "VALPOS",
                                        entry.get("VALPOS", ""))
                row = _write_field_by_name(row, dd07l_fields, "DOMVALUE_L",
                                           entry.get("DOMVALUE_L", ""))
                row = _write_field_by_name(row, dd07l_fields, "DOMVALUE_H",
                                           entry.get("DOMVALUE_H", ""))
                new_rows.append(row)
            _replace_rows_in_block(records, dd07l_blk, new_rows)
            print(f"  DOMA fixed values for {obj_name}: {len(new_rows)} "
                  f"(was {len(dd07l_blk[1])} in the template)")
        else:
            print("  WARNING: template has no DD07L REPC block -- "
                  "fixed values cannot be regenerated")

        # DD07L sits before DD07T. Replacing its rows can change the record
        # count, so the block location captured above no longer points at DD07T.
        dd07t_blk = _find_block_by_action(records, "DD07T", "00REP ")
        dd07t_fields = nametabs.get("DD07T")
        if dd07t_blk is not None and dd07t_fields:
            donor = records[dd07t_blk[1][0]] if dd07t_blk[1] else None
            new_rows = []
            for entry in values:
                row = (Record(offset=0, rtype=" ", payload=donor.payload, fragments=1)
                       if donor is not None else _blank_row(dd07t_fields))
                row = _write_field_by_name(row, dd07t_fields, "DOMNAME", obj_name)
                row = _write_field_by_name(row, dd07t_fields, "DDLANGUAGE",
                                           entry.get("DDLANGUAGE") or language)
                row = _write_dd04_field(row, dd07t_fields, "VALPOS",
                                        entry.get("VALPOS", ""))
                row = _write_field_by_name(row, dd07t_fields, "DDTEXT",
                                           entry.get("DDTEXT", ""))
                row = _write_field_by_name(row, dd07t_fields, "DOMVALUE_L",
                                           entry.get("DOMVALUE_L", ""))
                new_rows.append(row)
            _replace_rows_in_block(records, dd07t_blk, new_rows)
            records[dd07t_blk[0]] = fix_dtel_ddlanguage_key(
                records[dd07t_blk[0]], language)
        else:
            print("  WARNING: template has no DD07T REPC block -- "
                  "fixed-value texts cannot be regenerated")

    return records


_SHLP_DD30L_FIELDS = ("ISSIMPLE", "ELEMEXI", "NOFIELDS", "ATTACHEXI",
                     "SELMETHOD", "SELMTYPE", "TEXTTAB", "SELMEXIT",
                     "HOTKEY", "DIALOGTYPE", "ACTFLAG", "AUTOSUGGEST",
                     "FUZZY_SEARCH")
# AS4LOCAL/AS4USER/AS4DATE/AS4TIME are admin/bookkeeping fields abapGit's
# own serializer explicitly CLEARs before writing DD30V (see the source
# excerpt above) -- left at the template's own value, same convention
# TABL/DOMA/MSAG already use for their own admin fields.

_SHLP_DD31S_FIELDS = ("SUBSHLP", "SHPOSITION", "VIASHLP", "HIDEFLAG")
_SHLP_DD32S_FIELDS = ("FIELDNAME", "ROLLNAME", "SHLPINPUT", "SHLPOUTPUT",
                     "SHLPSELPOS", "SHLPSELDIS", "SHLPLISPOS", "SHLPUPPER",
                     "DEFAULTVAL", "DEFAULTTYP", "SQLTAB", "INDEXNAME",
                     "ROLLCHANGE")
# DATATYPE/LENG/DECIMALS handled separately below (blanked, like DTEL's
# DOMNAME/DATATYPE pair and TABL's DD03L -- abapGit's serializer explicitly
# clears these "inherited from domain" fields before writing DD32P, see the
# source excerpt above, but this project's own real DD32S ground truth
# (a FIELDNAME/ROLLNAME pair) ships them FULLY populated
# nonetheless -- same DTEL D3 / TABL caveat, unconfirmed against a real
# import). SCRLEN3 (present in real DD32P XML) has no home in this
# template's own DD32S nametab (19 fields, none named SCRLEN3) -- dropped,
# the same "no matching column in the real nametab" gap VIEW's ROLLNAME hit.
_SHLP_DD32S_NUMC_FIELDS = ("FLPOSITION", "SHLPSELPOS", "SHLPLISPOS")
_SHLP_DD33S_FIELDS = ("FIELDNAME", "SUBSHLP", "SUBFIELD", "DEFAULTVAL",
                     "DEFAULTTYP", "VALUEDIREC")


def _write_shlp_fuzzy_similarity(row: Record, fields: list,
                                 value: str) -> Record:
    """
    Write DD30L-FUZZY_SIMILARITY, a PACKED DECIMAL(3,1) field (2 bytes, 4
    nibbles: 3 digits + 1 sign nibble) -- verified directly against the real
    reference object's own bytes (raw `00 8c` decodes as digits "008" +
    sign nibble 'C' (positive) = 0.8 with the implied 1 decimal place,
    matching every real .shlp.xml sample surveyed). `value` is a decimal
    string like "0.8" (from the repo's <FUZZY_SIMILARITY> tag) or "" (blank
    -> 0.0, when the repo's XML doesn't carry it -- e.g. abapGit never
    serializes this at all for a collective search help, see
    docs/shlp-support.md).
    """
    for name, off, flen, ftype in fields or []:
        if name != "FUZZY_SIMILARITY" or ftype != "P":
            continue
        try:
            num = float(value) if value else 0.0
        except ValueError:
            num = 0.0
        total_digits = flen * 2 - 1     # 1 nibble reserved for the sign
        scaled = int(round(abs(num) * 10))   # 1 decimal place
        digits = str(scaled).zfill(total_digits)[-total_digits:]
        nibbles = [int(c) for c in digits] + [0xD if num < 0 else 0xC]
        packed = bytearray(flen)
        for i in range(flen):
            packed[i] = (nibbles[2 * i] << 4) | nibbles[2 * i + 1]
        payload = bytearray(row.payload)
        payload[off:off + flen] = bytes(packed)
        return Record(offset=row.offset, rtype=row.rtype,
                      payload=bytes(payload), fragments=row.fragments)
    return row


def regenerate_shlp_rows(records: list, obj_name: str, shlp_meta: dict) -> list:
    """
    Regenerate DD30L (header)/DD30T (description) from the repo's <DD30V>,
    DD32S (parameter list, arbitrary count) from <DD32P_TABLE>, and DD31S/
    DD33S (selection-method list / parameter-to-subhelp mapping) either from
    <DD31V_TABLE>/<DD33V_TABLE> (collective case) or SYNTHESIZED (elementary
    case -- see the module docstring above for why this is necessary, not
    just convenient). A post-pass over an already-renamed record list,
    mirroring _regenerate_doma_rows/_regenerate_tabl_rows's shape.
    """
    nametabs = _parse_nametabs(records)
    header = shlp_meta.get("header") or {}
    fields = shlp_meta.get("fields") or []
    submethods = shlp_meta.get("submethods") or []
    mappings = shlp_meta.get("mappings") or []
    language = (header.get("DDLANGUAGE") or "D")[:1] or "D"
    ddtext = header.get("DDTEXT") or _make_description(obj_name)

    # --- DD30L: single row. Content-defining fields ALWAYS written, blanked
    # when the XML doesn't carry them -- same "don't leave a stale flag from
    # the donor object" rule DOMA's D-finding established for VALEXI. ---
    dd30l_fields = nametabs.get("DD30L")
    dd30l_blk = _find_block_by_action(records, "DD30L", "00REP ")
    if dd30l_blk is not None and dd30l_fields:
        for ridx in dd30l_blk[1]:
            row = records[ridx]
            for fname in _SHLP_DD30L_FIELDS:
                row = _write_dd04_field(row, dd30l_fields, fname,
                                        header.get(fname, ""))
            row = _write_shlp_fuzzy_similarity(
                row, dd30l_fields, header.get("FUZZY_SIMILARITY", ""))
            records[ridx] = row
    elif dd30l_fields is None:
        print("  WARNING: template has no DD30L nametab -- "
              "search help header cannot be regenerated")

    # --- DD30T: single row, language + description text. Same H-key shape
    # as DOMA's DD01T/DTEL's DD04T (SHLPNAME padded + DDLANGUAGE + '*'). ---
    dd30t_fields = nametabs.get("DD30T")
    dd30t_blk = _find_block_by_action(records, "DD30T", "00REP ")
    if dd30t_blk is not None and dd30t_fields:
        for ridx in dd30t_blk[1]:
            row = _write_field_by_name(records[ridx], dd30t_fields,
                                       "DDLANGUAGE", language)
            row = _write_field_by_name(row, dd30t_fields, "DDTEXT", ddtext)
            records[ridx] = row
        records[dd30t_blk[0]] = _fix_dtel_ddlanguage_key(
            records[dd30t_blk[0]], language)

    # --- DD32S: one '00REP ' row per repo parameter (arbitrary count). ---
    dd32s_fields = nametabs.get("DD32S")
    dd32s_blk = _find_block_by_action(records, "DD32S", "00REP ")
    if dd32s_blk is not None and dd32s_fields:
        donor = records[dd32s_blk[1][0]] if dd32s_blk[1] else None
        new_rows = []
        any_type_blanked = False
        for pos, f in enumerate(fields, start=1):
            row = (Record(offset=0, rtype=" ", payload=donor.payload, fragments=1)
                   if donor is not None else _blank_row(dd32s_fields))
            row = _write_dd04_field(row, dd32s_fields, "FLPOSITION", str(pos))
            for fname in _SHLP_DD32S_FIELDS:
                row = _write_field_by_name(row, dd32s_fields, fname,
                                           f.get(fname, ""))
            for fname in _SHLP_DD32S_NUMC_FIELDS:
                row = _write_dd04_field(row, dd32s_fields, fname,
                                        f.get(fname, ""))
            # DATATYPE/LENG/DECIMALS: abapGit clears these before writing
            # DD32P (see module docstring) -- always written, zeroed when
            # absent, same unconfirmed-against-a-real-import choice DTEL/
            # TABL already made for the identical situation.
            row = _write_field_by_name(row, dd32s_fields, "DATATYPE",
                                       f.get("DATATYPE", ""))
            row = _write_dd04_field(row, dd32s_fields, "LENG", f.get("LENG", ""))
            row = _write_dd04_field(row, dd32s_fields, "DECIMALS",
                                    f.get("DECIMALS", ""))
            if f.get("ROLLNAME") and not (f.get("LENG") or f.get("DECIMALS")):
                any_type_blanked = True
            new_rows.append(row)
        _replace_rows_in_block(records, dd32s_blk, new_rows)
        print(f"  SHLP parameters for {obj_name}: {len(new_rows)} "
              f"(was {len(dd32s_blk[1])} in the template)")
    elif fields:
        print("  WARNING: template has no DD32S REPC block -- "
              "parameters cannot be regenerated")

    # --- DD31S / DD33S: collective case uses the repo's own XML row lists
    # directly (arbitrary count); elementary case (no <DD31V_TABLE>/
    # <DD33V_TABLE> in the XML at all) SYNTHESIZES the self-referencing rows
    # a real elementary search help's own transport section carries -- see
    # the module docstring for why this is necessary, not a guess. ---
    is_collective = bool(submethods)
    if not is_collective:
        submethods = [{"SUBSHLP": obj_name, "SHPOSITION": "0001",
                       "VIASHLP": "", "HIDEFLAG": ""}]
        mappings = [{"FIELDNAME": f.get("FIELDNAME", ""), "SUBSHLP": obj_name,
                     "SUBFIELD": f.get("FIELDNAME", ""), "DEFAULTVAL": "",
                     "DEFAULTTYP": "", "VALUEDIREC": "C"} for f in fields]
        print(f"  SHLP {obj_name}: elementary search help -- repo's "
              f".shlp.xml has no <DD31V_TABLE>/<DD33V_TABLE> (abapGit never "
              f"serializes these for an elementary help) -- synthesized 1 "
              f"self-referencing DD31S row + {len(mappings)} DD33S row(s), "
              f"matching the real reference object's own ground truth "
              f"(see docs/shlp-support.md)")

    dd31s_fields = nametabs.get("DD31S")
    dd31s_blk = _find_block_by_action(records, "DD31S", "00REP ")
    if dd31s_blk is not None and dd31s_fields:
        donor = records[dd31s_blk[1][0]] if dd31s_blk[1] else None
        new_rows = []
        for entry in submethods:
            row = (Record(offset=0, rtype=" ", payload=donor.payload, fragments=1)
                   if donor is not None else _blank_row(dd31s_fields))
            for fname in ("SUBSHLP", "VIASHLP", "HIDEFLAG"):
                row = _write_field_by_name(row, dd31s_fields, fname,
                                           entry.get(fname, ""))
            row = _write_dd04_field(row, dd31s_fields, "SHPOSITION",
                                    entry.get("SHPOSITION", ""))
            new_rows.append(row)
        _replace_rows_in_block(records, dd31s_blk, new_rows)
        print(f"  SHLP sub-search-helps for {obj_name}: {len(new_rows)} "
              f"({'collective' if is_collective else 'elementary'})")
    elif submethods:
        print("  WARNING: template has no DD31S REPC block -- "
              "sub-search-helps cannot be regenerated")

    dd33s_fields = nametabs.get("DD33S")
    dd33s_blk = _find_block_by_action(records, "DD33S", "00REP ")
    if dd33s_blk is not None and dd33s_fields:
        donor = records[dd33s_blk[1][0]] if dd33s_blk[1] else None
        new_rows = []
        for entry in mappings:
            row = (Record(offset=0, rtype=" ", payload=donor.payload, fragments=1)
                   if donor is not None else _blank_row(dd33s_fields))
            for fname in _SHLP_DD33S_FIELDS:
                row = _write_field_by_name(row, dd33s_fields, fname,
                                           entry.get(fname, ""))
            new_rows.append(row)
        _replace_rows_in_block(records, dd33s_blk, new_rows)
        print(f"  SHLP parameter mappings for {obj_name}: {len(new_rows)}")
    elif mappings:
        print("  WARNING: template has no DD33S REPC block -- "
              "parameter mappings cannot be regenerated")

    return records


_TTYP_DD40L_FIELDS = ("ROWTYPE", "ROWKIND", "DATATYPE", "LENG", "DECIMALS",
                      "ACCESSMODE", "GENERIC", "TTYPKIND", "RANGE_CTYP",
                      "REFTYPE")
_TTYP_DD40L_NUMERIC = ("LENG", "DECIMALS")

# DD40T: the master language's DDTEXT travels directly in <DD40V> (abapGit
# skips a separate texts block for the master language, same convention as
# DTEL's DD04T). Additional (non-master) languages are NOT implemented --
# see docs/ttyp-support.md.
_TTYP_DD40T_FIELDS = ("DDLANGUAGE", "DDTEXT")

def apply_ttyp_row(row: Record, table: str, fields: list,
                    ttyp_fields: dict, obj_name: str = "") -> Record:
    """
    Overwrite a DD40L or DD40T row's row-type/kind/access/key fields and
    description from the repo's .ttyp.xml. Called AFTER the generic per-row
    rename (TYPENAME, request number) has already run -- this fills in
    content that is genuinely new per object, mirroring _apply_dtel_row.

    KEYDEF/KEYKIND/KEYFDCOUNT: if the repo declares explicit key fields
    (KEYFDCOUNT > 0, i.e. KEYDEF is not the default key), this generator
    cannot ship them -- the template carries no DD42L block (none of the ten
    42-record TTYP candidates the template was built from do; a table type
    with an explicit key needs DD42L rows this generator does not
    synthesize). Rather than emit a DD40L row claiming N key fields with
    zero DD42L rows behind it (which would fail DDIC activation), the key
    definition is forced back to the default key and a WARNING is printed.
    """
    if table == "DD40L":
        keydef = ttyp_fields.get("KEYDEF", "D") or "D"
        keyfdcount_raw = ttyp_fields.get("KEYFDCOUNT", "") or "0"
        try:
            keyfdcount = int(keyfdcount_raw)
        except ValueError:
            keyfdcount = 0
        if keydef != "D" or keyfdcount > 0:
            print(f"  WARNING: {obj_name or '(object)'}: .ttyp.xml declares "
                  f"an explicit key ({keyfdcount} field(s), KEYDEF={keydef!r}) "
                  f"but this generator does not ship DD42L key-field rows -- "
                  f"falling back to the default key (KEYDEF='D')")
            keydef, keykind, keyfdcount_out = "D", "N", "0"
        else:
            keykind = ttyp_fields.get("KEYKIND", "N") or "N"
            keyfdcount_out = "0"
        row = _write_dd04_field(row, fields, "KEYDEF", keydef)
        row = _write_dd04_field(row, fields, "KEYKIND", keykind)
        row = _write_dd04_field(row, fields, "KEYFDCOUNT", keyfdcount_out)
        # TYPELEN is a pure DDIC-derived field (see the module comment
        # above) -- always blanked, never sourced from the XML.
        row = _write_dd04_field(row, fields, "TYPELEN", "0")
        for fname in _TTYP_DD40L_FIELDS:
            value = ttyp_fields.get(fname, "")
            if fname in _TTYP_DD40L_NUMERIC:
                row = _write_dd04_field(row, fields, fname, value or "0")
            else:
                row = _write_dd04_field(row, fields, fname, value)
    elif table == "DD40T":
        for fname in _TTYP_DD40T_FIELDS:
            value = ttyp_fields.get(fname, "")
            if fname == "DDTEXT":
                value = value or _make_description(obj_name)
            row = _write_dd04_field(row, fields, fname, value)
    return row


def fix_ttyp_ddlanguage_key(h_rec: Record, new_lang: str) -> Record:
    """
    DD40T's H-record key packs TYPENAME + DDLANGUAGE(1) + '*' -- the same
    shape DTEL's DD04T key has (verified against the template:
    '<name, 30 chars>D*'). The generic rename only touches
    the TYPENAME portion, so the language character would otherwise still
    read the template's original language. Identical fix to
    _fix_dtel_ddlanguage_key, duplicated (not shared) because the two
    tables' keys are independently-verified instances of the same shape,
    not a single mechanism -- a future refactor could unify them once a
    third instance confirms the pattern generalizes.
    """
    if not new_lang:
        return h_rec
    key_area = h_rec.payload[48:]
    text = key_area.decode("latin-1")
    star = text.rfind("*")
    if star < 1:
        return h_rec
    lang_char = text[star - 1]
    if not ("A" <= lang_char <= "Z"):
        return h_rec
    text = text[:star - 1] + new_lang[0] + text[star:]
    payload = bytearray(h_rec.payload)
    payload[48:] = text.encode("latin-1")
    return Record(offset=h_rec.offset, rtype=h_rec.rtype,
                  payload=bytes(payload), fragments=h_rec.fragments)
