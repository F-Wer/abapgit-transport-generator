"""TOBJ transport regeneration helpers."""

from collections.abc import Callable

from sap_transport_records import Record


_helpers: dict[str, Callable] = {}


def configure_tobj_helpers(**helpers: Callable) -> None:
    """Configure shared facade helpers used by the TOBJ implementation."""
    _helpers.update(helpers)


def _helper(name: str) -> Callable:
    try:
        return _helpers[name]
    except KeyError as exc:
        raise RuntimeError(f"TOBJ helper {name!r} has not been configured") from exc


def _parse_nametabs(*args, **kwargs):
    return _helper("parse_nametabs")(*args, **kwargs)


def _find_block(*args, **kwargs):
    return _helper("find_block")(*args, **kwargs)


def _find_block_by_action(*args, **kwargs):
    return _helper("find_block_by_action")(*args, **kwargs)


def _write_field_by_name(*args, **kwargs):
    return _helper("write_field_by_name")(*args, **kwargs)


def _write_dd04_field(*args, **kwargs):
    return _helper("write_dd04_field")(*args, **kwargs)


def _blank_row(*args, **kwargs):
    return _helper("blank_row")(*args, **kwargs)


def _replace_rows_in_block(*args, **kwargs):
    return _helper("replace_rows_in_block")(*args, **kwargs)


def _remove_block(*args, **kwargs):
    return _helper("remove_block")(*args, **kwargs)


_TOBJ_OBJH_FIELDS = ("OBJECTNAME", "OBJECTTYPE", "CLIDEP", "OBJCATEG",
                    "OBJTRANSP", "IMPORTABLE")
_TOBJ_OBJT_FIELDS = ("LANGUAGE", "OBJECTNAME", "OBJECTTYPE", "DDTEXT")
_TOBJ_OBJS_FIELDS = ("OBJECTNAME", "OBJECTTYPE", "TABNAME", "DDIC",
                    "PRIM_TABLE")
_TOBJ_TDDAT_FIELDS = ("TABNAME", "CCLASS")
_TOBJ_TVDIR_FIELDS = ("TABNAME", "AREA", "TYPE", "LISTE", "BASTAB", "FLAG")
# TVDIR.LISTE is the only NUMC (right-justified, zero-padded) field this
# generator writes for TOBJ -- everything else is plain text.
_TOBJ_NUMC_FIELDS = ("LISTE",)

# Matches either a self-closing tag or a normal open/close pair -- the same
# lenient shape every prior metadata-only type's tag regex uses (abapGit
# emits both forms for empty elements depending on context).


def _tobj_write_row(row: Record, fields: list, values: dict,
                    allowed: tuple) -> Record:
    """A row with exactly the repo's values: columns the XML does not
    carry are initial, not the template object's (its package in TVDIR-
    DEVCLASS, its last-changed user in OBJH-LUSER, ...). `allowed` is kept
    for the callers; every XML tag that names a column is written."""
    return _fresh_row(row, fields, "", values)


def _set_tobj_key(h_rec: Record, key_text: str, total_width: int = 240) -> Record:
    """
    Rebuild an OBJH/OBJS/OBJT/OBJLAN/OBJM/OBJSL/TDDAT/TVDIR/TVIMF-family
    H-record's key area (a fixed 240-byte, single-byte-per-char latin-1
    field, verified directly against the template's own real bytes -- NOT
    UTF-16LE the way data rows are) from a literal key string, space-padded
    to the full width. Unlike every prior type's language-key fix (which
    overwrites one or a few characters in place, preserving surrounding
    content), TOBJ's whole key content is per-object -- see the module
    docstring for why -- so this rebuilds the entire key area instead.
    """
    payload = bytearray(h_rec.payload)
    new_key = key_text.encode("latin-1").ljust(total_width)[:total_width]
    payload[48:48 + total_width] = new_key
    return Record(offset=h_rec.offset, rtype=h_rec.rtype,
                  payload=bytes(payload), fragments=h_rec.fragments)


def _tobj_objname_key(objectname: str, objecttype: str,
                      lang: str = "") -> str:
    """OBJH/OBJS/OBJLAN/OBJM/OBJSL's key shape: OBJECTNAME(30, space-padded)
    + OBJECTTYPE(1) + '*' -- verified against the template's real bytes
    ('<name, 30 chars>S*'). OBJT's key shape is the same with
    one extra LANGUAGE(1) byte first ('D<name, 30 chars>S*') --
    pass `lang` for that case."""
    return ((lang[:1] if lang else "")
            + (objectname or "").ljust(30)[:30]
            + (objecttype or " ")[:1] + "*")


def _tobj_tabname_key(tabname: str) -> str:
    """TDDAT/TVDIR/TVIMF's key shape: TABNAME(30, space-padded) + '*' -- no
    OBJECTTYPE byte at all (verified against the template's real bytes,
    e.g. '<name, 30 chars>*')."""
    return (tabname or "").ljust(30)[:30] + "*"


def _regenerate_tobj_rows(records: list, obj_name: str,
                          tobj_meta: dict) -> list:
    """
    Regenerate OBJH (header)/OBJT (description)/OBJS (one-or-more table
    assignments)/TDDAT (customizing class, optional)/TVDIR (view-maintenance
    registration) from the repo's .tobj.xml, plus the H-record keys every
    one of these tables (and the content-free OBJLAN/OBJM/OBJSL/TVIMF
    housekeeping blocks) carries -- see the module docstring for why the
    keys need explicit regeneration here, unlike every prior type.

    A post-pass over an already-renamed record list, called once at the end
    of _process_template_records -- mirrors _regenerate_tabl_rows's shape.
    """
    nametabs = _parse_nametabs(records)
    objh = tobj_meta.get("objh") or {}
    objt = tobj_meta.get("objt") or {}
    objs_rows = tobj_meta.get("objs_rows") or []
    tddat = tobj_meta.get("tddat")
    tvdir = tobj_meta.get("tvdir") or {}

    objh_objname = objh.get("OBJECTNAME", "")
    objh_objtype = objh.get("OBJECTTYPE", "")
    if not objh:
        print(f"  WARNING: {obj_name}: no <OBJH> in the .tobj.xml -- "
              f"OBJH/OBJS/OBJLAN/OBJM/OBJSL keys cannot be regenerated, "
              f"template's own stale object identity will ship")

    # --- OBJH: single row, '00REPC' ---
    objh_fields = nametabs.get("OBJH")
    objh_blk = _find_block_by_action(records, "OBJH", "00REPC")
    if objh_blk is not None and objh_fields:
        for ridx in objh_blk[1]:
            records[ridx] = _tobj_write_row(records[ridx], objh_fields,
                                            objh, _TOBJ_OBJH_FIELDS)
        if objh_objname:
            records[objh_blk[0]] = _set_tobj_key(
                records[objh_blk[0]],
                _tobj_objname_key(objh_objname, objh_objtype))
    elif objh:
        print(f"  WARNING: {obj_name}: template has no OBJH REPC block -- "
              f"header cannot be regenerated")

    # --- OBJS: one '00REPC' row per repo <OBJS><OBJS> entry (arbitrary
    # count, like TABL's DD03L / MSAG's T100) ---
    objs_fields = nametabs.get("OBJS")
    objs_blk = _find_block_by_action(records, "OBJS", "00REPC")
    if objs_blk is not None and objs_fields:
        donor = records[objs_blk[1][0]] if objs_blk[1] else None
        new_rows = []
        for row_meta in objs_rows:
            row = (Record(offset=0, rtype=" ", payload=donor.payload,
                          fragments=1) if donor is not None
                   else _blank_row(objs_fields))
            row = _tobj_write_row(row, objs_fields, row_meta,
                                  _TOBJ_OBJS_FIELDS)
            new_rows.append(row)
        if new_rows:
            _replace_rows_in_block(records, objs_blk, new_rows)
            first_name = objs_rows[0].get("OBJECTNAME", objh_objname)
            first_type = objs_rows[0].get("OBJECTTYPE", objh_objtype)
            if first_name:
                records[objs_blk[0]] = _set_tobj_key(
                    records[objs_blk[0]],
                    _tobj_objname_key(first_name, first_type))
            print(f"  TOBJ OBJS assignments for {obj_name}: {len(new_rows)} "
                  f"(was {len(objs_blk[1])} in the template)")
    elif objs_rows:
        print(f"  WARNING: {obj_name}: template has no OBJS REPC block -- "
              f"table assignments cannot be regenerated")

    # --- TDDAT: single row, '00REPC' -- OPTIONAL. Dropped entirely (H
    # through E, not just its rows) when the repo's <TOBJ> has no <TDDAT>
    # child at all (a real view-cluster-based maintenance object genuinely
    # carries none, confirmed: microsoft/ABAP-SDK-for-Azure's
    # zadf_v_configv.tobj.xml) -- shipping the template's own stale
    # customizing-class assignment for an object that doesn't have one
    # would be actively wrong, the same "drop unmatched content" rule
    # TABL's DD09L already applies. ---
    tddat_fields = nametabs.get("TDDAT")
    tddat_blk = _find_block_by_action(records, "TDDAT", "00REPC")
    if tddat_blk is not None:
        if tddat is not None:
            for ridx in tddat_blk[1]:
                records[ridx] = _tobj_write_row(records[ridx], tddat_fields,
                                                tddat, _TOBJ_TDDAT_FIELDS)
            if tddat.get("TABNAME"):
                records[tddat_blk[0]] = _set_tobj_key(
                    records[tddat_blk[0]],
                    _tobj_tabname_key(tddat["TABNAME"]))
        else:
            _remove_block(records, tddat_blk)
            print(f"  TOBJ TDDAT for {obj_name}: dropped -- repo's .tobj.xml "
                  f"has no <TDDAT> (view-cluster-based maintenance object, "
                  f"or abapGit didn't serialize one)")

    # --- TVDIR: single row, '00REPC' ---
    tvdir_fields = nametabs.get("TVDIR")
    tvdir_blk = _find_block_by_action(records, "TVDIR", "00REPC")
    if tvdir_blk is not None and tvdir_fields:
        for ridx in tvdir_blk[1]:
            records[ridx] = _tobj_write_row(records[ridx], tvdir_fields,
                                            tvdir, _TOBJ_TVDIR_FIELDS)
        if tvdir.get("TABNAME"):
            records[tvdir_blk[0]] = _set_tobj_key(
                records[tvdir_blk[0]], _tobj_tabname_key(tvdir["TABNAME"]))
    elif tvdir:
        print(f"  WARNING: {obj_name}: template has no TVDIR REPC block -- "
              f"view-maintenance registration cannot be regenerated")

    # --- OBJT: the template ships a real 49-language delete sweep (one
    # '00DELL', 0-row H-block per installed system language -- see
    # build_tobj_template.py's docstring for why no real REPC example exists
    # anywhere in the reference transport this was spliced from) but no
    # REPC block. Find the ONE block whose key's language byte matches the
    # repo's own OBJT.LANGUAGE and flip JUST THAT ONE from delete-sweep to
    # a single-row insert -- the same "synthesize a new-shape row set on
    # top of a template's delete-only block" move TRAN's TSTCP uses (see
    # _regenerate_tran_tstcp), so the other (up to) 48 languages' sweeps
    # stay untouched (and, since each carries a distinct language byte,
    # never collide with the promoted one). Every OBJT block's own
    # OBJECTNAME portion is corrected regardless of language (a stale key
    # would otherwise still point at the template's own donor object,
    # even for the 48 that stay delete sweeps).
    objt_fields = nametabs.get("OBJT")
    master_lang = (objt.get("LANGUAGE") or "D")[:1] or "D"
    objt_blocks = []
    i = 0
    while i < len(records):
        rec = records[i]
        if (rec.rtype == "H" and rec.payload[8:38].rstrip() == b"OBJT"):
            j = i + 1
            rows = []
            while j < len(records) and records[j].rtype != "E":
                if records[j].rtype == " ":
                    rows.append(j)
                j += 1
            objt_blocks.append((i, rows, j))
            i = j
        i += 1

    if objt_blocks and objt_fields and objh_objname:
        promoted = None
        for blk in objt_blocks:
            key_area = records[blk[0]].payload[48:49]
            if key_area.decode("latin-1", errors="replace") == master_lang:
                promoted = blk
                break
        if promoted is None:
            promoted = objt_blocks[0]
            print(f"  WARNING: {obj_name}: no existing OBJT delete-sweep "
                  f"block found for language {master_lang!r} -- promoting "
                  f"the first of {len(objt_blocks)} instead (cosmetic risk "
                  f"only: 0-row delete sweeps are otherwise unaffected)")

        for blk in objt_blocks:
            key_lang = master_lang if blk is promoted else \
                records[blk[0]].payload[48:49].decode("latin-1",
                                                       errors="replace")
            records[blk[0]] = _set_tobj_key(
                records[blk[0]],
                _tobj_objname_key(objh_objname, objh_objtype, key_lang))

        row = _blank_row(objt_fields)
        row = _tobj_write_row(row, objt_fields,
                              {**objt, "LANGUAGE": master_lang},
                              _TOBJ_OBJT_FIELDS)
        h_idx, row_idxs, e_idx = promoted
        payload = bytearray(records[h_idx].payload)
        payload[38:44] = b"00REPC"
        records[h_idx] = Record(offset=records[h_idx].offset,
                                rtype=records[h_idx].rtype,
                                payload=bytes(payload),
                                fragments=records[h_idx].fragments)
        _replace_rows_in_block(records, (h_idx, row_idxs, e_idx), [row])
        print(f"  TOBJ OBJT description for {obj_name}: language "
              f"{master_lang!r}, DDTEXT={objt.get('DDTEXT', '')!r}")
    elif objt:
        print(f"  WARNING: {obj_name}: template has no OBJT delete-sweep "
              f"blocks (or no <OBJH> to derive the key from) -- description "
              f"cannot be regenerated")

    # --- OBJLAN/OBJM/OBJSL/TVIMF: content-free housekeeping (0-row delete
    # sweeps) -- no abapGit content to write (see module docstring), but the
    # H-record key is still corrected to the real target identity. ---
    if objh_objname:
        for table in ("OBJLAN", "OBJM", "OBJSL"):
            blk = _find_block(records, table)
            if blk is not None:
                records[blk[0]] = _set_tobj_key(
                    records[blk[0]],
                    _tobj_objname_key(objh_objname, objh_objtype))
    tvimf_tabname = tvdir.get("TABNAME") or (tddat or {}).get("TABNAME", "")
    if tvimf_tabname:
        tvimf_blk = _find_block(records, "TVIMF")
        if tvimf_blk is not None:
            records[tvimf_blk[0]] = _set_tobj_key(
                records[tvimf_blk[0]], _tobj_tabname_key(tvimf_tabname))

    return records



# Public module names; the compatibility facade continues to expose the
# original underscored names.
tobj_write_row = _tobj_write_row
set_tobj_key = _set_tobj_key
tobj_objname_key = _tobj_objname_key
tobj_tabname_key = _tobj_tabname_key
regenerate_tobj_rows = _regenerate_tobj_rows
