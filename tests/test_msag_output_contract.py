"""End-to-end characterization of generated message-class transports."""

import pytest
from abapgit_to_transport import (
    _find_block_by_action,
    _get_field_text,
    _parse_nametabs,
    collect_sources,
    generate_transport,
)
from sap_transport_records import iter_records, u16
from sap_transport_writer import decompress_container, parse_container
from test_transport import verify

pytestmark = pytest.mark.templates


def test_message_class_generation_preserves_messages_and_language(tmp_path) -> None:
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    (source_dir / "z_orders.msag.xml").write_text(
        "<abapGit>"
        "<T100A><MASTERLANG>E</MASTERLANG><STEXT>Order messages</STEXT></T100A>"
        "<T100>"
        "<T100><MSGNR>1</MSGNR><TEXT>Order &amp;1 created</TEXT></T100>"
        "<T100><MSGNR>2</MSGNR><TEXT>Order &amp;1 rejected</TEXT></T100>"
        "</T100>"
        "</abapGit>",
        encoding="utf-8",
    )

    sources = collect_sources(source_dir, "MSAG", "Z_ORDERS")
    first_data, first_cofile = generate_transport(
        "MSAG", "Z_ORDERS", sources, "DEVK901003", sid="DEV", package="ZMSAG"
    )
    second_data, second_cofile = generate_transport(
        "MSAG", "Z_ORDERS", sources, "DEVK901003", sid="DEV", package="ZMSAG"
    )

    assert first_data == second_data
    assert first_cofile == second_cofile

    data_file = tmp_path / "R901003.DEV"
    cofile_file = tmp_path / "K901003.DEV"
    data_file.write_bytes(first_data)
    cofile_file.write_bytes(first_cofile)
    assert verify(data_file, "DEVK901003", "ZMSAG") == []

    records = iter_records(decompress_container(parse_container(first_data)))
    nametabs = _parse_nametabs(records)
    t100 = _find_block_by_action(records, "T100", "00REPC")
    assert t100 is not None
    assert len(t100[1]) == 2

    rows = [records[index] for index in t100[1]]
    assert [_get_field_text(row.payload, nametabs["T100"], "SPRSL") for row in rows] == [
        "E",
        "E",
    ]
    assert [_get_field_text(row.payload, nametabs["T100"], "ARBGB") for row in rows] == [
        "Z_ORDERS",
        "Z_ORDERS",
    ]
    assert [_get_field_text(row.payload, nametabs["T100"], "MSGNR") for row in rows] == [
        "001",
        "002",
    ]
    assert [_get_field_text(row.payload, nametabs["T100"], "TEXT") for row in rows] == [
        "Order &1 created",
        "Order &1 rejected",
    ]

    t100t = _find_block_by_action(records, "T100T", "00REPC")
    t100a = _find_block_by_action(records, "T100A", "00REPC")
    assert t100t is not None and t100a is not None
    assert _get_field_text(records[t100t[1][0]].payload, nametabs["T100T"], "SPRSL") == "E"
    assert _get_field_text(records[t100t[1][0]].payload, nametabs["T100T"], "STEXT") == "Order messages"
    assert _get_field_text(records[t100a[1][0]].payload, nametabs["T100A"], "MASTERLANG") == "E"

    object_keys = [u16(record.payload) for record in records if record.rtype == "C"]
    assert len(object_keys) == 1
    assert "MSAG" in object_keys[0]
    assert "Z_ORDERS" in object_keys[0]
