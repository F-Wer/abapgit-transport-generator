"""End-to-end characterization of generated application-log transports."""

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


def test_application_log_generation_preserves_arbitrary_object_rows(tmp_path) -> None:
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    (source_dir / "z_order_log.aplo.xml").write_text(
        "<abapGit><APLO>"
        "<BALOBJ><OBJECT>Z_ORDER_LOG</OBJECT></BALOBJ>"
        "<BALOBJ><OBJECT>Z_ORDER_AUDIT</OBJECT></BALOBJ>"
        "</APLO></abapGit>",
        encoding="utf-8",
    )

    sources = collect_sources(source_dir, "APLO", "Z_ORDER_LOG")
    first_data, first_cofile = generate_transport(
        "APLO", "Z_ORDER_LOG", sources, "DEVK901006", sid="DEV", package="ZAPLO"
    )
    second_data, second_cofile = generate_transport(
        "APLO", "Z_ORDER_LOG", sources, "DEVK901006", sid="DEV", package="ZAPLO"
    )

    assert first_data == second_data
    assert first_cofile == second_cofile

    data_file = tmp_path / "R901006.DEV"
    cofile_file = tmp_path / "K901006.DEV"
    data_file.write_bytes(first_data)
    cofile_file.write_bytes(first_cofile)
    assert verify(data_file, "DEVK901006", "ZAPLO") == []

    records = iter_records(decompress_container(parse_container(first_data)))
    nametabs = _parse_nametabs(records)
    objects = _find_block_by_action(records, "BALOBJ", "00REPC")
    if objects is None:
        objects = _find_block_by_action(records, "BALOBJ", "00REP ")
    assert objects is not None
    assert len(objects[1]) == 2
    assert [
        _get_field_text(records[index].payload, nametabs["BALOBJ"], "OBJECT")
        for index in objects[1]
    ] == ["Z_ORDER_LOG", "Z_ORDER_AUDIT"]
    object_keys = [u16(record.payload) for record in records if record.rtype == "C"]
    assert len(object_keys) == 1
    assert "APLO" in object_keys[0]
    assert "Z_ORDER_LOG" in object_keys[0]
