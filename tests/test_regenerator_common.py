"""Unit and compatibility tests for shared regenerator record primitives."""

import abapgit_to_transport as legacy
from sap_transport_records import Record
from transport_regenerators import common


def test_block_helpers_find_replace_and_remove_target_the_exact_block() -> None:
    header = bytearray(b" " * 50)
    header[8:12] = b"T100"
    header[38:44] = b"00REPC"
    records = [
        Record(0, "H", bytes(header), 1),
        Record(0, " ", b"first", 1),
        Record(0, "E", b"", 1),
    ]

    block = common.find_block_by_action(records, "T100", "00REPC")
    assert block == (0, [1], 2)
    common.replace_rows_in_block(records, block, [Record(0, " ", b"next", 1)])
    assert records[1].payload == b"next"
    common.remove_block(records, common.find_block_by_action(records, "T100", "00REPC"))
    assert records == []


def test_field_writers_and_blank_row_keep_record_shape() -> None:
    fields = [("TEXT", 0, 10, "C"), ("RAW", 10, 2, "X")]
    blank = common.blank_row(fields)
    text = common.write_field_by_name(blank, fields, "TEXT", "AB")
    raw = common.write_raw_field_by_name(text, fields, "RAW", b"\x01")
    assert common.get_field_text(raw.payload, fields, "TEXT") == "AB"
    assert raw.payload[10:12] == b"\x01\x00"


def test_common_helpers_remain_legacy_compatibility_exports() -> None:
    assert legacy._find_block_by_action is common.find_block_by_action
    assert legacy._replace_rows_in_block is common.replace_rows_in_block
    assert legacy._blank_row is common.blank_row
    assert legacy._remove_block is common.remove_block
    assert legacy._get_field_text is common.get_field_text
    assert legacy._write_field_by_name is common.write_field_by_name
    assert legacy._write_raw_field_by_name is common.write_raw_field_by_name
