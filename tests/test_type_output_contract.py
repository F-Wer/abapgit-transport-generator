"""End-to-end characterization of generated type-group transports."""

import pytest
from abapgit_to_transport import (
    _apply_type_row,
    _find_block,
    _fix_type_ddlanguage_key,
    _get_field_text,
    _make_type_pool_boilerplate,
    _parse_nametabs,
    collect_sources,
    generate_transport,
)
from sap_transport_records import iter_records, u16
from transport_regenerators.type_groups import (
    apply_type_row,
    fix_type_ddlanguage_key,
    make_type_pool_boilerplate,
)
from sap_transport_writer import decompress_container, parse_container
from test_transport import verify


@pytest.mark.templates
def test_type_group_generation_preserves_boilerplate_body_and_catalog_text(tmp_path) -> None:
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    (source_dir / "zordr.type.xml").write_text(
        "<abapGit><DDTEXT>Order type group</DDTEXT></abapGit>",
        encoding="utf-8",
    )
    (source_dir / "zordr.type.abap").write_text(
        "TYPES zorder_id TYPE c LENGTH 10.\nCONSTANTS zorder_kind TYPE c VALUE 'O'.",
        encoding="utf-8",
    )

    sources = collect_sources(source_dir, "TYPE", "ZORDR")
    first_data, first_cofile = generate_transport(
        "TYPE", "ZORDR", sources, "DEVK901016", sid="DEV", package="ZTYPE"
    )
    second_data, second_cofile = generate_transport(
        "TYPE", "ZORDR", sources, "DEVK901016", sid="DEV", package="ZTYPE"
    )

    assert first_data == second_data
    assert first_cofile == second_cofile

    data_file = tmp_path / "R901016.DEV"
    cofile_file = tmp_path / "K901016.DEV"
    data_file.write_bytes(first_data)
    cofile_file.write_bytes(first_cofile)
    assert verify(data_file, "DEVK901016", "ZTYPE") == []

    records = iter_records(decompress_container(parse_container(first_data)))
    nametabs = _parse_nametabs(records)
    catalog = _find_block(records, "DDTYPET")
    assert catalog is not None
    assert _get_field_text(records[catalog[1][0]].payload, nametabs["DDTYPET"], "TYPEGROUP") == "ZORDR"
    assert _get_field_text(records[catalog[1][0]].payload, nametabs["DDTYPET"], "DDLANGUAGE") == "D"
    assert _get_field_text(records[catalog[1][0]].payload, nametabs["DDTYPET"], "DDTEXT") == "Order type group"

    text = "\n".join(u16(record.payload) for record in records)
    assert "TYPE-POOL ZORDR ." in text
    assert "TYPES zorder_id TYPE c LENGTH 10." in text
    assert "CONSTANTS zorder_kind TYPE c VALUE 'O'." in text



def test_type_group_helpers_remain_compatibly_reexported() -> None:
    assert _apply_type_row is apply_type_row
    assert _fix_type_ddlanguage_key is fix_type_ddlanguage_key
    assert _make_type_pool_boilerplate is make_type_pool_boilerplate
