"""Special-object regeneration helpers."""

import base64
from collections.abc import Callable

from sap_transport_records import Record

_helpers: dict[str, Callable] = {}


def configure_special_helpers(**helpers: Callable) -> None:
    """Configure shared facade helpers needed by special-object implementations."""
    _helpers.update(helpers)


def _helper(name: str) -> Callable:
    try:
        return _helpers[name]
    except KeyError as exc:
        raise RuntimeError(f"Special helper {name!r} has not been configured") from exc


def _parse_nametabs(*args, **kwargs):
    return _helper("parse_nametabs")(*args, **kwargs)


def _find_block(*args, **kwargs):
    return _helper("find_block")(*args, **kwargs)


def _write_field_by_name(*args, **kwargs):
    return _helper("write_field_by_name")(*args, **kwargs)


def _write_raw_field_by_name(*args, **kwargs):
    return _helper("write_raw_field_by_name")(*args, **kwargs)


def _write_dd04_field(*args, **kwargs):
    return _helper("write_dd04_field")(*args, **kwargs)


def _blank_row(*args, **kwargs):
    return _helper("blank_row")(*args, **kwargs)


def _replace_rows_in_block(*args, **kwargs):
    return _helper("replace_rows_in_block")(*args, **kwargs)


def _make_description(*args, **kwargs):
    return _helper("make_description")(*args, **kwargs)


def _fix_msag_language_key(*args, **kwargs):
    return _helper("fix_msag_language_key")(*args, **kwargs)


_TRAN_TSTC_TEXT_FIELDS = ("PGMNA", "DYPNO")
_TRAN_TSTC_BLANK_FIELDS = ("MENUE", "ARBGB")

# TSTCT: SPRSL (language) + TTEXT (description). TTEXT falls back to a
# name-derived description when the repo's XML omits it, the same pattern
# DTEL's D4 fix and TTYP's DDTEXT fallback both established.
_TRAN_TSTCT_FIELDS = ("SPRSL", "TTEXT")

def apply_tran_row(row: Record, table: str, fields: list,
                    tran_fields: dict, obj_name: str = "") -> Record:
    """
    Overwrite a TSTC/TSTCC/TSTCT row's per-object content from the repo's
    .tran.xml. Called AFTER the generic per-row rename (TCODE, request
    number) has already run -- this fills in content that is genuinely new
    per object, mirroring _apply_dtel_row / _apply_ttyp_row. TSTCP is NOT
    handled here (it needs a row-count/action change, not a fixed-shape
    overwrite) -- see _regenerate_tran_tstcp, called once after this per-row
    pass has finished.
    """
    if table == "TSTC":
        tstc = tran_fields.get("TSTC") or {}
        for fname in _TRAN_TSTC_TEXT_FIELDS:
            # Absent (parameter transaction: no PGMNA/DYPNO at all) blanks
            # the field rather than leaving the template's own stale
            # report-transaction values -- same "never leave stale
            # per-object content" rule DTEL's DOMNAME/DATATYPE pair and
            # TTYP's TYPELEN blanking both apply.
            row = _write_dd04_field(row, fields, fname, tstc.get(fname, ""))
        for fname in _TRAN_TSTC_BLANK_FIELDS:
            row = _write_dd04_field(row, fields, fname, "")
        cinfo_b64 = tstc.get("CINFO", "")
        cinfo_bytes = b""
        if cinfo_b64:
            try:
                cinfo_bytes = base64.b64decode(cinfo_b64)
            except Exception as exc:
                print(f"  WARNING: {obj_name or '(object)'}: could not "
                      f"decode CINFO base64 {cinfo_b64!r}: {exc}")
        cinfo_flen = next((flen for name, _off, flen, _ft in (fields or [])
                           if name == "CINFO"), None)
        if cinfo_flen is not None and len(cinfo_bytes) > cinfo_flen:
            print(f"  WARNING: {obj_name or '(object)'}: CINFO is "
                  f"{len(cinfo_bytes)} bytes, template field is only "
                  f"{cinfo_flen} -- truncated (not observed in any real "
                  f".tran.xml surveyed, where CINFO is always 1 byte)")
        row = _write_raw_field_by_name(row, fields, "CINFO", cinfo_bytes)
    elif table == "TSTCC":
        # Client-independent GUI-availability flags -- presence-based, field
        # names vary by SAP release (S_WEBGUI/S_WIN32/... observed; newer
        # releases add more S_* flags). Every field the template's own
        # nametab knows about (except the key field TCODE, already renamed
        # generically) is reset from the repo's XML by name -- absent in
        # the XML means blanked, not left at the template's stale value,
        # since these are per-object availability flags, not boilerplate.
        tstcc = tran_fields.get("TSTCC") or {}
        for fname, _off, _flen, _ftype in fields or []:
            if fname == "TCODE":
                continue
            row = _write_dd04_field(row, fields, fname, tstcc.get(fname, ""))
        known = {fname for fname, _off, _flen, _ftype in fields or []}
        unmatched = sorted(f for f in tstcc if f not in known and f != "TCODE")
        if unmatched:
            print(f"  WARNING: {obj_name or '(object)'}: TSTCC flag(s) "
                  f"{unmatched} from the repo's .tran.xml are not in the "
                  f"template's own TSTCC nametab and were silently ignored "
                  f"(not observed in any real .tran.xml surveyed, where "
                  f"only S_WEBGUI/S_WIN32/S_PLATIN appear)")
    elif table == "TSTCT":
        tstct = tran_fields.get("TSTCT") or {}
        lang = tstct.get("SPRSL", "") or "D"
        ttext = tstct.get("TTEXT") or _make_description(obj_name)
        row = _write_dd04_field(row, fields, "SPRSL", lang)
        row = _write_dd04_field(row, fields, "TTEXT", ttext)
    return row


def fix_tran_tstct_language_key(h_rec: Record, new_lang: str) -> Record:
    """
    TSTCT's H-record key packs SPRSL(1) + TCODE -- verified against the
    template's actual bytes: 'D' + TCODE +
    spaces, with NO trailing '*' marker at all. This is a DIFFERENT shape
    than every prior type's language-keyed table (DD04T/T100T/DD02T/DD40T
    all pack NAME(padded) + LANG(1) + '*', language LAST) -- TSTCT packs the
    language FIRST, with no marker character to protect at all. Checked
    proactively per the task brief's explicit instruction to verify this
    pattern rather than assume it: `_fix_dtel_ddlanguage_key`'s `rfind('*')`
    would find nothing here (star == -1) and silently no-op, which would
    have been a real, easy-to-miss bug.

    The shape that DOES match is MSAG's T100/T100T key (SPRSL(1) +
    ARBGB(20, padded) + '*' -- language FIRST, verified in
    _fix_msag_language_key's own docstring) for the "language is the very
    first byte of the key" part specifically, which is genuinely generic
    (it just overwrites payload[48], not dependent on anything after it) --
    so TSTCT reuses _fix_msag_language_key directly rather than duplicating
    a near-identical function a third time, the same "generalizes, don't
    duplicate" call TABL made when it reused _fix_dtel_ddlanguage_key for
    DD02T's key instead of writing its own.
    """
    return _fix_msag_language_key(h_rec, new_lang)


def regenerate_tran_tstcp(records: list, obj_name: str,
                           tstcp_fields) -> list:
    """
    TSTCP (the parameter-transaction PARAM string) is entirely absent from
    a report transaction's .tran.xml and present only for a parameter
    transaction. The template (a report transaction)
    ships TSTCP as an empty '00DELL' delete-sweep with zero rows -- already
    correct, unmodified, for a report-transaction repo (tstcp_fields is
    None: nothing to add, block left as-is). When the repo's .tran.xml DOES
    carry a <TSTCP> block, the delete-sweep is converted to a '00REP '
    single-row insert carrying TCODE + PARAM -- the same "synthesize a new-
    shape row set on top of a template's delete-only block" move MSAG/TABL
    use for their own variable-row-count content, just fixed at exactly one
    row here since a transaction has at most one TSTCP row.
    """
    if tstcp_fields is None:
        return records
    nametabs = _parse_nametabs(records)
    fields = nametabs.get("TSTCP")
    blk = _find_block(records, "TSTCP")
    if blk is None or not fields:
        print(f"  WARNING: {obj_name}: repo declares TSTCP (parameter "
              f"transaction) but the template has no TSTCP block -- "
              f"parameter data cannot be shipped")
        return records
    h_idx, row_idxs, e_idx = blk
    h_rec = records[h_idx]
    param = tstcp_fields.get("PARAM", "")
    if not param:
        print(f"  WARNING: {obj_name}: repo declares <TSTCP> but it has no "
              f"<PARAM> (or it's empty) -- shipping a parameter-transaction "
              f"row with a blank PARAM, which is not what real abapGit "
              f"exports for a parameter transaction")
    row = _blank_row(fields)
    row = _write_field_by_name(row, fields, "TCODE", obj_name)
    row = _write_field_by_name(row, fields, "PARAM", param)
    # Flip the action from '00DELL' (delete sweep, 0 rows) to '00REP '
    # (full-row insert) -- same 6-char width, no re-padding needed. The H
    # key itself was already renamed to the target object generically
    # (same TCODE(20)+'*' shape TSTC/TSTCC share) before this function runs.
    payload = bytearray(h_rec.payload)
    payload[38:44] = b"00REP "
    records[h_idx] = Record(offset=h_rec.offset, rtype=h_rec.rtype,
                            payload=bytes(payload), fragments=h_rec.fragments)
    _replace_rows_in_block(records, (h_idx, row_idxs, e_idx), [row])
    print(f"  TSTCP: parameter transaction, PARAM={param!r}")
    return records
