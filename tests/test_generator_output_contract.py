"""End-to-end contracts for generated multi-object transports."""

import pytest
from abapgit_to_transport import collect_sources, generate_transport_multi
from sap_transport_records import iter_records, u16
from sap_transport_writer import decompress_container, parse_container
from test_transport import verify

pytestmark = pytest.mark.templates


def test_multi_object_generation_is_deterministic_and_structurally_valid(
    tmp_path,
) -> None:
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    (source_dir / "z_alpha.prog.abap").write_text("REPORT z_alpha.", encoding="utf-8")
    (source_dir / "z_beta.intf.abap").write_text(
        "INTERFACE z_beta.\nENDINTERFACE.", encoding="utf-8"
    )

    objects = [
        ("PROG", "Z_ALPHA", collect_sources(source_dir, "PROG", "Z_ALPHA"), ""),
        ("INTF", "Z_BETA", collect_sources(source_dir, "INTF", "Z_BETA"), ""),
    ]
    first_data, first_cofile = generate_transport_multi(
        objects, "DEVK900999", sid="DEV", package="ZREFAC"
    )
    second_data, second_cofile = generate_transport_multi(
        objects, "DEVK900999", sid="DEV", package="ZREFAC"
    )

    assert first_data == second_data
    assert first_cofile == second_cofile

    data_file = tmp_path / "R900999.DEV"
    cofile_file = tmp_path / "K900999.DEV"
    data_file.write_bytes(first_data)
    cofile_file.write_bytes(first_cofile)
    assert verify(data_file, "DEVK900999", "ZREFAC") == []

    records = iter_records(decompress_container(parse_container(first_data)))
    object_keys = [u16(record.payload) for record in records if record.rtype == "C"]
    assert len(object_keys) == 2
    assert any("Z_ALPHA" in key for key in object_keys)
    assert any("Z_BETA" in key for key in object_keys)
