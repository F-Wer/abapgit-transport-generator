"""End-to-end characterization of generated transaction-code transports."""

import pytest
from abapgit_to_transport import (
    _find_block,
    _get_field_text,
    _parse_nametabs,
    _apply_tran_row,
    _fix_tran_tstct_language_key,
    _regenerate_tran_tstcp,
    collect_sources,
    generate_transport,
)
from sap_transport_records import iter_records, u16
from transport_regenerators.special import (
    apply_tran_row,
    fix_tran_tstct_language_key,
    regenerate_tran_tstcp,
)
from sap_transport_writer import decompress_container, parse_container
from test_transport import verify


@pytest.mark.templates
def test_report_transaction_generation_preserves_program_flags_and_text(tmp_path) -> None:
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    (source_dir / "z_order_tx.tran.xml").write_text(
        "<abapGit><TSTC><TCODE>Z_ORDER_TX</TCODE><PGMNA>Z_ORDER_REPORT</PGMNA>"
        "<DYPNO>1000</DYPNO><CINFO>WA==</CINFO></TSTC>"
        "<TSTCC><TCODE>Z_ORDER_TX</TCODE><S_WEBGUI>X</S_WEBGUI>"
        "<S_WIN32>X</S_WIN32></TSTCC>"
        "<TSTCT><TCODE>Z_ORDER_TX</TCODE><SPRSL>E</SPRSL>"
        "<TTEXT>Order transaction</TTEXT></TSTCT></abapGit>",
        encoding="utf-8",
    )

    sources = collect_sources(source_dir, "TRAN", "Z_ORDER_TX")
    first_data, first_cofile = generate_transport(
        "TRAN", "Z_ORDER_TX", sources, "DEVK901013", sid="DEV", package="ZTRAN"
    )
    second_data, second_cofile = generate_transport(
        "TRAN", "Z_ORDER_TX", sources, "DEVK901013", sid="DEV", package="ZTRAN"
    )

    assert first_data == second_data
    assert first_cofile == second_cofile

    data_file = tmp_path / "R901013.DEV"
    cofile_file = tmp_path / "K901013.DEV"
    data_file.write_bytes(first_data)
    cofile_file.write_bytes(first_cofile)
    assert verify(data_file, "DEVK901013", "ZTRAN") == []

    records = iter_records(decompress_container(parse_container(first_data)))
    nametabs = _parse_nametabs(records)
    tstc = _find_block(records, "TSTC")
    tstct = _find_block(records, "TSTCT")
    assert tstc is not None and tstct is not None
    assert _get_field_text(records[tstc[1][0]].payload, nametabs["TSTC"], "PGMNA") == "Z_ORDER_REPORT"
    assert _get_field_text(records[tstc[1][0]].payload, nametabs["TSTC"], "DYPNO") == "1000"
    assert _get_field_text(records[tstct[1][0]].payload, nametabs["TSTCT"], "TTEXT") == "Order transaction"

    object_keys = [u16(record.payload) for record in records if record.rtype == "C"]
    assert len(object_keys) == 1
    assert "TRAN" in object_keys[0]
    assert "Z_ORDER_TX" in object_keys[0]


def test_tran_helpers_are_compatibly_reexported() -> None:
    assert _apply_tran_row is apply_tran_row
    assert _fix_tran_tstct_language_key is fix_tran_tstct_language_key
    assert _regenerate_tran_tstcp is regenerate_tran_tstcp
