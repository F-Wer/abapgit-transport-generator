"""XSLT transport regeneration helpers."""

import struct
from collections.abc import Callable

import pysapcompress

from sap_transport_records import Record


_helpers: dict[str, Callable] = {}


def configure_xslt_helpers(**helpers: Callable) -> None:
    """Configure shared facade helpers used by XSLT regeneration."""
    _helpers.update(helpers)


def _helper(name: str) -> Callable:
    try:
        return _helpers[name]
    except KeyError as exc:
        raise RuntimeError(f"XSLT helper {name!r} has not been configured") from exc


def _parse_nametabs(*args, **kwargs):
    return _helper("parse_nametabs")(*args, **kwargs)


def _find_block(*args, **kwargs):
    return _helper("find_block")(*args, **kwargs)


def _write_field_by_name(*args, **kwargs):
    return _helper("write_field_by_name")(*args, **kwargs)


def _blank_row(*args, **kwargs):
    return _helper("blank_row")(*args, **kwargs)


def _replace_rows_in_block(*args, **kwargs):
    return _helper("replace_rows_in_block")(*args, **kwargs)


_XSLT_CLUSTER_ENVELOPE = bytes.fromhex("ff06020102028000") + b"4103" + b"\x00" * 4


def _decompress_xslt_cluster(clustd: bytes) -> bytes:
    """Decompress an O2XSLTDESC-CLUSTD field's real content -- see the
    module comment above for the full grammar."""
    if clustd[:8] != _XSLT_CLUSTER_ENVELOPE[:8] or clustd[8:12] != b"4103":
        raise ValueError(
            f"CLUSTD envelope magic mismatch: {clustd[:12].hex()} -- "
            f"template may have changed")
    return pysapcompress._LZHDecompress(bytes(clustd[16:])).decompress()


def _recompress_xslt_cluster(decompressed: bytes) -> bytes:
    """Inverse of _decompress_xslt_cluster: recompress and re-wrap in the
    same 16-byte envelope. Returns the cluster's exact bytes (unpadded)."""
    _status, _comp_len, compressed = pysapcompress.compress(
        decompressed, algorithm=pysapcompress.ALG_LZH)
    return _XSLT_CLUSTER_ENVELOPE + bytes(compressed)


def _locate_xslt_chunks(decompressed: bytes) -> list:
    """
    Find every 0xBC-marked chunk of the transformation-source field inside
    a decompressed XSLT cluster payload. Returns a list of
    (marker_pos, value_start, length) tuples in ascending byte order.

    Anchored on contiguity rather than a blind scan for 0xBC bytes (which
    could hit incidental noise elsewhere in the buffer, the same false-
    positive risk ENHO's _locate_enho_bc_markers already guards against
    differently): the first chunk is the first 0xBC whose declared length
    fits in the buffer; every next chunk must start exactly 1 byte (the
    gap marker) after the previous chunk's value ends, or the run stops.
    """
    chunks = []
    pos = decompressed.find(b"\xbc")
    while pos != -1 and pos + 5 <= len(decompressed):
        length = struct.unpack_from(">I", decompressed, pos + 1)[0]
        value_start = pos + 5
        if value_start + length > len(decompressed) or length <= 0 or length > 4096:
            pos = decompressed.find(b"\xbc", pos + 1)
            continue
        chunks.append((pos, value_start, length))
        next_pos = value_start + length + 1   # +1 for the next gap byte
        if (next_pos < len(decompressed) and decompressed[next_pos] == 0xBC):
            pos = next_pos
        else:
            break
    return chunks


def _read_xslt_chunked_text(decompressed: bytes, chunks: list) -> str:
    """Reassemble a chunked field's full text (see _locate_xslt_chunks)."""
    return "".join(
        decompressed[vs:vs + length].decode("utf-16-le", errors="replace")
        for _mp, vs, length in chunks)


def _write_xslt_chunked_text(decompressed: bytearray, chunks: list,
                             new_text: str, obj_name: str) -> None:
    """
    In-place rewrite of a chunked field's full text, absorbing into
    trailing UTF-16LE space padding across the WHOLE chunk sequence (never
    changing chunk count/boundaries -- see the module comment above for
    why). Raises ValueError if new_text doesn't fit.
    """
    total_budget = sum(length for _mp, _vs, length in chunks)
    encoded = new_text.encode("utf-16-le")
    if len(encoded) > total_budget:
        raise ValueError(
            f"XSLT {obj_name}: transformation source too long "
            f"({len(encoded)} bytes needed, {total_budget} bytes "
            f"available across {len(chunks)} chunk(s) in this template) "
            f"-- a real, disclosed limitation, see "
            f"SICF_XSLT_SFPF_SFPI_PROGRESS.md")
    pad_needed = total_budget - len(encoded)
    padded = encoded + b"\x20\x00" * (pad_needed // 2)
    offset = 0
    for _mp, vs, length in chunks:
        decompressed[vs:vs + length] = padded[offset:offset + length]
        offset += length


def _regenerate_xslt_rows(records: list, obj_name: str, xslt_meta: dict) -> list:
    """
    Rewrite O2XSLTDESC (header + CLUSTD's own transformation-source
    content) and O2XSLTTEXT (the description, see _regenerate_xslt_text)
    from the repo's own .xslt.xml + .xslt.source.xml. O2XSLTOTR (OTR text
    usage) is left untouched -- the real template has 0 rows there too and
    no real sample with OTR-based translated text was found to learn the
    shape from; a repo declaring OTR-style text is a documented limitation,
    not guessed at.
    """
    nametabs = _parse_nametabs(records)
    desc_blk = _find_block(records, "O2XSLTDESC")
    if desc_blk is None:
        return records
    _h_idx, row_idxs, _e_idx = desc_blk
    if not row_idxs:
        print(f"  WARNING: {obj_name}: template has no O2XSLTDESC row -- "
              f"XSLT content not rewritten")
        return records
    desc_fields = nametabs.get("O2XSLTDESC") or []
    desc_row = records[row_idxs[0]]

    new_row = _write_field_by_name(desc_row, desc_fields, "XSLTDESC", obj_name)

    clustd_field = next((f for f in desc_fields if f[0] == "CLUSTD"), None)
    source = xslt_meta.get("source") or ""
    if clustd_field is None:
        raise ValueError(f"XSLT {obj_name}: template has no CLUSTD field")
    if not source:
        # Shipping the template's transformation under this object's name
        # would be silently wrong content -- refuse instead.
        raise ValueError(f"XSLT {obj_name}: no .xslt.source.xml found")
    _fname, offset, flen, _ftype = clustd_field
    cluster = _recompress_xslt_cluster(_replace_xslt_source_table(
        _decompress_xslt_cluster(bytes(new_row.payload[offset:offset + flen])),
        source, obj_name))
    # A cluster longer than one row's CLUSTD continues in further rows,
    # numbered by SRTF2; CLUSTR is the number of CLUSTD bytes a row uses.
    new_rows = []
    for srtf2, at in enumerate(range(0, len(cluster), flen)):
        piece = cluster[at:at + flen]
        payload = bytearray(new_row.payload)
        payload[offset:offset + flen] = piece.ljust(flen, b"\x00")
        for name, off, length, _t in desc_fields:
            if name == "SRTF2":
                payload[off:off + length] = srtf2.to_bytes(length, "big")
            elif name == "CLUSTR":
                payload[off:off + length] = len(piece).to_bytes(length, "big")
        new_rows.append(Record(offset=new_row.offset, rtype=new_row.rtype,
                               payload=bytes(payload),
                               fragments=new_row.fragments))
    _replace_rows_in_block(records, desc_blk, new_rows)
    print(f"  XSLT transformation source for {obj_name}: "
          f"{len(cluster)} cluster bytes in {len(new_rows)} row(s)")

    _regenerate_xslt_text(records, nametabs.get("O2XSLTTEXT") or [], obj_name,
                          (xslt_meta.get("langu") or "E")[:1],
                          xslt_meta.get("descript") or "")
    return records


def _key_language(h_rec: Record) -> str:
    """Language character of an O2XSLTTEXT key: XSLTDESC + LANGU + '*'."""
    key = h_rec.payload[48:].decode("latin-1")
    star = key.rfind("*")
    return key[star - 1] if star > 0 else ""


def _with_key_language(h_rec: Record, langu: str) -> Record:
    key = h_rec.payload[48:].decode("latin-1")
    star = key.rfind("*")
    payload = bytearray(h_rec.payload)
    payload[48:] = (key[:star - 1] + langu + key[star:]).encode("latin-1")
    return Record(offset=h_rec.offset, rtype=h_rec.rtype,
                  payload=bytes(payload), fragments=h_rec.fragments)


def _regenerate_xslt_text(records: list, fields: list, obj_name: str,
                          langu: str, descript: str) -> None:
    """Put the repo's description into the insert block for its language.

    The template sweeps every language with a delete block and inserts its
    own German text in a single 00REPC block. Rekey that block to the
    repo's language and give the language's delete block the template
    language instead, so each language is still swept exactly once.
    """
    heads = [i for i, rec in enumerate(records)
             if rec.rtype == "H" and rec.payload[8:38].rstrip() == b"O2XSLTTEXT"]
    insert = next((i for i in heads
                   if records[i].payload[38:44] == b"00REPC"), None)
    if insert is None or not fields:
        if descript:
            print(f"  WARNING: {obj_name}: template has no O2XSLTTEXT insert "
                  f"block -- description not transported")
        return
    old = _key_language(records[insert])
    if old and old != langu:
        for i in heads:
            if i != insert and _key_language(records[i]) == langu:
                records[i] = _with_key_language(records[i], old)
        records[insert] = _with_key_language(records[insert], langu)

    end = insert + 1
    while records[end].rtype != "E":
        end += 1
    row_idxs = [i for i in range(insert + 1, end) if records[i].rtype == " "]
    rows = []
    if descript:
        row = records[row_idxs[0]] if row_idxs else _blank_row(fields)
        row = _write_field_by_name(row, fields, "XSLTDESC", obj_name)
        row = _write_field_by_name(row, fields, "LANGU", langu)
        row = _write_field_by_name(row, fields, "DESCRIPT", descript)
        rows.append(row)
        print(f"  XSLT description text for {obj_name}: {descript!r} ({langu})")
    _replace_rows_in_block(records, (insert, row_idxs, end), rows)



decompress_xslt_cluster = _decompress_xslt_cluster
recompress_xslt_cluster = _recompress_xslt_cluster
locate_xslt_chunks = _locate_xslt_chunks
read_xslt_chunked_text = _read_xslt_chunked_text
write_xslt_chunked_text = _write_xslt_chunked_text
regenerate_xslt_rows = _regenerate_xslt_rows
