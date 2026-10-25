"""End-to-end characterization of generated TOBJ transports."""

import pytest
from abapgit_to_transport import (
    _find_block,
    _find_block_by_action,
    _get_field_text,
    _parse_nametabs,
    _regenerate_tobj_rows,
    collect_sources,
    generate_transport,
)
from sap_transport_records import iter_records, u16
from transport_regenerators.tobj import regenerate_tobj_rows
from sap_transport_writer import decompress_container, parse_container
from test_transport import verify


@pytest.mark.templates
def test_tobj_generation_preserves_xml_identity_metadata_and_record_order(tmp_path) -> None:
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    (source_dir / "z_order_cfgs.tobj.xml").write_text(
        "<abapGit>"
        "<OBJH><OBJECTNAME>Z_ORDER_CFG</OBJECTNAME><OBJECTTYPE>S</OBJECTTYPE>"
        "<CLIDEP>X</CLIDEP><OBJCATEG>CUST</OBJCATEG><OBJTRANSP>2</OBJTRANSP>"
        "<IMPORTABLE>3</IMPORTABLE></OBJH>"
        "<OBJT><LANGUAGE>E</LANGUAGE><OBJECTNAME>Z_ORDER_CFG</OBJECTNAME>"
        "<OBJECTTYPE>S</OBJECTTYPE><DDTEXT>Order configuration</DDTEXT></OBJT>"
        "<OBJS>"
        "<OBJS><OBJECTNAME>Z_ORDER_CFG</OBJECTNAME><OBJECTTYPE>S</OBJECTTYPE>"
        "<TABNAME>ZORDERCFG</TABNAME><DDIC>X</DDIC><PRIM_TABLE>X</PRIM_TABLE></OBJS>"
        "<OBJS><OBJECTNAME>Z_ORDER_CFG</OBJECTNAME><OBJECTTYPE>S</OBJECTTYPE>"
        "<TABNAME>ZORDERCFG_ITEM</TABNAME><DDIC>X</DDIC></OBJS>"
        "</OBJS>"
        "<TOBJ><TDDAT><TABNAME>ZORDERCFG</TABNAME><CCLASS>CUST</CCLASS></TDDAT>"
        "<TVDIR><TABNAME>ZORDERCFG</TABNAME><AREA>ZORDERFG</AREA><TYPE>1</TYPE>"
        "<LISTE>7</LISTE><BASTAB>X</BASTAB><FLAG>A</FLAG></TVDIR></TOBJ>"
        "</abapGit>",
        encoding="utf-8",
    )

    sources = collect_sources(source_dir, "TOBJ", "Z_ORDER_CFGS")
    first_data, first_cofile = generate_transport(
        "TOBJ", "Z_ORDER_CFGS", sources, "DEVK901014", sid="DEV",
        package="ZTOBJ",
    )
    second_data, second_cofile = generate_transport(
        "TOBJ", "Z_ORDER_CFGS", sources, "DEVK901014", sid="DEV",
        package="ZTOBJ",
    )

    assert first_data == second_data
    assert first_cofile == second_cofile

    data_file = tmp_path / "R901014.DEV"
    cofile_file = tmp_path / "K901014.DEV"
    data_file.write_bytes(first_data)
    cofile_file.write_bytes(first_cofile)
    assert verify(data_file, "DEVK901014", "ZTOBJ") == []

    records = iter_records(decompress_container(parse_container(first_data)))
    nametabs = _parse_nametabs(records)
    objh = _find_block_by_action(records, "OBJH", "00REPC")
    objs = _find_block_by_action(records, "OBJS", "00REPC")
    objt = _find_block_by_action(records, "OBJT", "00REPC")
    tddat = _find_block_by_action(records, "TDDAT", "00REPC")
    tvdir = _find_block_by_action(records, "TVDIR", "00REPC")
    assert objh is not None and objs is not None and objt is not None
    assert tddat is not None and tvdir is not None

    assert _get_field_text(records[objh[1][0]].payload, nametabs["OBJH"], "OBJECTNAME") == "Z_ORDER_CFG"
    assert _get_field_text(records[objt[1][0]].payload, nametabs["OBJT"], "LANGUAGE") == "E"
    assert _get_field_text(records[objt[1][0]].payload, nametabs["OBJT"], "DDTEXT") == "Order configuration"
    assert [
        _get_field_text(records[index].payload, nametabs["OBJS"], "TABNAME")
        for index in objs[1]
    ] == ["ZORDERCFG", "ZORDERCFG_ITEM"]
    assert _get_field_text(records[tddat[1][0]].payload, nametabs["TDDAT"], "CCLASS") == "CUST"
    assert _get_field_text(records[tvdir[1][0]].payload, nametabs["TVDIR"], "LISTE") == "0007"

    objh_key = records[objh[0]].payload[48:48 + 32].decode("latin-1")
    tddat_key = records[tddat[0]].payload[48:48 + 31].decode("latin-1")
    assert objh_key == "Z_ORDER_CFG".ljust(30) + "S*"
    assert tddat_key == "ZORDERCFG".ljust(30) + "*"

    object_keys = [u16(record.payload) for record in records if record.rtype == "C"]
    assert len(object_keys) == 1
    assert "TOBJ" in object_keys[0]
    assert "Z_ORDER_CFGS" in object_keys[0]


@pytest.mark.templates
def test_tobj_generation_drops_tddat_when_the_xml_has_no_tddat(tmp_path) -> None:
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    (source_dir / "z_order_cluster.tobj.xml").write_text(
        "<abapGit>"
        "<OBJH><OBJECTNAME>Z_ORDER_CLUSTER</OBJECTNAME><OBJECTTYPE>V</OBJECTTYPE></OBJH>"
        "<OBJT><LANGUAGE>D</LANGUAGE><OBJECTNAME>Z_ORDER_CLUSTER</OBJECTNAME>"
        "<OBJECTTYPE>V</OBJECTTYPE><DDTEXT>Order cluster</DDTEXT></OBJT>"
        "<OBJS><OBJS><OBJECTNAME>Z_ORDER_CLUSTER</OBJECTNAME><OBJECTTYPE>V</OBJECTTYPE>"
        "<TABNAME>ZORDERVIEW</TABNAME></OBJS></OBJS>"
        "<TOBJ><TVDIR><TABNAME>ZORDERVIEW</TABNAME><AREA>ZORDERFG</AREA>"
        "<TYPE>1</TYPE><LISTE>1</LISTE></TVDIR></TOBJ>"
        "</abapGit>",
        encoding="utf-8",
    )

    sources = collect_sources(source_dir, "TOBJ", "Z_ORDER_CLUSTER")
    data, _ = generate_transport(
        "TOBJ", "Z_ORDER_CLUSTER", sources, "DEVK901015", sid="DEV",
        package="ZTOBJ",
    )
    records = iter_records(decompress_container(parse_container(data)))
    assert _find_block(records, "TDDAT") is None


def test_tobj_regenerator_is_compatibly_reexported() -> None:
    assert _regenerate_tobj_rows is regenerate_tobj_rows
