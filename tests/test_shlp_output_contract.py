"""End-to-end characterization of generated search-help transports."""

import pytest
from abapgit_to_transport import (
    _find_block_by_action,
    _get_field_text,
    _parse_nametabs,
    _regenerate_shlp_rows,
    collect_sources,
    generate_transport,
)
from sap_transport_records import iter_records, u16
from transport_regenerators.ddic import regenerate_shlp_rows
from sap_transport_writer import decompress_container, parse_container
from test_transport import verify


@pytest.mark.templates
def test_elementary_search_help_generation_preserves_metadata_and_mappings(tmp_path) -> None:
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    (source_dir / "z_order_help.shlp.xml").write_text(
        "<abapGit>"
        "<DD30V><SHLPNAME>Z_ORDER_HELP</SHLPNAME><DDLANGUAGE>E</DDLANGUAGE>"
        "<ISSIMPLE>X</ISSIMPLE><SELMETHOD>ZORDERS</SELMETHOD>"
        "<DDTEXT>Order help</DDTEXT></DD30V>"
        "<DD32P_TABLE>"
        "<DD32P><SHLPNAME>Z_ORDER_HELP</SHLPNAME><FIELDNAME>ORDER_ID</FIELDNAME>"
        "<ROLLNAME>Z_ORDER_ID</ROLLNAME><SHLPINPUT>X</SHLPINPUT>"
        "<SHLPOUTPUT>X</SHLPOUTPUT></DD32P>"
        "<DD32P><SHLPNAME>Z_ORDER_HELP</SHLPNAME><FIELDNAME>ORDER_TYPE</FIELDNAME>"
        "<ROLLNAME>Z_ORDER_TYPE</ROLLNAME><SHLPINPUT>X</SHLPINPUT>"
        "</DD32P>"
        "</DD32P_TABLE></abapGit>",
        encoding="utf-8",
    )

    sources = collect_sources(source_dir, "SHLP", "Z_ORDER_HELP")
    first_data, first_cofile = generate_transport(
        "SHLP", "Z_ORDER_HELP", sources, "DEVK901010", sid="DEV", package="ZSHLP"
    )
    second_data, second_cofile = generate_transport(
        "SHLP", "Z_ORDER_HELP", sources, "DEVK901010", sid="DEV", package="ZSHLP"
    )

    assert first_data == second_data
    assert first_cofile == second_cofile

    data_file = tmp_path / "R901010.DEV"
    cofile_file = tmp_path / "K901010.DEV"
    data_file.write_bytes(first_data)
    cofile_file.write_bytes(first_cofile)
    assert verify(data_file, "DEVK901010", "ZSHLP") == []

    records = iter_records(decompress_container(parse_container(first_data)))
    nametabs = _parse_nametabs(records)
    header = _find_block_by_action(records, "DD30L", "00REP ")
    text_rows = _find_block_by_action(records, "DD30T", "00REP ")
    fields = _find_block_by_action(records, "DD32S", "00REP ")
    subhelps = _find_block_by_action(records, "DD31S", "00REP ")
    mappings = _find_block_by_action(records, "DD33S", "00REP ")
    assert header is not None and text_rows is not None
    assert fields is not None and subhelps is not None and mappings is not None
    assert _get_field_text(records[header[1][0]].payload, nametabs["DD30L"], "SELMETHOD") == "ZORDERS"
    assert _get_field_text(records[text_rows[1][0]].payload, nametabs["DD30T"], "DDTEXT") == "Order help"
    assert [
        _get_field_text(records[index].payload, nametabs["DD32S"], "FIELDNAME")
        for index in fields[1]
    ] == ["ORDER_ID", "ORDER_TYPE"]
    assert [
        _get_field_text(records[index].payload, nametabs["DD31S"], "SUBSHLP")
        for index in subhelps[1]
    ] == ["Z_ORDER_HELP"]
    assert [
        _get_field_text(records[index].payload, nametabs["DD33S"], "FIELDNAME")
        for index in mappings[1]
    ] == ["ORDER_ID", "ORDER_TYPE"]

    object_keys = [u16(record.payload) for record in records if record.rtype == "C"]
    assert len(object_keys) == 1
    assert "SHLP" in object_keys[0]
    assert "Z_ORDER_HELP" in object_keys[0]


def test_shlp_regenerator_is_compatibly_reexported() -> None:
    assert _regenerate_shlp_rows is regenerate_shlp_rows
