"""Message-class transport regeneration helpers.

The legacy generator configures shared record helpers after module initialization,
so this module has no reverse dependency on the CLI compatibility facade.
"""

from collections.abc import Callable

from sap_transport_records import Record


_helpers: dict[str, Callable] = {}


def configure_msag_helpers(**helpers: Callable) -> None:
    """Provide shared record helpers owned by the compatibility facade."""
    _helpers.update(helpers)


def _helper(name: str) -> Callable:
    try:
        return _helpers[name]
    except KeyError as exc:
        raise RuntimeError(f"MSAG helper {name!r} has not been configured") from exc


def _parse_nametabs(*args, **kwargs):
    return _helper("parse_nametabs")(*args, **kwargs)


def _make_description(*args, **kwargs):
    return _helper("make_description")(*args, **kwargs)


def _find_block_by_action(*args, **kwargs):
    return _helper("find_block_by_action")(*args, **kwargs)


def _write_field_by_name(*args, **kwargs):
    return _helper("write_field_by_name")(*args, **kwargs)


def _blank_row(*args, **kwargs):
    return _helper("blank_row")(*args, **kwargs)


def _replace_rows_in_block(*args, **kwargs):
    return _helper("replace_rows_in_block")(*args, **kwargs)


def fix_msag_language_key(h_rec: Record, new_lang: str) -> Record:
    """
    T100/T100T's H-record key packs SPRSL(1) + ARBGB(20, padded) + '*'
    (verified against the template: 'D<ARBGB, 20 chars>*'). The generic
    rename only touches the ARBGB portion, so the language character would
    otherwise still read the template's own language even when the repo's
    MASTERLANG differs -- the REPC block's key would then disagree with the
    SPRSL its own regenerated rows carry (mirrors the DTEL sibling's
    _fix_dtel_ddlanguage_key for DD04T, same bug class in a different field
    position -- MSAG's language char is the FIRST byte of the key, DTEL's
    DDLANGUAGE is the last before '*'). Overwrite just that one leading
    character (fixed position, no re-padding needed).
    """
    if not new_lang:
        return h_rec
    key_area = h_rec.payload[48:]
    text = key_area.decode("latin-1")
    if not text:
        return h_rec
    text = new_lang[0] + text[1:]
    payload = bytearray(h_rec.payload)
    payload[48:] = text.encode("latin-1")
    return Record(offset=h_rec.offset, rtype=h_rec.rtype,
                  payload=bytes(payload), fragments=h_rec.fragments)



def regenerate_msag_rows(records: list, obj_name: str,
                          msag_meta: dict) -> list:
    """
    Regenerate the T100 (message text) and T100U (usage flags) row sets
    from the repo's message list, and set T100T / T100A's STEXT (plus the
    actual target language, everywhere it is recorded) to the repo's class
    header. Operates on an already-renamed record list (the generic
    per-record pass has already renamed every H-record key and
    substring-renamed the object name inside existing rows -- but NOT the
    language character packed into the T100/T100T REPC block's own H-key,
    which needs fixing here once the target language is known; see
    _fix_msag_language_key).
    """
    nametabs = _parse_nametabs(records)
    master_lang = (msag_meta.get("masterlang") or "D")[:1] or "D"
    stext = msag_meta.get("stext") or _make_description(obj_name)
    messages = msag_meta.get("messages") or []

    # --- T100: one '00REPC' row per message ---
    t100_fields = nametabs.get("T100")
    t100_blk = _find_block_by_action(records, "T100", "00REPC")
    if t100_blk is not None and t100_fields:
        donor = records[t100_blk[1][0]] if t100_blk[1] else None
        new_rows = []
        for msgnr, msg_text in messages:
            row = (Record(offset=0, rtype=" ", payload=donor.payload, fragments=1)
                   if donor is not None else _blank_row(t100_fields))
            row = _write_field_by_name(row, t100_fields, "SPRSL", master_lang)
            row = _write_field_by_name(row, t100_fields, "ARBGB", obj_name)
            row = _write_field_by_name(row, t100_fields, "MSGNR", msgnr)
            row = _write_field_by_name(row, t100_fields, "TEXT", msg_text)
            new_rows.append(row)
        _replace_rows_in_block(records, t100_blk, new_rows)
        records[t100_blk[0]] = fix_msag_language_key(
            records[t100_blk[0]], master_lang)
        print(f"  MSAG messages for {obj_name}: {len(new_rows)} "
              f"(was {len(t100_blk[1])} in the template)")
    elif messages:
        print("  WARNING: template has no T100 REPC block -- "
              "messages cannot be regenerated")

    # --- T100U: one row per message (NAME/DATUM/SELFDEF from the template's
    # own donor row -- these are importer-assigned bookkeeping fields with
    # no equivalent in the abapGit XML, see the module docstring above) ---
    t100u_fields = nametabs.get("T100U")
    t100u_blk = _find_block_by_action(records, "T100U", "00REPC")
    if t100u_blk is not None and t100u_fields:
        donor = records[t100u_blk[1][0]] if t100u_blk[1] else None
        new_rows = []
        for msgnr, _msg_text in messages:
            row = (Record(offset=0, rtype=" ", payload=donor.payload, fragments=1)
                   if donor is not None else _blank_row(t100u_fields))
            row = _write_field_by_name(row, t100u_fields, "ARBGB", obj_name)
            row = _write_field_by_name(row, t100u_fields, "MSGNR", msgnr)
            new_rows.append(row)
        _replace_rows_in_block(records, t100u_blk, new_rows)

    # --- T100T: row count unchanged (1) -- SPRSL + STEXT in the row, and
    # the language character in the block's own H-key (M1: both were
    # previously left at the template's own language, contradicting
    # T100A.MASTERLANG and the SPRSL the row actually carries) ---
    t100t_fields = nametabs.get("T100T")
    t100t_blk = _find_block_by_action(records, "T100T", "00REPC")
    if t100t_blk is not None and t100t_fields:
        for ridx in t100t_blk[1]:
            row = _write_field_by_name(records[ridx], t100t_fields,
                                       "SPRSL", master_lang)
            row = _write_field_by_name(row, t100t_fields, "STEXT", stext)
            records[ridx] = row
        records[t100t_blk[0]] = fix_msag_language_key(
            records[t100t_blk[0]], master_lang)

    # --- T100A: row count unchanged (1), STEXT + MASTERLANG in place ---
    t100a_fields = nametabs.get("T100A")
    t100a_blk = _find_block_by_action(records, "T100A", "00REPC")
    if t100a_blk is not None and t100a_fields:
        for ridx in t100a_blk[1]:
            row = _write_field_by_name(records[ridx], t100a_fields, "STEXT", stext)
            row = _write_field_by_name(row, t100a_fields, "MASTERLANG",
                                       master_lang)
            records[ridx] = row

    return records
