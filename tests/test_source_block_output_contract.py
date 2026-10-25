"""Record-level characterization of REPOS source-block injection."""

import pytest
from abapgit_to_transport import (
    _build_repos_key,
    _class_pool_boilerplate,
    _encode_source_lines,
    _interface_pool_boilerplate,
    collect_sources,
    generate_transport,
)
from sap_transport_records import iter_records
from transport_source_blocks import (
    build_repos_key,
    class_pool_boilerplate,
    encode_source_lines,
    interface_pool_boilerplate,
    map_source_to_includes,
)
from sap_transport_writer import decompress_container, parse_container
from test_transport import verify


def _repos_blocks(data: bytes) -> dict[str, tuple[bytes, tuple[bytes, ...], str]]:
    records = iter_records(decompress_container(parse_container(data)))
    blocks = {}
    for index, record in enumerate(records):
        if (record.rtype != "H" or b"ABAPREAD" not in record.payload[:20]
                or record.payload[8:38].decode("latin-1").rstrip() != "REPOS"):
            continue
        full_key = record.payload[48:].decode("latin-1").rstrip()
        action = record.payload[38:44].decode("latin-1")
        key = full_key[:60].rstrip() if action == "00MMRG" else full_key
        metadata = records[index + 1]
        assert metadata.rtype == " "
        assert len(metadata.payload) == 628
        rows = []
        position = index + 2
        while records[position].rtype != "*":
            assert records[position].rtype == " "
            rows.append(records[position].payload)
            position += 1
        assert records[position].payload == b"COMMIT"
        assert records[position + 1].rtype == "E"
        blocks[key] = (metadata.payload, tuple(rows), action, full_key)
    return blocks


def _assert_source_block(
    blocks: dict[str, tuple[bytes, tuple[bytes, ...], str]], key: str, source: str
) -> None:
    assert key in blocks, sorted(blocks)
    metadata, rows, action, full_key = blocks[key]
    assert len(metadata) == 628
    assert action
    if action == "00MMRG":
        assert full_key[120:150].rstrip() == "ZCL_SRC"
        assert full_key[150:240].rstrip() == "EXECUTE"
    assert rows == tuple(_encode_source_lines(source))


@pytest.mark.templates
def test_source_injection_preserves_repos_keys_order_and_utf16_rows(
    tmp_path,
) -> None:
    source_dir = tmp_path / "src"
    source_dir.mkdir()

    program = "REPORT zsrc.\nWRITE: / 'main'."
    program_include = "DATA gv_value TYPE string."
    (source_dir / "zsrc.prog.abap").write_text(program, encoding="utf-8")
    (source_dir / "zsrc_top.prog.abap").write_text(program_include, encoding="utf-8")

    interface = "INTERFACE zif_src.\n  METHODS run.\nENDINTERFACE."
    (source_dir / "zif_src.intf.abap").write_text(interface, encoding="utf-8")

    class_definition = "CLASS zcl_src DEFINITION.\n  PUBLIC SECTION.\n  METHODS execute.\nENDCLASS."
    class_implementation = "CLASS zcl_src IMPLEMENTATION.\n  METHOD execute.\n    WRITE 'done'.\n  ENDMETHOD.\nENDCLASS."
    class_source = class_definition + "\n" + class_implementation
    class_local_def = "TYPES ty_local TYPE c LENGTH 1."
    (source_dir / "zcl_src.clas.abap").write_text(class_source, encoding="utf-8")
    (source_dir / "zcl_src.clas.locals_def.abap").write_text(
        class_local_def, encoding="utf-8"
    )

    (source_dir / "zfg_src.fugr.xml").write_text(
        "<abapGit><FUNCTIONS><item><FUNCNAME>Z_FG_RUN</FUNCNAME>"
        "<SHORT_TEXT>Run function</SHORT_TEXT></item></FUNCTIONS></abapGit>",
        encoding="utf-8",
    )
    function_pool = "FUNCTION-POOL zfg_src."
    function_source = "FUNCTION z_fg_run.\nENDFUNCTION."
    (source_dir / "zfg_src.fugr.saplzfg_src.abap").write_text(
        function_pool, encoding="utf-8"
    )
    (source_dir / "zfg_src.fugr.z_fg_run.abap").write_text(
        function_source, encoding="utf-8"
    )

    cases = [
        ("PROG", "ZSRC", "DEVK901030", {
            "ZSRC": program,
        }),
        ("PROG", "ZSRC_TOP", "DEVK901034", {"ZSRC_TOP": program_include}),
        ("INTF", "ZIF_SRC", "DEVK901031", {
            _build_repos_key("INTF", "ZIF_SRC", "IU"): interface,
            _build_repos_key("INTF", "ZIF_SRC", "IP"): _interface_pool_boilerplate("ZIF_SRC"),
        }),
        ("CLAS", "ZCL_SRC", "DEVK901032", {
            _build_repos_key("CLAS", "ZCL_SRC", "CU"): class_definition.rsplit("\n", 1)[0],
            _build_repos_key("CLAS", "ZCL_SRC", "CO"): "  PROTECTED SECTION.",
            _build_repos_key("CLAS", "ZCL_SRC", "CI"): "  PRIVATE SECTION.",
            _build_repos_key("CLAS", "ZCL_SRC", "CM001"): "  METHOD execute.\n    WRITE 'done'.\n  ENDMETHOD.",
            _build_repos_key("CLAS", "ZCL_SRC", "CCDEF"): class_local_def,
        }),
        ("FUGR", "ZFG_SRC", "DEVK901033", {
            _build_repos_key("FUGR", "ZFG_SRC", ""): function_pool,
            _build_repos_key("FUGR", "ZFG_SRC", "U01"): function_source,
        }),
    ]

    for obj_type, obj_name, request, expected_sources in cases:
        sources = collect_sources(source_dir, obj_type, obj_name)
        data, cofile = generate_transport(
            obj_type, obj_name, sources, request, sid="DEV", package="ZSOURCE"
        )
        data_file = tmp_path / f"R{request[-6:]}.DEV"
        cofile_file = tmp_path / f"K{request[-6:]}.DEV"
        data_file.write_bytes(data)
        cofile_file.write_bytes(cofile)
        assert verify(data_file, request, "ZSOURCE") == []
        assert cofile

        blocks = _repos_blocks(data)
        for key, source in expected_sources.items():
            _assert_source_block(blocks, key, source)


def test_source_block_helpers_remain_compatibly_reexported() -> None:
    assert _build_repos_key is build_repos_key
    assert _encode_source_lines is encode_source_lines
    assert _interface_pool_boilerplate is interface_pool_boilerplate
    assert _class_pool_boilerplate is class_pool_boilerplate
