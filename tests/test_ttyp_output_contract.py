"""End-to-end characterization of generated table-type transports."""

import pytest
from abapgit_to_transport import (
    _find_block_by_action,
    _get_field_text,
    _parse_nametabs,
    _apply_ttyp_row,
    _fix_ttyp_ddlanguage_key,
    collect_sources,
    generate_transport,
)
from sap_transport_records import iter_records, u16
from transport_regenerators.ddic import apply_ttyp_row, fix_ttyp_ddlanguage_key
from sap_transport_writer import decompress_container, parse_container
from test_transport import verify


@pytest.mark.templates
def test_table_type_generation_preserves_row_type_and_text(tmp_path) -> None:
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    (source_dir / "ztt_order_id.ttyp.xml").write_text(
        "<abapGit><DD40V><TYPENAME>ZTT_ORDER_ID</TYPENAME>"
        "<DDLANGUAGE>E</DDLANGUAGE><ROWTYPE>Z_ORDER_ID</ROWTYPE>"
        "<ROWKIND>E</ROWKIND><DATATYPE>CHAR</DATATYPE><LENG>10</LENG>"
        "<DECIMALS>0</DECIMALS><ACCESSMODE>R</ACCESSMODE><TTYPKIND>T</TTYPKIND>"
        "<KEYDEF>D</KEYDEF><KEYKIND>N</KEYKIND><KEYFDCOUNT>0</KEYFDCOUNT>"
        "<DDTEXT>Order ID table</DDTEXT></DD40V></abapGit>",
        encoding="utf-8",
    )

    sources = collect_sources(source_dir, "TTYP", "ZTT_ORDER_ID")
    first_data, first_cofile = generate_transport(
        "TTYP", "ZTT_ORDER_ID", sources, "DEVK901012", sid="DEV", package="ZTTYP"
    )
    second_data, second_cofile = generate_transport(
        "TTYP", "ZTT_ORDER_ID", sources, "DEVK901012", sid="DEV", package="ZTTYP"
    )

    assert first_data == second_data
    assert first_cofile == second_cofile

    data_file = tmp_path / "R901012.DEV"
    cofile_file = tmp_path / "K901012.DEV"
    data_file.write_bytes(first_data)
    cofile_file.write_bytes(first_cofile)
    assert verify(data_file, "DEVK901012", "ZTTYP") == []

    records = iter_records(decompress_container(parse_container(first_data)))
    nametabs = _parse_nametabs(records)
    header = _find_block_by_action(records, "DD40L", "00REP ")
    text_rows = _find_block_by_action(records, "DD40T", "00REP ")
    assert header is not None and text_rows is not None
    assert _get_field_text(records[header[1][0]].payload, nametabs["DD40L"], "ROWTYPE") == "Z_ORDER_ID"
    assert _get_field_text(records[header[1][0]].payload, nametabs["DD40L"], "TTYPKIND") == "T"
    assert _get_field_text(records[text_rows[1][0]].payload, nametabs["DD40T"], "DDTEXT") == "Order ID table"

    object_keys = [u16(record.payload) for record in records if record.rtype == "C"]
    assert len(object_keys) == 1
    assert "TTYP" in object_keys[0]
    assert "ZTT_ORDER_ID" in object_keys[0]


def test_ttyp_helpers_are_compatibly_reexported() -> None:
    assert _apply_ttyp_row is apply_ttyp_row
    assert _fix_ttyp_ddlanguage_key is fix_ttyp_ddlanguage_key
