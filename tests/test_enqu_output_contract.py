"""End-to-end characterization of generated lock-object transports."""

import pytest
from abapgit_to_transport import (
    _find_block_by_action,
    _get_field_text,
    _parse_nametabs,
    _regenerate_enqu_rows,
    collect_sources,
    generate_transport,
)
from sap_transport_records import iter_records, u16
from transport_regenerators.ddic import regenerate_enqu_rows
from sap_transport_writer import decompress_container, parse_container
from test_transport import verify


@pytest.mark.templates
def test_lock_object_generation_preserves_header_tables_and_fields(tmp_path) -> None:
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    (source_dir / "z_order_lock.enqu.xml").write_text(
        "<abapGit>"
        "<DD25V><VIEWNAME>Z_ORDER_LOCK</VIEWNAME><DDLANGUAGE>E</DDLANGUAGE>"
        "<AGGTYPE>E</AGGTYPE><ROOTTAB>ZORDERS</ROOTTAB>"
        "<DDTEXT>Order lock</DDTEXT></DD25V>"
        "<DD26E_TABLE>"
        "<DD26E><TABNAME>ZORDERS</TABNAME><TABPOS>0001</TABPOS>"
        "<ENQMODE>E</ENQMODE></DD26E>"
        "</DD26E_TABLE>"
        "<DD27P_TABLE>"
        "<DD27P><VIEWFIELD>ORDER_ID</VIEWFIELD><TABNAME>ZORDERS</TABNAME>"
        "<FIELDNAME>ORDER_ID</FIELDNAME><KEYFLAG>X</KEYFLAG>"
        "<ENQMODE>E</ENQMODE></DD27P>"
        "<DD27P><VIEWFIELD>ORDER_ID</VIEWFIELD><TABNAME>ZORDERS</TABNAME>"
        "<FIELDNAME>*</FIELDNAME><ENQMODE>E</ENQMODE></DD27P>"
        "</DD27P_TABLE></abapGit>",
        encoding="utf-8",
    )

    sources = collect_sources(source_dir, "ENQU", "Z_ORDER_LOCK")
    first_data, first_cofile = generate_transport(
        "ENQU", "Z_ORDER_LOCK", sources, "DEVK901008", sid="DEV", package="ZENQU"
    )
    second_data, second_cofile = generate_transport(
        "ENQU", "Z_ORDER_LOCK", sources, "DEVK901008", sid="DEV", package="ZENQU"
    )

    assert first_data == second_data
    assert first_cofile == second_cofile

    data_file = tmp_path / "R901008.DEV"
    cofile_file = tmp_path / "K901008.DEV"
    data_file.write_bytes(first_data)
    cofile_file.write_bytes(first_cofile)
    assert verify(data_file, "DEVK901008", "ZENQU") == []

    records = iter_records(decompress_container(parse_container(first_data)))
    nametabs = _parse_nametabs(records)
    header = _find_block_by_action(records, "DD25L", "00REP ")
    text_rows = _find_block_by_action(records, "DD25T", "00REP ")
    tables = _find_block_by_action(records, "DD26S", "00REP ")
    fields = _find_block_by_action(records, "DD27S", "00REP ")
    assert header is not None and text_rows is not None
    assert tables is not None and fields is not None
    assert _get_field_text(records[header[1][0]].payload, nametabs["DD25L"], "AGGTYPE") == "E"
    assert _get_field_text(records[header[1][0]].payload, nametabs["DD25L"], "ROOTTAB") == "ZORDERS"
    assert _get_field_text(records[text_rows[1][0]].payload, nametabs["DD25T"], "DDTEXT") == "Order lock"
    assert len(tables[1]) == 1
    assert [
        _get_field_text(records[index].payload, nametabs["DD26S"], "TABNAME")
        for index in tables[1]
    ] == ["ZORDERS"]
    assert len(fields[1]) == 2
    assert [
        _get_field_text(records[index].payload, nametabs["DD27S"], "FIELDNAME")
        for index in fields[1]
    ] == ["ORDER_ID", "*"]
    assert [
        _get_field_text(records[index].payload, nametabs["DD27S"], "ENQMODE")
        for index in fields[1]
    ] == ["", "E"]  # Native DD27S stores lock mode on the '*' table row.

    object_keys = [u16(record.payload) for record in records if record.rtype == "C"]
    assert len(object_keys) == 1
    assert "ENQU" in object_keys[0]
    assert "Z_ORDER_LOCK" in object_keys[0]


def test_enqu_regenerator_is_compatibly_reexported() -> None:
    assert _regenerate_enqu_rows is regenerate_enqu_rows
