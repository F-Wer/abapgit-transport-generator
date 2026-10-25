"""End-to-end characterization of generated API-state transports."""

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


def test_api_state_generation_preserves_header_and_release_states(tmp_path) -> None:
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    (source_dir / "z_orders.apis.xml").write_text(
        "<abapGit><APIS>"
        "<OBJECT_ID>Z_ORDERS</OBJECT_ID><OBJECT_TYPE>ENHS</OBJECT_TYPE>"
        "<OBJECT_NAME>Z_ORDERS</OBJECT_NAME><API_VERSION>002</API_VERSION>"
        "<API_STATES>"
        "<ROW><OBJECT_ID>Z_ORDERS</OBJECT_ID><OBJECT_TYPE>ENHS</OBJECT_TYPE>"
        "<SUB_OBJECT_TYPE>BADI_DEF</SUB_OBJECT_TYPE>"
        "<SUB_OBJECT_NAME>Z_ORDERS</SUB_OBJECT_NAME>"
        "<COMPATIBILITY_CONTRACT>C2</COMPATIBILITY_CONTRACT>"
        "<OBJECT_NAME>Z_ORDERS</OBJECT_NAME>"
        "<RELEASE_STATE>RELEASED</RELEASE_STATE>"
        "<SOFTWARE_RELEASE_NAME>2025</SOFTWARE_RELEASE_NAME></ROW>"
        "<ROW><OBJECT_ID>Z_ORDERS</OBJECT_ID><OBJECT_TYPE>ENHS</OBJECT_TYPE>"
        "<SUB_OBJECT_TYPE>BADI_DEF</SUB_OBJECT_TYPE>"
        "<SUB_OBJECT_NAME>Z_ORDERS_SECOND</SUB_OBJECT_NAME>"
        "<COMPATIBILITY_CONTRACT>C3</COMPATIBILITY_CONTRACT>"
        "<OBJECT_NAME>Z_ORDERS</OBJECT_NAME>"
        "<RELEASE_STATE>DEPRECATED</RELEASE_STATE>"
        "<SOFTWARE_RELEASE_NAME>2026</SOFTWARE_RELEASE_NAME></ROW>"
        "</API_STATES></APIS></abapGit>",
        encoding="utf-8",
    )

    sources = collect_sources(source_dir, "APIS", "Z_ORDERS")
    first_data, first_cofile = generate_transport(
        "APIS", "Z_ORDERS", sources, "DEVK901005", sid="DEV", package="ZAPIS"
    )
    second_data, second_cofile = generate_transport(
        "APIS", "Z_ORDERS", sources, "DEVK901005", sid="DEV", package="ZAPIS"
    )

    assert first_data == second_data
    assert first_cofile == second_cofile

    data_file = tmp_path / "R901005.DEV"
    cofile_file = tmp_path / "K901005.DEV"
    data_file.write_bytes(first_data)
    cofile_file.write_bytes(first_cofile)
    assert verify(data_file, "DEVK901005", "ZAPIS") == []

    records = iter_records(decompress_container(parse_container(first_data)))
    nametabs = _parse_nametabs(records)
    header = _find_block_by_action(records, "ARS_W_API", "00REP ")
    states = _find_block_by_action(records, "ARS_W_API_STATE", "00REPC")
    assert header is not None and states is not None
    assert _get_field_text(records[header[1][0]].payload, nametabs["ARS_W_API"], "API_VERSION") == "002"
    assert len(states[1]) == 2
    assert [
        _get_field_text(records[index].payload, nametabs["ARS_W_API_STATE"], "RELEASE_STATE")
        for index in states[1]
    ] == ["RELEASED", "DEPRECATED"]
    assert [
        _get_field_text(records[index].payload, nametabs["ARS_W_API_STATE"], "SOFTWARE_RELEASE_NAME")
        for index in states[1]
    ] == ["2025", "2026"]

    object_keys = [u16(record.payload) for record in records if record.rtype == "C"]
    assert len(object_keys) == 1
    assert "APIS" in object_keys[0]
    assert "Z_ORDERS" in object_keys[0]
