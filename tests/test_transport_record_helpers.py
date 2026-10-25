from abapgit_to_transport import (
    _find_block,
    _parse_nametabs,
    _replace_block_rows,
)
from sap_transport_records import Record
from transport_record_helpers import find_block, parse_nametabs, replace_block_rows


def _record(record_type: str, payload: bytes = b"") -> Record:
    return Record(offset=0, rtype=record_type, payload=payload)


def _header(record_type: str, table: str) -> Record:
    return _record(record_type, b"DLIB    " + table.encode("latin-1").ljust(30) + b"00REPC")


def test_parse_nametabs_reports_offsets_and_types() -> None:
    field = b"XC000004FIELD".ljust(38)
    records = [_header("N", "ZTAB"), _record(" ", field), _record("E")]

    assert parse_nametabs(records) == {"ZTAB": [("FIELD", 0, 4, "C")]}


def test_find_block_does_not_match_table_name_prefixes() -> None:
    records = [
        _header("H", "SEOCOMPODF"),
        _record(" ", b"wrong"),
        _record("E"),
        _header("H", "SEOCOMPO"),
        _record(" ", b"right"),
        _record("E"),
    ]

    assert find_block(records, "SEOCOMPO") == (3, [4], 5)


def test_replace_block_rows_preserves_row_order_and_end_marker() -> None:
    records = [
        _header("H", "E071"),
        _record(" ", b"old-1"),
        _record(" ", b"old-2"),
        _record("E"),
    ]
    replacements = [_record(" ", b"new-1"), _record(" ", b"new-2")]

    replace_block_rows(records, "E071", replacements)

    assert [record.payload for record in records[1:3]] == [b"new-1", b"new-2"]
    assert records[3].rtype == "E"


def test_legacy_generator_helper_imports_remain_available() -> None:
    assert _parse_nametabs is parse_nametabs
    assert _find_block is find_block
    assert _replace_block_rows is replace_block_rows
