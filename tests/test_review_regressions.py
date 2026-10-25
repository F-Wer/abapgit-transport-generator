"""Regressions for the three findings in PR #75's Codex review."""
import pytest

import abapgit_to_transport as generator
from sap_transport_records import iter_records
from sap_transport_writer import decompress_container, parse_container
from test_transport import verify


@pytest.mark.templates
def test_new_language_keeps_text_when_all_donor_languages_are_removed():
    _, records = generator._load_template_records("APLO")
    table = "BALOBJT"
    blocks = generator._table_blocks(records, table)
    assert len(blocks) > 1
    assert all(chr(records[b[0]].payload[48]) != "J" for b in blocks)
    generator._regenerate_table_content(
        records, "Z_REVIEW", {table: [{"SPRAS": "J", "OBJECT": "Z_REVIEW",
                                      "OBJTXT": "Japanese description"}]}, language="J")
    blocks = generator._table_blocks(records, table)
    assert len(blocks) == 1
    assert chr(records[blocks[0][0]].payload[48]) == "J"
    fields = generator._parse_nametabs(records)[table]
    rows = [records[i].payload for i in blocks[0][1]]
    assert len(rows) == 1
    assert generator._get_field_text(rows[0], fields, "OBJTXT") == "Japanese description"


@pytest.mark.parametrize("declaration", [
    "INTERFACE z_review. CONSTANTS gc_value TYPE string VALUE 'a  b'. ENDINTERFACE.",
    "CLASS z_review DEFINITION. PUBLIC SECTION.\n"
    "CONSTANTS: gc_value TYPE string VALUE 'a  b', gc_other TYPE string VALUE ' c   d '. ENDCLASS.",
])
def test_constant_metadata_preserves_literal_whitespace(declaration):
    members = generator._parse_seo_declarations(declaration)["members"]
    constants = {m["name"]: m["value"] for m in members if m["kind"] == "const"}
    assert constants["GC_VALUE"] == "a  b"
    if "GC_OTHER" in constants:
        assert constants["GC_OTHER"] == " c   d "


@pytest.mark.templates
def test_self_owned_package_verifies_with_the_actual_generation_package(tmp_path):
    source = tmp_path / "src"
    source.mkdir()
    (source / "z_review.devc.xml").write_text(
        "<abapGit><DEVC><CTEXT>Review package</CTEXT></DEVC></abapGit>")
    sources = generator.collect_sources(source, "DEVC", "Z_REVIEW")
    data, _ = generator.generate_transport(
        "DEVC", "Z_REVIEW", sources, "DEVK910121", sid="DEV", package="ZROOT")
    output = tmp_path / "R910121.DEV"
    output.write_bytes(data)
    assert not verify(output, "DEVK910121", "ZROOT")
    records = iter_records(decompress_container(parse_container(data)))
    a = next(r for r in records if r.rtype == "A").payload.decode("utf-16-le")
    assert a[81:111].rstrip() == "Z_REVIEW"
