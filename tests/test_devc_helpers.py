import pytest
from pathlib import Path

from devc_helpers import parse_devc_xml, regenerate_devc_rows


def test_parse_devc_xml_extracts_unescaped_description(tmp_path: Path) -> None:
    source = tmp_path / "z_package.devc.xml"
    source.write_text(
        "<abapGit><TDEVCT><DDTEXT>Package &amp; transport</DDTEXT></TDEVCT></abapGit>",
        encoding="utf-8",
    )

    assert parse_devc_xml(source) == {"description": "Package & transport",
                                      "TDEVC": {}, "TDEVCT": {"DDTEXT": "Package & transport"}}


def test_parse_devc_xml_is_safe_for_missing_and_invalid_inputs(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.devc.xml"
    invalid.write_text("<broken>", encoding="utf-8")

    empty = {"description": "", "TDEVC": {}, "TDEVCT": {}}
    assert parse_devc_xml(None) == empty
    assert parse_devc_xml(tmp_path / "missing.devc.xml") == empty
    assert parse_devc_xml(invalid) == empty


@pytest.mark.templates
def test_regenerate_devc_rows_recreates_package_metadata(tmp_path: Path) -> None:
    from abapgit_to_transport import (_find_block_by_action, _get_field_text,
                                      _parse_nametabs, collect_sources,
                                      generate_transport)
    from sap_transport_records import iter_records
    from sap_transport_writer import decompress_container, parse_container
    from test_transport import verify

    source_dir = tmp_path / "src"
    source_dir.mkdir()
    (source_dir / "zdemo_devc.devc.xml").write_text(
        "<abapGit><DEVC><CTEXT>Demo package</CTEXT></DEVC></abapGit>", encoding="utf-8")
    sources = collect_sources(source_dir, "DEVC", "ZDEMO_DEVC")
    data, _ = generate_transport("DEVC", "ZDEMO_DEVC", sources, "DEVK900503",
                                 package="IGNORED_FOR_DEVC", author="DEVELOPER")
    output = tmp_path / "R900503.DEV"
    output.write_bytes(data)
    # A package's own TADIR entry belongs to itself, whatever --package says.
    assert not verify(output, "DEVK900503", "IGNORED_FOR_DEVC")

    records = iter_records(decompress_container(parse_container(data)))
    fields = _parse_nametabs(records)
    header = _find_block_by_action(records, "TDEVC", "00REP ")
    text = _find_block_by_action(records, "TDEVCT", "00REPC")
    assert header and text
    hrow = records[header[1][0]].payload
    trow = records[text[1][0]].payload
    assert _get_field_text(hrow, fields["TDEVC"], "DEVCLASS") == "ZDEMO_DEVC"
    assert _get_field_text(hrow, fields["TDEVC"], "KORRFLAG") == "X"
    assert _get_field_text(hrow, fields["TDEVC"], "DLVUNIT") == "HOME"
    assert _get_field_text(hrow, fields["TDEVC"], "NAMESPACE") == "/0CUST/"
    assert _get_field_text(trow, fields["TDEVCT"], "DEVCLASS") == "ZDEMO_DEVC"
    assert _get_field_text(trow, fields["TDEVCT"], "CTEXT") == "Demo package"
