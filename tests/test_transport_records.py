import struct
from pathlib import Path

import pytest

from sap_transport_records import (
    BlockHeader,
    DataBlock,
    FieldDef,
    Nametab,
    Record,
    Transport,
    decode_row,
    export_nametabs,
    extract_sources,
    iter_records,
    key_parts,
    parse_fielddef,
    parse_header,
    parse_stream,
    u16,
    validate,
)


def physical_record(rtype: str, payload: bytes = b"", continuation: int = 0x20) -> bytes:
    return struct.pack(">I", len(payload) + 6) + bytes((continuation, ord(rtype))) + payload


def block_header(table: str, action: str = "00REP ", key: str = "") -> bytes:
    return (
        b"ATAB    "
        + table.encode("latin-1").ljust(30)
        + action.encode("latin-1")
        + b"\0" * 4
        + key.encode("latin-1")
    ).ljust(288)


def field(name: str, dtype: str, length: int, key: bool = False) -> bytes:
    return (
        (b"X" if key else b" ")
        + dtype.encode("ascii")
        + f"{length:06d}".encode("ascii")
        + name.encode("latin-1").ljust(30)
    )


def test_iter_records_joins_fragments_and_rejects_bad_framing() -> None:
    stream = (
        physical_record("U", b"a" * 500, 0x46)
        + physical_record("U", b"b")
        + physical_record("Z")
    )

    records = iter_records(stream)
    assert [(record.rtype, record.fragments, len(record.payload)) for record in records] == [
        ("U", 2, 501),
        ("Z", 1, 0),
    ]

    with pytest.raises(ValueError, match="bad record length"):
        iter_records(b"\0\0\0\x05xx")
    with pytest.raises(ValueError, match="unknown continuation"):
        iter_records(physical_record("Z", continuation=0x01))
    with pytest.raises(ValueError, match="trailing bytes"):
        iter_records(physical_record("Z") + b"x")


def test_helpers_parse_headers_fields_and_rows() -> None:
    header = parse_header(block_header("ZTAB", key="KEY  PART"))
    definition = parse_fielddef(field("NAME", "C", 8, key=True))
    nametab = Nametab(header=header, fields=[definition, FieldDef(False, "X", 2, "RAW")])

    assert header == BlockHeader("ATAB    ", "ZTAB", "00REP ", "KEY  PART")
    assert definition.chars == 4
    assert nametab.row_length == 10
    assert nametab.key_length == 8
    assert decode_row(nametab, "ABCD".encode("utf-16-le") + b"\xaa\xbb") == [
        ("NAME", "ABCD"),
        ("RAW", "aabb"),
    ]
    assert decode_row(nametab, b"") == [("NAME", "<truncated>"), ("RAW", "<truncated>")]
    assert u16(b"A\0B") == "A"
    assert key_parts("  FIRST  SECOND   THIRD ") == ["FIRST", "SECOND", "THIRD"]


def test_parse_stream_builds_objects_nametabs_and_blocks() -> None:
    key = "DEVK900001".ljust(20) + "000001R3TRTABLZTAB"
    attributes = "R3TRTABLZTAB".ljust(58) + "DEV".ljust(10) + "DEV".ljust(12) + " " + "ZPKG".ljust(30)
    row = "ABCD".encode("utf-16-le")
    stream = b"".join(
        [
            physical_record("F", "DEVK900001".encode("utf-16-le")),
            physical_record("*", b"Source System = DEV"),
            physical_record("D"),
            physical_record("C", key.encode("utf-16-le")),
            physical_record("A", attributes.encode("utf-16-le")),
            physical_record("N", block_header("ZTAB")),
            physical_record(" ", field("NAME", "C", 8, key=True)),
            physical_record("E"),
            physical_record("H", block_header("ZTAB")),
            physical_record(" ", row),
            physical_record("E"),
            physical_record("Z"),
        ]
    )

    transport = parse_stream(stream)
    assert transport.request == "DEVK900001"
    assert transport.directives == {"Source System": "DEV"}
    assert transport.objects[0].e071_key.endswith("ZTAB")
    assert transport.objects[0].attributes.rstrip().endswith("ZPKG")
    assert transport.nametabs["ZTAB"].row_length == 8
    assert transport.blocks[0].rows == [row]
    assert validate(transport) == 0


def test_validate_detects_object_and_full_row_mismatches() -> None:
    nametab = Nametab(BlockHeader("ATAB    ", "ZTAB", "00REP ", ""), [FieldDef(True, "C", 8, "NAME")])
    transport = Transport(
        records=[Record(0, "D", b""), Record(6, "C", b""), Record(12, "C", b"")],
        nametabs={"ZTAB": nametab},
        blocks=[DataBlock(BlockHeader("ATAB    ", "ZTAB", "00REP ", ""), 0, [b"too short"])],
    )

    assert validate(transport) == 2


def test_export_nametabs_and_extract_sources(tmp_path: Path) -> None:
    nametab = Nametab(
        BlockHeader("ATAB    ", "ZTAB", "00REP ", ""),
        [FieldDef(True, "C", 8, "NAME"), FieldDef(False, "A", 2, "")],
    )
    output = tmp_path / "nametabs.json"
    export_nametabs([Transport(nametabs={"ZTAB": nametab})], output)
    text = output.read_text(encoding="utf-8")
    assert '"table_count": 1' in text
    assert '"padding": true' in text

    source_rows = [
        b"attribute header",
        "REPORT z_test.".encode("utf-16-le"),
        "WRITE 'ok'.".encode("utf-16-le"),
    ]
    transport = Transport(
        blocks=[
            DataBlock(
                BlockHeader("ABAPREAD", "REPOS", "00REP ", "Z_TEST  Z_TEST"),
                0,
                source_rows,
            )
        ]
    )
    extract_sources(transport, tmp_path / "sources")
    assert (tmp_path / "sources" / "Z_TEST.abap").read_text(encoding="utf-8") == (
        "REPORT z_test.\nWRITE 'ok'.\n"
    )
