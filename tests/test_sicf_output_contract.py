"""End-to-end characterization of generated ICF-service transports."""

import pytest
from abapgit_to_transport import (
    _find_block,
    _get_field_text,
    _parse_nametabs,
    _regenerate_sicf_rows,
    collect_sources,
    generate_transport,
)
from sap_transport_records import iter_records, u16
from transport_regenerators.services import regenerate_sicf_rows
from sap_transport_writer import decompress_container, parse_container
from test_transport import verify


@pytest.mark.templates
def test_icf_service_generation_preserves_header_text_and_handlers(tmp_path) -> None:
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    obj_name = "Z_ORDER_SERVICE1234567890123456789012345"
    (source_dir / f"{obj_name.lower()}.sicf.xml").write_text(
        "<abapGit><URL>/sap/bc/z_order_service</URL>"
        "<ICFSERVICE><ICF_NAME>Z_ORDER_SERVICE</ICF_NAME>"
        "<ORIG_NAME>Z_ORDER_SERVICE</ORIG_NAME></ICFSERVICE>"
        "<ICFDOCU><ICF_LANGU>E</ICF_LANGU><ICF_DOCU>Order service</ICF_DOCU></ICFDOCU>"
        "<ICFHANDLER_TABLE>"
        "<ICFHANDLER><ICFORDER>1</ICFORDER><ICFTYP>H</ICFTYP>"
        "<ICFHANDLER>ZCL_ORDER_HTTP_HANDLER</ICFHANDLER></ICFHANDLER>"
        "</ICFHANDLER_TABLE></abapGit>",
        encoding="utf-8",
    )

    sources = collect_sources(source_dir, "SICF", obj_name)
    first_data, first_cofile = generate_transport(
        "SICF", obj_name, sources, "DEVK901011", sid="DEV", package="ZSICF"
    )
    second_data, second_cofile = generate_transport(
        "SICF", obj_name, sources, "DEVK901011", sid="DEV", package="ZSICF"
    )

    assert first_data == second_data
    assert first_cofile == second_cofile

    data_file = tmp_path / "R901011.DEV"
    cofile_file = tmp_path / "K901011.DEV"
    data_file.write_bytes(first_data)
    cofile_file.write_bytes(first_cofile)
    assert verify(data_file, "DEVK901011", "ZSICF") == []

    records = iter_records(decompress_container(parse_container(first_data)))
    nametabs = _parse_nametabs(records)
    service = _find_block(records, "ICFSERVICE")
    docu = _find_block(records, "ICFDOCU")
    handlers = _find_block(records, "ICFHANDLER")
    assert service is not None and docu is not None and handlers is not None
    assert _get_field_text(records[service[1][0]].payload, nametabs["ICFSERVICE"], "ICF_NAME") == "Z_ORDER_SERVICE"
    assert _get_field_text(records[docu[1][0]].payload, nametabs["ICFDOCU"], "ICF_DOCU") == "Order service"
    assert len(handlers[1]) == 1
    assert _get_field_text(records[handlers[1][0]].payload, nametabs["ICFHANDLER"], "ICFHANDLER") == "ZCL_ORDER_HTTP_HANDLER"

    object_keys = [u16(record.payload) for record in records if record.rtype == "C"]
    assert len(object_keys) == 1
    assert "SICF" in object_keys[0]
    assert obj_name in object_keys[0]


def test_sicf_regenerator_is_compatibly_reexported() -> None:
    assert _regenerate_sicf_rows is regenerate_sicf_rows
