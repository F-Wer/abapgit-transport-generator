"""Helpers for reading and updating R3trans record blocks."""

from collections.abc import Sequence


def parse_nametabs(records: Sequence) -> dict:
    """Return transported table layouts keyed by table name.

    A layout starts with an N record and continues with 38-byte field
    definitions until its closing E record. Each returned field is
    (name, byte_offset, byte_length, ABAP_type).
    """
    tabs = {}
    for index, record in enumerate(records):
        if record.rtype != "N":
            continue
        table = record.payload[8:38].decode("latin-1").rstrip()
        fields = []
        offset = 0
        cursor = index + 1
        while cursor < len(records) and records[cursor].rtype != "E":
            payload = records[cursor].payload
            if records[cursor].rtype == " " and len(payload) == 38:
                try:
                    field_length = int(payload[2:8].decode("latin-1"))
                except ValueError:
                    break
                fields.append(
                    (
                        payload[8:38].decode("latin-1").rstrip(),
                        offset,
                        field_length,
                        chr(payload[1]),
                    )
                )
                offset += field_length
            cursor += 1
        if fields:
            tabs[table] = fields
    return tabs


def find_block(records: Sequence, table: str):
    """Find the first data block for exactly the supplied table name.

    Returns (header_index, row_indices, end_index) or None. The trailing-space
    check prevents a prefix match, for example SEOCOMPO matching SEOCOMPODF.
    """
    needle = table.encode("latin-1")
    for index, record in enumerate(records):
        if (
            record.rtype == "H"
            and record.payload[8 : 8 + len(needle)] == needle
            and record.payload[8 + len(needle) : 9 + len(needle)] == b" "
        ):
            rows = []
            cursor = index + 1
            while cursor < len(records) and records[cursor].rtype != "E":
                if records[cursor].rtype == " ":
                    rows.append(cursor)
                cursor += 1
            return index, rows, cursor
    return None


def replace_block_rows(records: list, table: str, new_rows: list) -> None:
    """Replace the data rows of the first table block in place."""
    block = find_block(records, table)
    if block is None:
        return
    for index in reversed(block[1]):
        del records[index]

    block = find_block(records, table)
    if block is None:
        return
    insert_at = block[0] + 1
    while insert_at < len(records) and records[insert_at].rtype == " ":
        insert_at += 1
    for row in reversed(new_rows):
        records.insert(insert_at, row)
