from __future__ import annotations

import pytest

from object_handlers.clas import collect_clas_sources
from object_handlers.fugr import collect_fugr_sources, parse_fugr_xml
from object_handlers.intf import collect_intf_sources
from object_handlers.prog import collect_prog_sources
from object_handlers.source_code import SOURCE_COLLECTORS
from object_handlers.type import collect_type_sources, parse_type_xml


class SourceSet(dict):
    pass


def key(*parts: str) -> str:
    return "|".join(parts)


def test_class_interface_program_collectors_cover_supported_file_names(tmp_path):
    (tmp_path / "z_class.clas.abap").write_text("CLASS z_class DEFINITION.")
    (tmp_path / "z_class.clas.locals_def.abap").write_text("TYPES ty_local TYPE c.")
    (tmp_path / "z_class.clas.locals_imp.abap").write_text("METHOD local.")
    (tmp_path / "z_class.clas.macros.abap").write_text("DEFINE test.")
    (tmp_path / "z_class.clas.testclasses.abap").write_text("CLASS ltc DEFINITION FOR TESTING.")

    clas = collect_clas_sources(tmp_path, "Z_CLASS", "z_class", key)
    assert clas["Z_CLASS"] == "CLASS z_class DEFINITION."
    assert clas[key("CLAS", "Z_CLASS", "CCDEF")] == "TYPES ty_local TYPE c."
    assert clas[key("CLAS", "Z_CLASS", "CCIMP")] == "METHOD local."
    assert clas[key("CLAS", "Z_CLASS", "CCMAC")] == "DEFINE test."
    assert clas[key("CLAS", "Z_CLASS", "CCAU")] == "CLASS ltc DEFINITION FOR TESTING."

    (tmp_path / "z_interface.intf.abap").write_text("INTERFACE z_interface.")
    assert collect_intf_sources(tmp_path, "Z_INTERFACE", "z_interface", key) == {
        key("INTF", "Z_INTERFACE", "IU"): "INTERFACE z_interface."
    }
    assert collect_intf_sources(tmp_path, "Z_EMPTY", "z_empty", key) == {}

    (tmp_path / "z_report.prog.abap").write_text("REPORT z_report.")
    (tmp_path / "z_report_top.prog.abap").write_text("DATA gv_text TYPE string.")
    program = collect_prog_sources(tmp_path, "Z_REPORT", "z_report", key)
    assert program == {
        "Z_REPORT": "REPORT z_report.",
    }
    assert collect_prog_sources(tmp_path, "Z_REPORT_TOP", "z_report_top", key) == {
        "Z_REPORT_TOP": "DATA gv_text TYPE string."}
    assert SOURCE_COLLECTORS == {
        "PROG": collect_prog_sources,
        "CLAS": collect_clas_sources,
        "INTF": collect_intf_sources,
    }


def test_function_group_parser_and_collector_cover_sources_and_missing_function(tmp_path, capsys):
    from abapgit_to_transport import _build_repos_key as key
    xml_path = tmp_path / "zfg.fugr.xml"
    xml_path.write_text(
        "<ROOT><AREAT>Group text</AREAT><FUNCTIONS>"
        "<item><FUNCNAME>z_func</FUNCNAME><SHORT_TEXT>Function</SHORT_TEXT></item>"
        "<item><FUNCNAME>Z_MISSING</FUNCNAME></item></FUNCTIONS></ROOT>"
    )
    parsed = parse_fugr_xml(xml_path)
    assert parsed["areat"] == "Group text"
    assert parsed["functions"] == [("Z_FUNC", "Function"), ("Z_MISSING", "")]
    assert parsed["interfaces"]["Z_FUNC"]["params"] == []
    assert parse_fugr_xml(tmp_path / "missing.xml") == {"areat": "", "functions": [], "interfaces": {}}

    (tmp_path / "zfg.fugr.saplzfg.abap").write_text("FUNCTION-POOL zfg.")
    (tmp_path / "zfg.fugr.lzfgfoo.abap").write_text("INCLUDE lzfgfoo.")
    (tmp_path / "zfg.fugr.z_func.abap").write_text("FUNCTION z_func.")
    sources = collect_fugr_sources(tmp_path, "ZFG", "zfg", key, SourceSet)

    assert sources.fugr_areat == "Group text"
    assert sources.fugr_functions == [("Z_FUNC", "Function"), ("Z_MISSING", "")]
    assert sources[key("FUGR", "ZFG", "")] == "FUNCTION-POOL zfg."
    assert sources[key("FUGR", "ZFG", "FOO")] == "INCLUDE lzfgfoo."
    assert sources[key("FUGR", "ZFG", "U01")] == "FUNCTION z_func."
    assert "FM Z_MISSING" in capsys.readouterr().out


def test_type_group_parser_and_collector_cover_valid_empty_and_length_errors(tmp_path, capsys):
    xml_path = tmp_path / "ztype.type.xml"
    xml_path.write_text("<ROOT><DDTEXT>Type &amp; text</DDTEXT></ROOT>")
    assert parse_type_xml(xml_path) == {"DDTEXT": "Type & text"}
    xml_path.write_text("<ROOT><DDTEXT /></ROOT>")
    assert parse_type_xml(xml_path) == {"DDTEXT": ""}
    assert parse_type_xml(tmp_path / "missing.xml") == {}

    xml_path.write_text("<ROOT><DDTEXT>Type text</DDTEXT></ROOT>")
    (tmp_path / "ztype.type.abap").write_text("TYPE-POOLS ztype.")
    sources = collect_type_sources(
        tmp_path,
        "ZTYPE",
        "ztype",
        key,
        lambda name: f"* boilerplate {name}",
        SourceSet,
    )
    assert sources.type_meta == {"DDTEXT": "Type text"}
    assert sources[key("TYPE", "ZTYPE", "C")] == "* boilerplate ZTYPE\nTYPE-POOLS ztype."
    assert sources[key("TYPE", "ZTYPE", "TT")] == ""

    empty = collect_type_sources(tmp_path, "ZEMP", "missing", key, lambda _: "", SourceSet)
    assert empty[key("TYPE", "ZEMP", "TT")] == ""
    assert "missing.type.xml" in capsys.readouterr().out
    with pytest.raises(ValueError, match="too long"):
        collect_type_sources(tmp_path, "TOOLONG", "toolong", key, lambda _: "", SourceSet)
