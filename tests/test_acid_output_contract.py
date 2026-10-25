"""End-to-end characterization of generated checkpoint-group transports."""

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


def test_checkpoint_group_generation_preserves_description(tmp_path) -> None:
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    (source_dir / "z_orders.acid.xml").write_text(
        "<abapGit><DESCRIPTION>Order processing checkpoints</DESCRIPTION></abapGit>",
        encoding="utf-8",
    )

    sources = collect_sources(source_dir, "ACID", "Z_ORDERS")
    first_data, first_cofile = generate_transport(
        "ACID", "Z_ORDERS", sources, "DEVK901004", sid="DEV", package="ZACID"
    )
    second_data, second_cofile = generate_transport(
        "ACID", "Z_ORDERS", sources, "DEVK901004", sid="DEV", package="ZACID"
    )

    assert first_data == second_data
    assert first_cofile == second_cofile

    data_file = tmp_path / "R901004.DEV"
    cofile_file = tmp_path / "K901004.DEV"
    data_file.write_bytes(first_data)
    cofile_file.write_bytes(first_cofile)
    assert verify(data_file, "DEVK901004", "ZACID") == []

    records = iter_records(decompress_container(parse_container(first_data)))
    fields = _parse_nametabs(records)["AAB_ID_PROPT"]
    block = _find_block_by_action(records, "AAB_ID_PROPT", "00REPC")
    assert block is not None
    assert block[1]
    descriptions = [
        _get_field_text(records[index].payload, fields, "DESCRIPT")
        for index in block[1]
    ]
    assert descriptions == ["Order processing checkpoints"] * len(descriptions)

    object_keys = [u16(record.payload) for record in records if record.rtype == "C"]
    assert len(object_keys) == 1
    assert "ACID" in object_keys[0]
    assert "Z_ORDERS" in object_keys[0]
