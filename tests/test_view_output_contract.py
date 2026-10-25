"""End-to-end characterization of generated database-view transports."""

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


def test_database_view_generation_preserves_header_tables_and_fields(tmp_path) -> None:
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    (source_dir / "z_order_view.view.xml").write_text(
        "<abapGit>"
        "<DD25V><VIEWNAME>Z_ORDER_VIEW</VIEWNAME><DDLANGUAGE>E</DDLANGUAGE>"
        "<AGGTYPE>V</AGGTYPE><APPLCLASS>SD</APPLCLASS><ROOTTAB>ZORDERS</ROOTTAB>"
        "<DDTEXT>Order view</DDTEXT><VIEWCLASS>C</VIEWCLASS></DD25V>"
        "<DD26V_TABLE>"
        "<DD26V><TABNAME>ZORDERS</TABNAME><TABPOS>0001</TABPOS></DD26V>"
        "<DD26V><TABNAME>ZORDERITEM</TABNAME><TABPOS>0002</TABPOS>"
        "<FORTABNAME>ZORDERS</FORTABNAME><FORFIELD>ORDER_ID</FORFIELD><FORDIR>1</FORDIR>"
        "</DD26V></DD26V_TABLE>"
        "<DD27P_TABLE>"
        "<DD27P><VIEWFIELD>ORDER_ID</VIEWFIELD><TABNAME>ZORDERS</TABNAME>"
        "<FIELDNAME>ORDER_ID</FIELDNAME><KEYFLAG>X</KEYFLAG></DD27P>"
        "<DD27P><VIEWFIELD>ITEM_ID</VIEWFIELD><TABNAME>ZORDERITEM</TABNAME>"
        "<FIELDNAME>ITEM_ID</FIELDNAME></DD27P>"
        "</DD27P_TABLE></abapGit>",
        encoding="utf-8",
    )

    sources = collect_sources(source_dir, "VIEW", "Z_ORDER_VIEW")
    first_data, first_cofile = generate_transport(
        "VIEW", "Z_ORDER_VIEW", sources, "DEVK901007", sid="DEV", package="ZVIEW"
    )
    second_data, second_cofile = generate_transport(
        "VIEW", "Z_ORDER_VIEW", sources, "DEVK901007", sid="DEV", package="ZVIEW"
    )

    assert first_data == second_data
    assert first_cofile == second_cofile

    data_file = tmp_path / "R901007.DEV"
    cofile_file = tmp_path / "K901007.DEV"
    data_file.write_bytes(first_data)
    cofile_file.write_bytes(first_cofile)
    assert verify(data_file, "DEVK901007", "ZVIEW") == []

    records = iter_records(decompress_container(parse_container(first_data)))
    nametabs = _parse_nametabs(records)
    header = _find_block_by_action(records, "DD25L", "00REP ")
    text_rows = _find_block_by_action(records, "DD25T", "00REP ")
    tables = _find_block_by_action(records, "DD26S", "00REP ")
    fields = _find_block_by_action(records, "DD27S", "00REP ")
    assert header is not None and text_rows is not None
    assert tables is not None and fields is not None
    assert _get_field_text(records[header[1][0]].payload, nametabs["DD25L"], "ROOTTAB") == "ZORDERS"
    assert _get_field_text(records[text_rows[1][0]].payload, nametabs["DD25T"], "DDTEXT") == "Order view"
    assert len(tables[1]) == 2
    assert [
        _get_field_text(records[index].payload, nametabs["DD26S"], "TABNAME")
        for index in tables[1]
    ] == ["ZORDERS", "ZORDERITEM"]
    assert len(fields[1]) == 2
    assert [
        _get_field_text(records[index].payload, nametabs["DD27S"], "VIEWFIELD")
        for index in fields[1]
    ] == ["ORDER_ID", "ITEM_ID"]

    object_keys = [u16(record.payload) for record in records if record.rtype == "C"]
    assert len(object_keys) == 1
    assert "VIEW" in object_keys[0]
    assert "Z_ORDER_VIEW" in object_keys[0]
