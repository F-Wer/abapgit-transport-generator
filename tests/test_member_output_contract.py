"""Characterization of class/interface member parsing and SEO row serialization."""

from __future__ import annotations

import pytest
import struct

from abapgit_to_transport import (
    _find_block,
    _get_field_text,
    _parse_class_members,
    _parse_interface_members,
    _parse_nametabs,
    collect_sources,
    generate_transport,
)
from sap_transport_records import iter_records
from transport_members import (
    build_class_member_row,
    build_component_row,
    parse_class_members,
    parse_interface_members,
)
from sap_transport_writer import decompress_container, parse_container
from test_transport import verify


def _rows_for_table(records, table: str):
    block = _find_block(records, table)
    assert block is not None
    return [records[index] for index in block[1]]


def _field_values(records, nametabs, table: str, field: str) -> list[str]:
    fields = nametabs[table]
    assert any(name == field for name, *_ in fields)
    return [_get_field_text(row.payload, fields, field) for row in _rows_for_table(records, table)]


def _edit_orders(records, nametabs, table: str) -> list[int] | None:
    fields = nametabs[table]
    field = next((item for item in fields if item[0] == "EDITORDER"), None)
    if field is None:
        return None
    _, offset, width, _ = field
    assert width >= 4
    return [struct.unpack(">I", row.payload[offset:offset + 4])[0]
            for row in _rows_for_table(records, table)]


@pytest.mark.templates
def test_member_parsers_and_seo_rows_preserve_member_order_and_fields(tmp_path) -> None:
    source_dir = tmp_path / "src"
    source_dir.mkdir()

    interface_source = (
        "INTERFACE zif_members.\n"
        "  CONSTANTS gc_kind TYPE char1 VALUE 'A'.\n"
        "  METHODS run.\n"
        "ENDINTERFACE."
    )
    assert _parse_interface_members(interface_source) == [
        {"kind": "const", "name": "GC_KIND", "type": "CHAR1", "value": "A", "exposure": "2"},
        {"kind": "method", "name": "RUN", "mtddecltyp": "0", "mtdtype": "0", "exposure": "2"},
    ]
    (source_dir / "zif_members.intf.abap").write_text(interface_source, encoding="utf-8")

    class_definition = (
        "CLASS zcl_members DEFINITION.\n"
        "  PUBLIC SECTION.\n"
        "  METHODS run.\n"
        "  CONSTANTS gc_status TYPE char1 VALUE 'A'.\n"
        "  PROTECTED SECTION.\n"
        "  CLASS-METHODS factory.\n"
        "  PRIVATE SECTION.\n"
        "  METHODS constructor.\n"
        "ENDCLASS."
    )
    class_implementation = (
        "CLASS zcl_members IMPLEMENTATION.\n"
        "  METHOD run.\n"
        "  ENDMETHOD.\n"
        "  METHOD factory.\n"
        "  ENDMETHOD.\n"
        "  METHOD constructor.\n"
        "  ENDMETHOD.\n"
        "ENDCLASS."
    )
    class_source = class_definition + "\n" + class_implementation
    assert _parse_class_members(class_source) == [
        {"kind": "method", "name": "RUN", "mtddecltyp": "0", "mtdtype": "0", "exposure": "2"},
        {"kind": "const", "name": "GC_STATUS", "type": "CHAR1", "value": "A", "exposure": "2"},
        {"kind": "method", "name": "FACTORY", "mtddecltyp": "1", "mtdtype": "0", "exposure": "1"},
        {"kind": "method", "name": "CONSTRUCTOR", "mtddecltyp": "0", "mtdtype": "2", "exposure": "0"},
    ]
    (source_dir / "zcl_members.clas.abap").write_text(class_source, encoding="utf-8")

    cases = [
        ("INTF", "ZIF_MEMBERS", "DEVK901040", ["GC_KIND", "RUN"]),
        ("CLAS", "ZCL_MEMBERS", "DEVK901041", ["RUN", "GC_STATUS", "FACTORY", "CONSTRUCTOR"]),
    ]
    for obj_type, obj_name, request, expected_names in cases:
        sources = collect_sources(source_dir, obj_type, obj_name)
        data, _ = generate_transport(
            obj_type, obj_name, sources, request, sid="DEV", package="ZMEMBER"
        )
        data_file = tmp_path / f"R{request[-6:]}.DEV"
        data_file.write_bytes(data)
        assert verify(data_file, request, "ZMEMBER") == []

        records = iter_records(decompress_container(parse_container(data)))
        nametabs = _parse_nametabs(records)
        edit_order_tables = []
        for table in ("SEOCOMPO", "SEOCOMPODF", "SEOCOMPOTX"):
            assert _field_values(records, nametabs, table, "CMPNAME") == expected_names
            edit_orders = _edit_orders(records, nametabs, table)
            if edit_orders is not None:
                edit_order_tables.append(table)
                expected_edit_orders = (list(range(1, len(expected_names) + 1))
                                        if obj_type == "CLAS"
                                        else [1] * len(expected_names))
                assert edit_orders == expected_edit_orders
        assert edit_order_tables

        if obj_type == "INTF":
            assert _field_values(records, nametabs, "SEOCOMPO", "CMPTYPE") == ["0", "1"]
            assert _field_values(records, nametabs, "SEOCOMPODF", "ATTVALUE") == ["'A'", ""]
            assert _field_values(records, nametabs, "SEOCOMPODF", "TYPE") == ["CHAR1", ""]
        else:
            assert _field_values(records, nametabs, "SEOCOMPO", "CMPTYPE") == ["1", "0", "1", "1"]
            assert _field_values(records, nametabs, "SEOCOMPO", "MTDTYPE") == ["0", "0", "0", "2"]
            assert _field_values(records, nametabs, "SEOCOMPODF", "MTDDECLTYP") == ["0", "0", "1", "0"]
            assert _field_values(records, nametabs, "SEOCOMPODF", "EXPOSURE") == ["2", "2", "1", "0"]
            assert _field_values(records, nametabs, "SEOCOMPODF", "ATTVALUE") == ["", "'A'", "", ""]
            assert _field_values(records, nametabs, "SEOCOMPODF", "TYPE") == ["", "CHAR1", "", ""]


def test_member_helpers_remain_compatibly_reexported() -> None:
    from abapgit_to_transport import _build_class_member_row, _build_component_row

    assert _parse_interface_members is parse_interface_members
    assert _parse_class_members is parse_class_members
    assert _build_component_row is build_component_row
    assert _build_class_member_row is build_class_member_row
