"""End-to-end characterization of generated ENHO transports."""

import pytest
from abapgit_to_transport import (
    _make_enho_master_include_source,
    _regenerate_enho_badi_data_blob,
    _regenerate_enho_data_blob,
    collect_sources,
    generate_transport,
)
from sap_transport_records import iter_records, u16
from transport_regenerators.enhancements import (
    make_enho_master_include_source,
    regenerate_enho_badi_data_blob,
    regenerate_enho_data_blob,
)
from sap_transport_writer import decompress_container, parse_container
from test_transport import verify
from transport_templates import template_name


@pytest.mark.templates
def test_class_enhancement_generation_preserves_source_and_binary_metadata(tmp_path) -> None:
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    (source_dir / "zenh_order.enho.xml").write_text(
        "<abapGit><TOOL>CLASENH</TOOL><SHORTTEXT>Order enhancement</SHORTTEXT>"
        "<CLASS>ZCL_ORDER</CLASS><TAB_METHODS><ENHNEWMETH_DATA>"
        "<METH_HEADER><CMPNAME>CHECK_ORDER</CMPNAME><DESCRIPT>Check order</DESCRIPT>"
        "<EXPOSURE>2</EXPOSURE><STATE>1</STATE><EDITORDER>1</EDITORDER>"
        "<MTDDECLTYP>0</MTDDECLTYP></METH_HEADER><METH_PARAM>"
        "<ENHMETHPARAM><SCONAME>IV_ORDER</SCONAME><DESCRIPT>Order key</DESCRIPT>"
        "<EDITORDER>1</EDITORDER><PARPASSTYP>1</PARPASSTYP><TYPTYPE>1</TYPTYPE>"
        "<TYPE>CHAR10</TYPE></ENHMETHPARAM></METH_PARAM>"
        "</ENHNEWMETH_DATA></TAB_METHODS></abapGit>",
        encoding="utf-8",
    )
    (source_dir / "zenh_order.enho.em_check_order.abap").write_text(
        "METHOD check_order.\nENDMETHOD.", encoding="utf-8"
    )

    sources = collect_sources(source_dir, "ENHO", "ZENH_ORDER")
    first_data, first_cofile = generate_transport(
        "ENHO", "ZENH_ORDER", sources, "DEVK901017", sid="DEV", package="ZENHO"
    )
    second_data, second_cofile = generate_transport(
        "ENHO", "ZENH_ORDER", sources, "DEVK901017", sid="DEV", package="ZENHO"
    )
    assert first_data == second_data
    assert first_cofile == second_cofile

    data_file = tmp_path / "R901017.DEV"
    cofile_file = tmp_path / "K901017.DEV"
    data_file.write_bytes(first_data)
    cofile_file.write_bytes(first_cofile)
    # The known defect that keeps ENHO unregistered: the enhancement stays
    # attached to the template's class. The verifier must flag it.
    template_class = template_name("ENHO", "class")
    assert verify(data_file, "DEVK901017", "ZENHO") == [
        f"template leftover: {template_class}"]

    records = iter_records(decompress_container(parse_container(first_data)))
    stream = b"".join(record.payload for record in records)
    for value in ("ZENH_ORDER", "ZCL_ORDER", "CHECK_ORDER", "IV_ORDER", "CHAR10"):
        assert value.encode("utf-16-le") in stream
    text = "\n".join(u16(record.payload) for record in records)
    assert "METHOD check_order." in text
    assert "class-methods CHECK_ORDER" in text
    object_keys = [u16(record.payload) for record in records if record.rtype == "C"]
    assert len(object_keys) == 1
    assert "ENHO" in object_keys[0] and "ZENH_ORDER" in object_keys[0]


def test_enho_helpers_remain_compatibly_reexported() -> None:
    assert _make_enho_master_include_source is make_enho_master_include_source
    assert _regenerate_enho_data_blob is regenerate_enho_data_blob
    assert _regenerate_enho_badi_data_blob is regenerate_enho_badi_data_blob
