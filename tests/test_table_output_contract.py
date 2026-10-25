"""End-to-end characterization of generated transparent-table transports."""

import pytest
from abapgit_to_transport import _find_block, collect_sources, generate_transport
from sap_transport_records import iter_records, u16
from sap_transport_writer import decompress_container, parse_container
from test_transport import verify

pytestmark = pytest.mark.templates


def test_transparent_table_generation_is_deterministic_and_structurally_valid(
    tmp_path,
) -> None:
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    (source_dir / "z_orders.tabl.xml").write_text(
        "<abapGit>"
        "<DD02V><TABNAME>Z_ORDERS</TABNAME><DDLANGUAGE>E</DDLANGUAGE>"
        "<TABCLASS>TRANSP</TABCLASS><DDTEXT>Orders</DDTEXT><CLIDEP>X</CLIDEP>"
        "</DD02V>"
        "<DD09L><TABNAME>Z_ORDERS</TABNAME><AS4LOCAL>A</AS4LOCAL>"
        "<TABKAT>0</TABKAT><TABART>APPL0</TABART><BUFALLOW>X</BUFALLOW>"
        "</DD09L>"
        "<DD03P_TABLE>"
        "<DD03P><FIELDNAME>MANDT</FIELDNAME><KEYFLAG>X</KEYFLAG>"
        "<ROLLNAME>MANDT</ROLLNAME><INTTYPE>C</INTTYPE><INTLEN>6</INTLEN>"
        "</DD03P>"
        "<DD03P><FIELDNAME>ORDER_ID</FIELDNAME><KEYFLAG>X</KEYFLAG>"
        "<ROLLNAME>CHAR10</ROLLNAME><INTTYPE>C</INTTYPE><INTLEN>20</INTLEN>"
        "</DD03P>"
        "</DD03P_TABLE>"
        "</abapGit>",
        encoding="utf-8",
    )

    sources = collect_sources(source_dir, "TABL", "Z_ORDERS")
    first_data, first_cofile = generate_transport(
        "TABL", "Z_ORDERS", sources, "DEVK901002", sid="DEV", package="ZDDIC"
    )
    second_data, second_cofile = generate_transport(
        "TABL", "Z_ORDERS", sources, "DEVK901002", sid="DEV", package="ZDDIC"
    )

    assert first_data == second_data
    assert first_cofile == second_cofile

    data_file = tmp_path / "R901002.DEV"
    cofile_file = tmp_path / "K901002.DEV"
    data_file.write_bytes(first_data)
    cofile_file.write_bytes(first_cofile)
    assert verify(data_file, "DEVK901002", "ZDDIC") == []

    records = iter_records(decompress_container(parse_container(first_data)))
    assert _find_block(records, "DD02L") is not None
    assert _find_block(records, "DD02T") is not None
    assert _find_block(records, "DD03L") is not None
    assert _find_block(records, "DD09L") is not None

    object_keys = [u16(record.payload) for record in records if record.rtype == "C"]
    assert len(object_keys) == 1
    assert "TABL" in object_keys[0]
    assert "Z_ORDERS" in object_keys[0]

    text = "\n".join(u16(record.payload) for record in records)
    assert "Z_ORDERS" in text
    assert "Orders" in text
    assert "ORDER_ID" in text
