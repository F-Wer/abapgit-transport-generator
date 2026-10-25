"""Characterization of the transport-engine orchestration boundary."""

import pytest
from abapgit_to_transport import (
    _derive_task,
    _load_template_records,
    _make_rule,
    _process_template_records,
    _serialize_records,
    collect_sources,
    generate_transport,
)
from transport_engine import OBJECT_REGENERATORS, process_template_records
from transport_native_support import _set_request_text, request_text
from transport_templates import TEMPLATES


@pytest.mark.templates
def test_template_processing_matches_the_public_single_object_transport(tmp_path) -> None:
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    (source_dir / "zengine.prog.abap").write_text(
        "REPORT zengine.\nWRITE: / 'engine contract'.", encoding="utf-8"
    )
    (source_dir / "zengine_top.prog.abap").write_text(
        "DATA gv_engine TYPE string.", encoding="utf-8"
    )

    obj_type = "PROG"
    obj_name = "ZENGINE"
    request = "DEVK901050"
    sources = collect_sources(source_dir, obj_type, obj_name)
    container, template_records = _load_template_records(obj_type)
    template = TEMPLATES[obj_type]
    task = _derive_task(request)
    rule = _make_rule(
        template,
        obj_name,
        request,
        new_task=task,
        old_task=_derive_task(template["request"]),
    )

    processed = _process_template_records(
        template_records, obj_type, obj_name, sources, rule, package="ZENGINE"
    )
    # Request finalization the public entry point adds after processing.
    _set_request_text(processed, request_text([obj_name]))
    direct_data = _serialize_records(processed, container)
    public_data, public_cofile = generate_transport(
        obj_type, obj_name, sources, request, sid="DEV", package="ZENGINE"
    )

    assert direct_data == public_data
    assert public_cofile
    assert [record.rtype for record in processed].count("H") >= 1
    assert any(
        record.rtype == " " and "engine contract".encode("utf-16-le") in record.payload
        for record in processed
    )


def test_template_processor_remains_compatibly_reexported() -> None:
    assert _process_template_records is process_template_records


def test_object_regenerator_registry_covers_the_extracted_object_families() -> None:
    assert {"MSAG", "TABL", "TRAN", "TOBJ", "ENHO", "VIEW", "DOMA", "ENQU", "SHLP", "XSLT", "SICF"} <= set(OBJECT_REGENERATORS)
