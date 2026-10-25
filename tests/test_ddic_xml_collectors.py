from __future__ import annotations

from object_handlers.enqu import collect_enqu_sources, parse_enqu_xml
from object_handlers.shlp import collect_shlp_sources, parse_shlp_xml
from object_handlers.sicf import collect_sicf_sources, parse_sicf_xml
from object_handlers.tabl import collect_tabl_sources, parse_tabl_xml
from object_handlers.view import collect_view_sources, parse_view_xml


class SourceSet(dict):
    pass


def test_table_parser_collects_header_technical_settings_and_fields(tmp_path):
    path = tmp_path / "z_table.tabl.xml"
    path.write_text(
        "<ROOT><DD02V><TABNAME>Z_TABLE</TABNAME><DDLANGUAGE>E</DDLANGUAGE>"
        "<TABCLASS>TRANSP</TABCLASS><DDTEXT>Table &amp; text</DDTEXT><CLIDEP>X</CLIDEP></DD02V>"
        "<DD09L><TABNAME>Z_TABLE</TABNAME><AS4LOCAL>A</AS4LOCAL><TABKAT>0</TABKAT>"
        "<TABART>APPL0</TABART><BUFALLOW>X</BUFALLOW></DD09L>"
        "<DD03P_TABLE><DD03P><FIELDNAME>MANDT</FIELDNAME><KEYFLAG>X</KEYFLAG>"
        "<ROLLNAME>MANDT</ROLLNAME><INTTYPE>C</INTTYPE><INTLEN>6</INTLEN></DD03P>"
        "<DD03P><FIELDNAME></FIELDNAME></DD03P></DD03P_TABLE></ROOT>"
    )
    parsed = parse_tabl_xml(path)
    assert parsed["tabname"] == "Z_TABLE"
    assert parsed["ddtext"] == "Table & text"
    assert parsed["dd09l"]["TABART"] == "APPL0"
    assert parsed["fields"] == [{
        "FIELDNAME": "MANDT", "KEYFLAG": "X", "ROLLNAME": "MANDT",
        "INTTYPE": "C", "INTLEN": "6",
    }]
    assert parse_tabl_xml(tmp_path / "missing.xml")["fields"] == []
    sources = collect_tabl_sources(tmp_path, "Z_TABLE", "z_table", SourceSet)
    assert sources.tabl_meta["tabclass"] == "TRANSP"


def test_search_help_parser_collects_header_parameters_subhelps_and_mapping(tmp_path):
    path = tmp_path / "z_help.shlp.xml"
    path.write_text(
        "<ROOT><DD30V><SHLPNAME>Z_HELP</SHLPNAME><DDTEXT>Help</DDTEXT><HOTKEY>A</HOTKEY></DD30V>"
        "<DD32P_TABLE><DD32P><SHLPNAME>Z_HELP</SHLPNAME><FIELDNAME>KEY</FIELDNAME>"
        "<ROLLNAME>Z_KEY</ROLLNAME></DD32P></DD32P_TABLE>"
        "<DD31V_TABLE><DD31V><SHLPNAME>Z_HELP</SHLPNAME><SUBSHLP>Z_SUB</SUBSHLP>"
        "<SHLPPOS>1</SHLPPOS></DD31V></DD31V_TABLE>"
        "<DD33V_TABLE><DD33V><SHLPNAME>Z_HELP</SHLPNAME><SUBSHLP>Z_SUB</SUBSHLP>"
        "<FIELDNAME>KEY</FIELDNAME></DD33V></DD33V_TABLE></ROOT>"
    )
    parsed = parse_shlp_xml(path)
    assert parsed["header"] == {"DDTEXT": "Help", "HOTKEY": "A"}
    assert parsed["fields"] == [{"FIELDNAME": "KEY", "ROLLNAME": "Z_KEY"}]
    assert parsed["submethods"] == [{"SUBSHLP": "Z_SUB", "SHLPPOS": "1"}]
    assert parsed["mappings"] == [{"SUBSHLP": "Z_SUB", "FIELDNAME": "KEY"}]
    assert parse_shlp_xml(tmp_path / "missing.xml")["header"] == {}
    assert collect_shlp_sources(tmp_path, "Z_HELP", "z_help", SourceSet).shlp_meta == parsed


def test_service_parser_collects_url_metadata_and_handlers(tmp_path):
    path = tmp_path / "z_service.sicf.xml"
    path.write_text(
        "<ROOT><URL>/sap/z</URL><ICFSERVICE><ICF_NAME>Z_SERVICE</ICF_NAME>"
        "<ORIG_NAME>Z_ORIG</ORIG_NAME><ICFALTNME>ALT</ICFALTNME>"
        "<ICFALTNME_ORIG>OLD</ICFALTNME_ORIG></ICFSERVICE>"
        "<ICFDOCU><ICF_LANGU>E</ICF_LANGU><ICF_DOCU>Service</ICF_DOCU></ICFDOCU>"
        "<ICFHANDLER_TABLE><ICFHANDLER><ICFORDER>1</ICFORDER><ICFTYP>ABAP</ICFTYP>"
        "<ICFHANDLER>ZCL_HANDLER</ICFHANDLER></ICFHANDLER></ICFHANDLER_TABLE></ROOT>"
    )
    parsed = parse_sicf_xml(path)
    assert parsed["url"] == "/sap/z"
    assert parsed["icf_name"] == "Z_SERVICE"
    assert parsed["ddtext"] == "Service"
    assert parsed["handlers"] == [{"ICFORDER": "1", "ICFTYP": "ABAP", "ICFHANDLER": "ZCL_HANDLER"}]
    assert parse_sicf_xml(tmp_path / "missing.xml")["handlers"] == []
    assert collect_sicf_sources(tmp_path, "Z_SERVICE", "z_service", SourceSet).sicf_meta == parsed


def test_lock_and_view_parsers_collect_headers_tables_and_fields(tmp_path):
    enqu_path = tmp_path / "z_lock.enqu.xml"
    enqu_path.write_text(
        "<ROOT><DD25V><VIEWNAME>Z_LOCK</VIEWNAME><DDLANGUAGE>E</DDLANGUAGE>"
        "<AGGTYPE>E</AGGTYPE><ROOTTAB>Z_TAB</ROOTTAB><DDTEXT>Lock</DDTEXT></DD25V>"
        "<DD26E_TABLE><DD26E><TABNAME>Z_TAB</TABNAME><TABPOS>1</TABPOS>"
        "<FORTABNAME>Z_PARENT</FORTABNAME><ENQMODE>E</ENQMODE></DD26E></DD26E_TABLE>"
        "<DD27P_TABLE><DD27P><VIEWFIELD>KEY</VIEWFIELD><TABNAME>Z_TAB</TABNAME>"
        "<FIELDNAME>KEY</FIELDNAME><KEYFLAG>X</KEYFLAG><ENQMODE>E</ENQMODE></DD27P></DD27P_TABLE></ROOT>"
    )
    enqu = parse_enqu_xml(enqu_path)
    assert enqu["viewname"] == "Z_LOCK"
    assert enqu["tables"] == [{"TABNAME": "Z_TAB", "TABPOS": "1", "FORTABNAME": "Z_PARENT", "ENQMODE": "E"}]
    assert enqu["fields"] == [{"VIEWFIELD": "KEY", "TABNAME": "Z_TAB", "FIELDNAME": "KEY", "KEYFLAG": "X", "ENQMODE": "E"}]
    assert collect_enqu_sources(tmp_path, "Z_LOCK", "z_lock", SourceSet).enqu_meta == enqu

    view_path = tmp_path / "z_view.view.xml"
    view_path.write_text(
        "<ROOT><DD25V><VIEWNAME>Z_VIEW</VIEWNAME><DDLANGUAGE>E</DDLANGUAGE>"
        "<AGGTYPE>V</AGGTYPE><APPLCLASS>SD</APPLCLASS><ROOTTAB>Z_TAB</ROOTTAB>"
        "<DDTEXT>View</DDTEXT><VIEWCLASS>D</VIEWCLASS><CUSTOMAUTH>X</CUSTOMAUTH>"
        "<VIEWGRANT>G</VIEWGRANT><GLOBALFLAG>X</GLOBALFLAG></DD25V>"
        "<DD26V_TABLE><DD26V><TABNAME>Z_TAB</TABNAME><TABPOS>1</TABPOS>"
        "<FORTABNAME>Z_PARENT</FORTABNAME><FORFIELD>ID</FORFIELD><FORDIR>A</FORDIR></DD26V></DD26V_TABLE>"
        "<DD27P_TABLE><DD27P><VIEWFIELD>ID</VIEWFIELD><TABNAME>Z_TAB</TABNAME>"
        "<FIELDNAME>ID</FIELDNAME><KEYFLAG>X</KEYFLAG><RDONLY></RDONLY>"
        "<SHLPORIGIN>P</SHLPORIGIN><VALEXI>X</VALEXI><LOGFLAG>L</LOGFLAG>"
        "<CHECKTABLE>Z_CHECK</CHECKTABLE></DD27P></DD27P_TABLE></ROOT>"
    )
    view = parse_view_xml(view_path)
    assert view["applclass"] == "SD"
    assert view["tables"][0]["FORDIR"] == "A"
    assert view["fields"][0]["CHECKTABLE"] == "Z_CHECK"
    assert collect_view_sources(tmp_path, "Z_VIEW", "z_view", SourceSet).view_meta == view
