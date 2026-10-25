"""Generic ABAP Query (AQ*) transport row regenerators."""

import base64
import binascii
from collections.abc import Callable

from sap_transport_records import Record


_helpers: dict[str, Callable] = {}


def configure_query_helpers(**helpers: Callable) -> None:
    """Provide shared record helpers owned by the compatibility facade."""
    _helpers.update(helpers)


def _helper(name: str) -> Callable:
    try:
        return _helpers[name]
    except KeyError as exc:
        raise RuntimeError(f"query helper {name!r} has not been configured") from exc


def _parse_nametabs(*args, **kwargs):
    return _helper("parse_nametabs")(*args, **kwargs)


def _find_block_by_action(*args, **kwargs):
    return _helper("find_block_by_action")(*args, **kwargs)


def _blank_row(*args, **kwargs):
    return _helper("blank_row")(*args, **kwargs)


def _replace_rows_in_block(*args, **kwargs):
    return _helper("replace_rows_in_block")(*args, **kwargs)


def _write_field_by_name(*args, **kwargs):
    return _helper("write_field_by_name")(*args, **kwargs)


def _write_raw_field_by_name(*args, **kwargs):
    return _helper("write_raw_field_by_name")(*args, **kwargs)


def regenerate_aqbg_rows(records: list, aqbg_meta: dict) -> list:
    fields = _parse_nametabs(records).get("AQGDBBG") or []
    block = _find_block_by_action(records, "AQGDBBG", "00REP ")
    if block and fields:
        for index in block[1]:
            row = records[index]
            for name, value in aqbg_meta.items(): row = _write_field_by_name(row, fields, name, value)
            records[index] = row
    return records


def regenerate_aqqu_rows(records: list, aqqu_meta: dict) -> list:
    """Regenerate the generic AQQU tables from abapGit's serialized rows.

    ``AQGDB-CLUSTD`` is binary and represented by abapGit as base64; all
    other supported fields are character-like.  The captured AQQU template
    provides the exact fixed-width row layout and delete sweeps.
    """
    tabs = _parse_nametabs(records)
    for table, action in (("AQGQCAT", "00REP "), ("AQGDB", "00REPC"),
                          ("AQGTQ", "00REPC")):
        rows_meta = aqqu_meta.get(table) or []
        if not rows_meta:
            continue
        fields = tabs.get(table) or []
        block = _find_block_by_action(records, table, action)
        if not fields or not block:
            continue
        donor = records[block[1][0]] if block[1] else _blank_row(fields)
        rows = []
        for meta in rows_meta:
            row = Record(offset=0, rtype=" ", payload=donor.payload,
                         fragments=1)
            for name, value in meta.items():
                row = write_aq_value(row, fields, name, value, table)
            rows.append(row)
        _replace_rows_in_block(records, block, rows)
    return records


def regenerate_aqsg_rows(records: list, aqsg_meta: dict) -> list:
    """Regenerate generic AQSG catalogue and cluster rows."""
    tabs = _parse_nametabs(records)
    for table, action in (("AQGSCAT", "00REP "), ("AQGDB", "00REPC")):
        rows_meta = aqsg_meta.get(table) or []
        fields = tabs.get(table) or []
        block = _find_block_by_action(records, table, action)
        if not rows_meta or not fields or not block:
            continue
        donor = records[block[1][0]] if block[1] else _blank_row(fields)
        rows = []
        for meta in rows_meta:
            row = Record(offset=0, rtype=" ", payload=donor.payload, fragments=1)
            for name, value in meta.items():
                row = write_aq_value(row, fields, name, value, table)
            rows.append(row)
        _replace_rows_in_block(records, block, rows)
    return records


def write_aq_value(row: Record, fields: list, name: str, value: str,
                    table: str) -> Record:
    """Write one generic AQ* value, preserving binary ABAP field types."""
    field = next((entry for entry in fields if entry[0] == name), None)
    if field is None:
        return row
    _field, offset, length, dtype = field
    if dtype == "X":
        try:
            return _write_raw_field_by_name(row, fields, name,
                                            base64.b64decode(value))
        except (ValueError, TypeError, binascii.Error) as exc:
            raise ValueError(f"AQ {table}-{name} must be base64: {exc}") from exc
    if dtype in {"I", "S"}:
        try:
            raw = int(value or "0").to_bytes(length, "little", signed=True)
        except (ValueError, OverflowError) as exc:
            raise ValueError(f"AQ {table}-{name} must be an integer: {value!r}") from exc
        payload = bytearray(row.payload)
        payload[offset:offset + length] = raw
        return Record(offset=row.offset, rtype=row.rtype, payload=bytes(payload),
                      fragments=row.fragments)
    return _write_field_by_name(row, fields, name, value)
