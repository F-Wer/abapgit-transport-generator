"""End-to-end characterization of generated domain transports."""

import pytest
from abapgit_to_transport import (
    _find_block_by_action,
    _get_field_text,
    _parse_nametabs,
    _regenerate_doma_rows,
    collect_sources,
    generate_transport,
)
from sap_transport_records import iter_records, u16
from transport_regenerators.ddic import regenerate_doma_rows
from sap_transport_writer import decompress_container, parse_container
from test_transport import verify


@pytest.mark.templates
def test_domain_generation_preserves_header_values_and_texts(tmp_path) -> None:
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    (source_dir / "z_order_status.doma.xml").write_text(
        "<abapGit>"
        "<DD01V><DOMNAME>Z_ORDER_STATUS</DOMNAME><DDLANGUAGE>E</DDLANGUAGE>"
        "<DATATYPE>CHAR</DATATYPE><LENG>2</LENG><OUTPUTLEN>2</OUTPUTLEN>"
        "<DECIMALS>0</DECIMALS><VALEXI>X</VALEXI><DDTEXT>Order status</DDTEXT>"
        "</DD01V>"
        "<DD07V_TAB>"
        "<DD07V><DOMNAME>Z_ORDER_STATUS</DOMNAME><VALPOS>0001</VALPOS>"
        "<DOMVALUE_L>OP</DOMVALUE_L><DDLANGUAGE>E</DDLANGUAGE>"
        "<DDTEXT>Open</DDTEXT></DD07V>"
        "<DD07V><DOMNAME>Z_ORDER_STATUS</DOMNAME><VALPOS>0002</VALPOS>"
        "<DOMVALUE_L>CL</DOMVALUE_L><DDLANGUAGE>E</DDLANGUAGE>"
        "<DDTEXT>Closed</DDTEXT></DD07V>"
        "</DD07V_TAB></abapGit>",
        encoding="utf-8",
    )

    sources = collect_sources(source_dir, "DOMA", "Z_ORDER_STATUS")
    first_data, first_cofile = generate_transport(
        "DOMA", "Z_ORDER_STATUS", sources, "DEVK901009", sid="DEV", package="ZDOMA"
    )
    second_data, second_cofile = generate_transport(
        "DOMA", "Z_ORDER_STATUS", sources, "DEVK901009", sid="DEV", package="ZDOMA"
    )

    assert first_data == second_data
    assert first_cofile == second_cofile

    data_file = tmp_path / "R901009.DEV"
    cofile_file = tmp_path / "K901009.DEV"
    data_file.write_bytes(first_data)
    cofile_file.write_bytes(first_cofile)
    assert verify(data_file, "DEVK901009", "ZDOMA") == []

    records = iter_records(decompress_container(parse_container(first_data)))
    nametabs = _parse_nametabs(records)
    header = _find_block_by_action(records, "DD01L", "00REP ")
    text_rows = _find_block_by_action(records, "DD01T", "00REP ")
    values = _find_block_by_action(records, "DD07L", "00REP ")
    value_texts = _find_block_by_action(records, "DD07T", "00REP ")
    assert header is not None and text_rows is not None
    assert values is not None and value_texts is not None
    assert _get_field_text(records[header[1][0]].payload, nametabs["DD01L"], "DATATYPE") == "CHAR"
    assert _get_field_text(records[header[1][0]].payload, nametabs["DD01L"], "VALEXI") == "X"
    assert _get_field_text(records[text_rows[1][0]].payload, nametabs["DD01T"], "DDTEXT") == "Order status"
    assert [
        _get_field_text(records[index].payload, nametabs["DD07L"], "DOMVALUE_L")
        for index in values[1]
    ] == ["OP", "CL"]
    assert [
        _get_field_text(records[index].payload, nametabs["DD07T"], "DDTEXT")
        for index in value_texts[1]
    ] == ["Open", "Closed"]

    object_keys = [u16(record.payload) for record in records if record.rtype == "C"]
    assert len(object_keys) == 1
    assert "DOMA" in object_keys[0]
    assert "Z_ORDER_STATUS" in object_keys[0]


def test_doma_regenerator_is_compatibly_reexported() -> None:
    assert _regenerate_doma_rows is regenerate_doma_rows
