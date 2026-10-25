"""End-to-end characterization of generated DDIC transports."""

import pytest
from abapgit_to_transport import (
    _find_block,
    collect_sources,
    generate_transport,
)
from sap_transport_records import iter_records, u16
from sap_transport_writer import decompress_container, parse_container
from test_transport import verify

pytestmark = pytest.mark.templates


def test_data_element_generation_is_deterministic_and_structurally_valid(
    tmp_path,
) -> None:
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    (source_dir / "z_order_id.dtel.xml").write_text(
        "<abapGit><DD04V>"
        "<ROLLNAME>Z_ORDER_ID</ROLLNAME>"
        "<DDLANGUAGE>E</DDLANGUAGE>"
        "<REFKIND>E</REFKIND>"
        "<DATATYPE>CHAR</DATATYPE>"
        "<LENG>000010</LENG>"
        "<DECIMALS>000000</DECIMALS>"
        "<OUTPUTLEN>000010</OUTPUTLEN>"
        "<DDTEXT>Order ID</DDTEXT>"
        "<REPTEXT>Order identifier</REPTEXT>"
        "<SCRTEXT_S>Order</SCRTEXT_S>"
        "<SCRTEXT_M>Order ID</SCRTEXT_M>"
        "<SCRTEXT_L>Order identifier</SCRTEXT_L>"
        "</DD04V></abapGit>",
        encoding="utf-8",
    )

    sources = collect_sources(source_dir, "DTEL", "Z_ORDER_ID")
    first_data, first_cofile = generate_transport(
        "DTEL", "Z_ORDER_ID", sources, "DEVK901001", sid="DEV", package="ZDDIC"
    )
    second_data, second_cofile = generate_transport(
        "DTEL", "Z_ORDER_ID", sources, "DEVK901001", sid="DEV", package="ZDDIC"
    )

    assert first_data == second_data
    assert first_cofile == second_cofile

    data_file = tmp_path / "R901001.DEV"
    cofile_file = tmp_path / "K901001.DEV"
    data_file.write_bytes(first_data)
    cofile_file.write_bytes(first_cofile)
    assert verify(data_file, "DEVK901001", "ZDDIC") == []

    records = iter_records(decompress_container(parse_container(first_data)))
    assert _find_block(records, "DD04L") is not None
    assert _find_block(records, "DD04T") is not None

    object_keys = [u16(record.payload) for record in records if record.rtype == "C"]
    assert len(object_keys) == 1
    assert "DTEL" in object_keys[0]
    assert "Z_ORDER_ID" in object_keys[0]

    text = "\n".join(u16(record.payload) for record in records)
    assert "Z_ORDER_ID" in text
    assert "Order ID" in text
