"""End-to-end characterization of generated XSLT transports."""

import pytest
from abapgit_to_transport import (
    _decompress_xslt_cluster,
    _find_block,
    _get_field_text,
    _locate_xslt_chunks,
    _parse_nametabs,
    _read_xslt_chunked_text,
    _regenerate_xslt_rows,
    collect_sources,
    generate_transport,
)
from sap_transport_records import iter_records, u16
from transport_regenerators.xslt import regenerate_xslt_rows
from sap_transport_writer import decompress_container, parse_container
from test_transport import verify


@pytest.mark.templates
def test_xslt_generation_preserves_source_cluster_and_description(tmp_path) -> None:
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    source = '<tt:transform xmlns:tt="http://www.sap.com/transformation-templates"><tt:root name="ROOT"/></tt:transform>'
    (source_dir / "zorder_xslt.xslt.xml").write_text(
        "<abapGit><ATTRIBUTES><XSLTDESC>ZORDER_XSLT</XSLTDESC><LANGU>E</LANGU>"
        "<DESCRIPT>Order transformation</DESCRIPT></ATTRIBUTES></abapGit>",
        encoding="utf-8",
    )
    (source_dir / "zorder_xslt.xslt.source.xml").write_text(source, encoding="utf-8")

    sources = collect_sources(source_dir, "XSLT", "ZORDER_XSLT")
    first_data, first_cofile = generate_transport(
        "XSLT", "ZORDER_XSLT", sources, "DEVK901018", sid="DEV", package="ZXSLT"
    )
    second_data, second_cofile = generate_transport(
        "XSLT", "ZORDER_XSLT", sources, "DEVK901018", sid="DEV", package="ZXSLT"
    )
    assert first_data == second_data
    assert first_cofile == second_cofile

    data_file = tmp_path / "R901018.DEV"
    cofile_file = tmp_path / "K901018.DEV"
    data_file.write_bytes(first_data)
    cofile_file.write_bytes(first_cofile)
    assert verify(data_file, "DEVK901018", "ZXSLT") == []

    records = iter_records(decompress_container(parse_container(first_data)))
    nametabs = _parse_nametabs(records)
    desc = _find_block(records, "O2XSLTDESC")
    texts = _find_block(records, "O2XSLTTEXT")
    assert desc is not None and texts is not None
    row = records[desc[1][0]]
    assert _get_field_text(row.payload, nametabs["O2XSLTDESC"], "XSLTDESC") == "ZORDER_XSLT"
    clustd = next(field for field in nametabs["O2XSLTDESC"] if field[0] == "CLUSTD")
    _, offset, length, _ = clustd
    cluster = _decompress_xslt_cluster(row.payload[offset:offset + length])
    regenerated = _read_xslt_chunked_text(cluster, _locate_xslt_chunks(cluster)).rstrip()
    assert regenerated == source
    # The template sweeps each language with a delete block and inserts its
    # German text in one 00REPC block; only that block may carry a row, and
    # it must be the repo's text in the repo's language.
    text_fields = nametabs["O2XSLTTEXT"]
    blocks, current = [], None
    for record in records:
        if record.rtype == "H" and record.payload[8:38].rstrip() == b"O2XSLTTEXT":
            current = (record.payload[38:44], record.payload[48:].decode("latin-1"), [])
            blocks.append(current)
        elif record.rtype == "E":
            current = None
        elif record.rtype == " " and current is not None:
            current[2].append(record)
    inserts = [block for block in blocks if block[0] == b"00REPC"]
    assert len(inserts) == 1
    _action, key, rows = inserts[0]
    assert key.rstrip().endswith("E*")
    assert [(_get_field_text(row.payload, text_fields, "LANGU"),
             _get_field_text(row.payload, text_fields, "DESCRIPT")) for row in rows] == [
        ("E", "Order transformation")]
    assert all(not block[2] for block in blocks if block[0] != b"00REPC")
    swept = sorted(block[1].rstrip()[-2] for block in blocks)
    assert len(swept) == len(set(swept))

    object_keys = [u16(record.payload) for record in records if record.rtype == "C"]
    assert len(object_keys) == 1
    assert "XSLT" in object_keys[0] and "ZORDER_XSLT" in object_keys[0]


def test_xslt_regenerator_remains_compatibly_reexported() -> None:
    assert _regenerate_xslt_rows is regenerate_xslt_rows
