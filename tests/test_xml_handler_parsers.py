from __future__ import annotations

from object_handlers import amsd, aplo, aqbg, char, devc, dtel, msag, tran, ttyp, xslt


class SourceSet:
    pass


def test_amsd_parser_and_collector_cover_valid_missing_and_malformed_xml(tmp_path):
    xml_path = tmp_path / "z_amsd.amsd.xml"
    xml_path.write_text("<ROOT><AMSD><NAME>A &amp; B</NAME><NEST><VALUE>X</VALUE></NEST></AMSD></ROOT>")
    assert amsd.parse_amsd_xml(xml_path) == {"NAME": "A & B", "VALUE": "X"}
    assert amsd.parse_amsd_xml(tmp_path / "missing.xml") == {}
    xml_path.write_text("<AMSD>")
    assert amsd.parse_amsd_xml(xml_path) == {}

    xml_path.write_text("<ROOT><AMSD><NAME>Z</NAME></AMSD></ROOT>")
    sources = amsd.collect_amsd_sources(tmp_path, "Z_AMSD", "z_amsd", SourceSet)
    assert sources.amsd_meta == {"NAME": "Z"}


def test_aplo_parser_and_collector_handle_direct_and_row_sections(tmp_path):
    xml_path = tmp_path / "z_aplo.aplo.xml"
    xml_path.write_text(
        "<ROOT><BALOBJ><OBJECT>LOG</OBJECT><TEXT>Main</TEXT></BALOBJ>"
        "<BALSUBT><ROW><LANGU>E</LANGU><TEXT>Sub</TEXT></ROW></BALSUBT></ROOT>"
    )
    parsed = aplo.parse_aplo_xml(xml_path)
    assert parsed["BALOBJ"] == [{"OBJECT": "LOG", "TEXT": "Main"}]
    assert parsed["BALSUBT"] == [{"LANGU": "E", "TEXT": "Sub"}]
    assert aplo.parse_aplo_xml(tmp_path / "missing.xml") == {}
    xml_path.write_text("<ROOT>")
    assert aplo.parse_aplo_xml(xml_path) == {}

    xml_path.write_text("<ROOT><BALOBJ><OBJECT>LOG</OBJECT></BALOBJ></ROOT>")
    sources = aplo.collect_aplo_sources(tmp_path, "Z_APLO", "z_aplo", SourceSet)
    assert sources.aplo_meta["BALOBJ"][0]["OBJECT"] == "LOG"


def test_aqbg_and_char_collectors_cover_xml_paths(tmp_path):
    (tmp_path / "z_group.aqbg.xml").write_text("<ROOT><AQGDBBG><USERGROUP>ZGRP</USERGROUP></AQGDBBG></ROOT>")
    aqbg_sources = aqbg.collect_aqbg_sources(tmp_path, "Z_GROUP", "z_group", SourceSet)
    assert aqbg_sources.aqbg_meta == {"USERGROUP": "ZGRP"}

    char_path = tmp_path / "z_char.char.xml"
    char_path.write_text(
        "<ROOT><CLS_ATTRIBUTE><NAME>COLOR</NAME></CLS_ATTRIBUTE>"
        "<CLS_ATTRIBUTET><ROW><LANGU>E</LANGU><TEXT>Colour</TEXT></ROW></CLS_ATTRIBUTET></ROOT>"
    )
    char_sources = char.collect_char_sources(tmp_path, "Z_CHAR", "z_char", SourceSet)
    assert char_sources.char_meta["CLS_ATTRIBUTE"] == [{"NAME": "COLOR"}]
    assert char_sources.char_meta["CLS_ATTRIBUTET"] == [{"LANGU": "E", "TEXT": "Colour"}]

    char_path.write_text("<ROOT>")
    assert char.collect_char_sources(tmp_path, "Z_CHAR", "z_char", SourceSet).char_meta == {}


def test_devc_dtel_and_ttyp_collectors_extract_dictionary_metadata(tmp_path):
    (tmp_path / "z_pkg.devc.xml").write_text(
        "<ROOT><TDEVCT><DDTEXT>Package</DDTEXT></TDEVCT></ROOT>"
    )
    devc_sources = devc.collect_devc_sources(tmp_path, "ZPKG", "z_pkg", SourceSet)
    assert devc_sources.devc_meta == {"description": "Package", "TDEVC": {},
                                      "TDEVCT": {"DDTEXT": "Package"}}

    dtel_path = tmp_path / "z_elem.dtel.xml"
    dtel_path.write_text("<ROOT><DD04V><ROLLNAME>Z_ELEM</ROLLNAME><DDTEXT>A &amp; B</DDTEXT><FLAG /></DD04V></ROOT>")
    assert dtel.parse_dtel_xml(dtel_path) == {"ROLLNAME": "Z_ELEM", "DDTEXT": "A & B", "FLAG": ""}
    dtel_sources = dtel.collect_dtel_sources(tmp_path, "Z_ELEM", "z_elem", SourceSet)
    assert dtel_sources.dtel_fields["ROLLNAME"] == "Z_ELEM"

    ttyp_path = tmp_path / "z_tabtype.ttyp.xml"
    ttyp_path.write_text("<ROOT><DD40V><TYPENAME>Z_TABTYPE</TYPENAME><ROWTYPE>Z_ELEM</ROWTYPE></DD40V></ROOT>")
    assert ttyp.parse_ttyp_xml(ttyp_path) == {"TYPENAME": "Z_TABTYPE", "ROWTYPE": "Z_ELEM"}
    ttyp_sources = ttyp.collect_ttyp_sources(tmp_path, "Z_TABTYPE", "z_tabtype", SourceSet)
    assert ttyp_sources.ttyp_fields["TYPENAME"] == "Z_TABTYPE"


def test_msag_and_tran_collectors_extract_transport_metadata(tmp_path):
    msag_path = tmp_path / "z_messages.msag.xml"
    msag_path.write_text(
        "<ROOT><T100A><MASTERLANG>E</MASTERLANG><STEXT>Messages</STEXT></T100A>"
        "<T100><T100><MSGNR>1</MSGNR><TEXT>Hello</TEXT></T100></T100></ROOT>"
    )
    parsed_msag = msag.parse_msag_xml(msag_path)
    assert parsed_msag["masterlang"] == "E"
    assert parsed_msag["messages"] == [("001", "Hello")]
    assert msag.parse_msag_xml(tmp_path / "missing.xml")["messages"] == []
    msag_sources = msag.collect_msag_sources(tmp_path, "Z_MESSAGES", "z_messages", SourceSet)
    assert msag_sources.msag_messages == [("001", "Hello")]

    tran_path = tmp_path / "z_tran.tran.xml"
    tran_path.write_text(
        "<ROOT><TSTC><TCODE>ZRUN</TCODE></TSTC><TSTCC><TCODE>ZRUN</TCODE><PARAM>P</PARAM></TSTCC>"
        "<TSTCT><TCODE>ZRUN</TCODE><TEXT>Run</TEXT></TSTCT><TSTCP><PARAM>X</PARAM></TSTCP></ROOT>"
    )
    parsed_tran = tran.parse_tran_xml(tran_path)
    assert parsed_tran["TSTC"]["TCODE"] == "ZRUN"
    assert parsed_tran["TSTCC"]["PARAM"] == "P"
    assert parsed_tran["TSTCT"]["TEXT"] == "Run"
    assert parsed_tran["TSTCP"]["PARAM"] == "X"
    assert tran.parse_tran_xml(tmp_path / "missing.xml")["TSTC"] == {}
    tran_sources = tran.collect_tran_sources(tmp_path, "Z_TRAN", "z_tran", SourceSet)
    assert tran_sources.tran_fields["TSTC"]["TCODE"] == "ZRUN"


def test_xslt_parser_and_collector_read_attributes_and_source(tmp_path):
    xml_path = tmp_path / "z_transform.xslt.xml"
    source_path = tmp_path / "z_transform.xslt.source.xml"
    xml_path.write_text(
        "<ROOT><ATTRIBUTES><XSLTDESC>Z_TRANSFORM</XSLTDESC><LANGU>E</LANGU>"
        "<DESCRIPT>Transform</DESCRIPT></ATTRIBUTES></ROOT>"
    )
    source_path.write_text("<xsl:stylesheet version=\"1.0\" />")
    parsed = xslt.parse_xslt_xml(xml_path)
    assert parsed["xsltdesc"] == "Z_TRANSFORM"
    assert parsed["langu"] == "E"
    assert parsed["source"] == "<xsl:stylesheet version=\"1.0\" />"
    assert xslt.parse_xslt_xml(tmp_path / "missing.xslt.xml")["source"] == ""
    sources = xslt.collect_xslt_sources(tmp_path, "Z_TRANSFORM", "z_transform", SourceSet)
    assert sources.xslt_meta["descript"] == "Transform"
