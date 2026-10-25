"""Shared SAP transport record-block primitives for object regenerators."""

from sap_transport_records import Record


def find_block_by_action(records, table: str, action: str):
    """
    Like _find_block, but matches a specific action code too -- MSAG's
    T100/T100T tables have both a 49-language delete sweep (action
    '00DELL') AND a single '00REPC' fill block sharing the same table name,
    so the plain first-match _find_block would find a delete block (0 rows)
    instead of the one we need to regenerate rows in.
    Returns (h_idx, row_indices, e_idx) or None.
    """
    needle = table.encode("latin-1")
    for i, rec in enumerate(records):
        if (rec.rtype == "H" and rec.payload[8:8 + len(needle)] == needle
                and rec.payload[8 + len(needle):9 + len(needle)] == b" "
                and rec.payload[38:44].decode("latin-1") == action):
            rows = []
            j = i + 1
            while j < len(records) and records[j].rtype != "E":
                if records[j].rtype == " ":
                    rows.append(j)
                j += 1
            return i, rows, j
    return None


def replace_rows_in_block(records: list, blk, new_rows: list) -> None:
    """Replace the rows of an ALREADY-LOCATED block (h_idx, row_idxs, e_idx)
    -- unlike _replace_block_rows, this does not re-find by table name, so
    it stays targeted at one specific block even when several blocks share
    the same table name (MSAG's T100/T100T delete-sweep + REPC blocks)."""
    h_idx, row_idxs, _e_idx = blk
    for idx in reversed(row_idxs):
        del records[idx]
    pos = h_idx + 1
    for row in reversed(new_rows):
        records.insert(pos, row)


def blank_row(fields: list) -> Record:
    """A row of UTF-16LE spaces sized exactly to `fields` -- used when a
    table's REPC block template has zero rows to clone field values from."""
    length = sum(flen for _n, _o, flen, _t in fields)
    return Record(offset=0, rtype=" ", payload=b"\x20\x00" * (length // 2),
                  fragments=1)


def remove_block(records: list, blk) -> None:
    """Delete an entire already-located block (H record through E record,
    inclusive) from the record list. Used for content this generator has no
    real-import ground truth for on a *particular* object -- e.g. TABL's
    DD09L (technical settings) block when the repo's own .tabl.xml carries
    no <DD09L> element at all (the structure case, TABCLASS=INTTAB): a real
    SAP export of a plain structure genuinely does not carry this block
    (confirmed against two real .tabl.xml samples, see docs/tabl-support.md),
    so shipping it anyway -- even zeroed -- would be less faithful than not
    shipping it, the same 'drop unmatched content' rule every other type
    already applies at the row level (TABL's own COMPTYPE=S field drop,
    FUGR's nonexistent-CP-include drop, ...). Unlike _replace_rows_in_block,
    this removes the H and E markers too, not just the rows between them."""
    h_idx, _row_idxs, e_idx = blk
    del records[h_idx:e_idx + 1]




def get_field_text(payload: bytes, fields: list, fname: str) -> str:
    """Decode one UTF-16LE field from a row by NAME (stripped)."""
    for name, off, flen, _ftype in fields or []:
        if name == fname and off + flen <= len(payload):
            try:
                return payload[off:off + flen].decode("utf-16-le").rstrip()
            except UnicodeDecodeError:
                return ""
    return ""


def write_field_by_name(row: Record, fields: list, fname: str,
                         value: str) -> Record:
    """
    Write one field by NAME into a row -- offset 120 is CMPTYPE in SEOCOMPO
    but LANGU in SEOCOMPOTX, so fixed offsets would clobber the wrong field.
    Value is truncated to the field, the remainder is space-padded.
    """
    payload = bytearray(row.payload)
    for name, off, flen, _ftype in fields or []:
        if name != fname or off + flen > len(payload):
            continue
        encoded = value.encode("utf-16-le")
        if len(encoded) > flen:
            encoded = encoded[:flen]
        payload[off:off + flen] = encoded.ljust(flen, b"\x00")[:flen]
        tail = off + len(encoded)
        while tail + 1 < off + flen:
            payload[tail:tail + 2] = b"\x20\x00"
            tail += 2
        break
    return Record(offset=row.offset, rtype=row.rtype,
                  payload=bytes(payload), fragments=row.fragments)


def write_raw_field_by_name(row: Record, fields: list, fname: str,
                             raw: bytes) -> Record:
    """
    Write RAW (non-text) bytes into an X-type field by name -- e.g. TSTC's
    CINFO, a single binary control-info byte. Unlike _write_field_by_name /
    _write_dd04_field (which encode a string as UTF-16LE or a zero-padded
    NUMC digit string), an X-type field's bytes are the value itself, one
    byte per unit width (not doubled) -- written verbatim, truncated or
    zero-padded to the field's own byte width.
    """
    payload = bytearray(row.payload)
    for name, off, flen, _ftype in fields or []:
        if name != fname or off + flen > len(payload):
            continue
        data = raw[:flen].ljust(flen, b"\x00")
        payload[off:off + flen] = data
        break
    return Record(offset=row.offset, rtype=row.rtype,
                  payload=bytes(payload), fragments=row.fragments)
