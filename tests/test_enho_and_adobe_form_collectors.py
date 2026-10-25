from __future__ import annotations

from object_handlers.enho import collect_enho_sources, parse_enho_xml
from object_handlers.sfpf import collect_sfpf_sources, parse_sfpf_xml
from object_handlers.sfpi import collect_sfpi_sources, parse_sfpi_xml


class SourceSet(dict):
    pass


def key(*parts: str) -> str:
    return "|".join(parts)


def test_enho_class_enhancement_parser_and_collector_include_method_sources(tmp_path):
    xml_path = tmp_path / "z_impl.enho.xml"
    xml_path.write_text(
        "<ROOT><TOOL>CLASENH</TOOL><SHORTTEXT>Enhancement</SHORTTEXT><CLASS>ZCL_TARGET</CLASS>"
        "<TAB_METHODS><ENHNEWMETH_DATA><METH_HEADER><CMPNAME>DO_IT</CMPNAME>"
        "<DESCRIPT>Run &amp; check</DESCRIPT><EXPOSURE>2</EXPOSURE><STATE>A</STATE>"
        "<EDITORDER>1</EDITORDER><MTDDECLTYP>I</MTDDECLTYP></METH_HEADER>"
        "<METH_PARAM><ENHMETHPARAM><SCONAME>IV_VALUE</SCONAME><DESCRIPT>Input</DESCRIPT>"
        "<EDITORDER>1</EDITORDER><PARPASSTYP>I</PARPASSTYP><TYPTYPE>1</TYPTYPE>"
        "<TYPE>STRING</TYPE></ENHMETHPARAM></METH_PARAM></ENHNEWMETH_DATA></TAB_METHODS></ROOT>"
    )
    parsed = parse_enho_xml(xml_path)
    assert parsed["tool"] == "CLASENH"
    assert parsed["class"] == "ZCL_TARGET"
    assert parsed["methods"] == [{
        "name": "DO_IT", "descript": "Run & check", "exposure": "2", "state": "A",
        "editorder": "1", "mtddecltyp": "I",
        "params": [{
            "sconame": "IV_VALUE", "descript": "Input", "editorder": "1",
            "parpasstyp": "I", "typtype": "1", "type": "STRING",
        }],
    }]

    (tmp_path / "z_impl.enho.em_do_it.abap").write_text("METHOD do_it.")
    sources = collect_enho_sources(
        tmp_path,
        "Z_IMPL",
        "z_impl",
        key,
        lambda name, meta: f"* master {name} {meta['tool']}",
        SourceSet,
    )
    assert sources[key("ENHO", "Z_IMPL", "E")] == "* master Z_IMPL CLASENH"
    assert sources[key("ENHO", "Z_IMPL", "EM001")] == "METHOD do_it."


def test_enho_badi_parser_collects_filter_metadata_and_handles_missing_xml(tmp_path):
    xml_path = tmp_path / "z_badi.enho.xml"
    xml_path.write_text(
        "<ROOT><TOOL>BADI_IMPL</TOOL><SHORTTEXT>Implementation</SHORTTEXT><IMPL>"
        "<ENH_BADI_IMPL_DATA><SPOT_NAME>Z_SPOT</SPOT_NAME><BADI_NAME>Z_BADI</BADI_NAME>"
        "<IMPL_NAME>Z_IMPL</IMPL_NAME><IMPL_CLASS>ZCL_IMPL</IMPL_CLASS><ACTIVE>X</ACTIVE>"
        "<IMPL_SHORTTEXT>BAdI &amp; text</IMPL_SHORTTEXT>"
        "<FILTER_ROOT><ENH_BADIIMPL_FILTER_ROOT><ROOT>R1</ROOT><FILTERS>"
        "<ENH_BADIIMPL_FILTER_ID><FILTER_NAME>COUNTRY</FILTER_NAME><ID>1</ID>"
        "</ENH_BADIIMPL_FILTER_ID></FILTERS></ENH_BADIIMPL_FILTER_ROOT></FILTER_ROOT>"
        "<FILTER_VALUES><ENH_BADIIMPL_FILTER_VALUE><ID>1</ID><FILTER_NAME>COUNTRY</FILTER_NAME>"
        "<FILTER_TYPE>C</FILTER_TYPE><COMPARE>=</COMPARE><FILTER_CHAR_VALUE1>DE</FILTER_CHAR_VALUE1>"
        "<FILTER_NUMERIC_VALUE1>0</FILTER_NUMERIC_VALUE1></ENH_BADIIMPL_FILTER_VALUE></FILTER_VALUES>"
        "</ENH_BADI_IMPL_DATA></IMPL></ROOT>"
    )
    parsed = parse_enho_xml(xml_path)
    assert parsed["methods"] == []
    assert parsed["badi"]["impl_class"] == "ZCL_IMPL"
    assert parsed["badi"]["filter_root"] == [{
        "root": "R1", "filters": [{"name": "COUNTRY", "id": "1"}],
    }]
    assert parsed["badi"]["filter_values"][0]["char_value1"] == "DE"
    assert parse_enho_xml(tmp_path / "missing.xml")["badi"] == {}

    sources = collect_enho_sources(tmp_path, "Z_BADI", "z_badi", key, lambda *_: "", SourceSet)
    assert sources.enho_meta["badi"]["badi_name"] == "Z_BADI"


def test_adobe_form_and_interface_parsers_surface_unsupported_object_references(tmp_path, capsys):
    sfpf_path = tmp_path / "z_form.sfpf.xml"
    sfpf_path.write_text(
        "<asx:values><VERSION>1</VERSION><TYPE>FORM</TYPE><INTERFACE>Z_INTERFACE</INTERFACE>"
        "<OFFLINEHANDLER/><DATAPROVIDER>CLASS</DATAPROVIDER><FRTYPE>P</FRTYPE><CNTSET>X</CNTSET>"
        "<FNTEMB>N</FNTEMB><CONTEXTT><FPCONTEXTT><TEXT>Form &amp; text</TEXT></FPCONTEXTT>"
        "</CONTEXTT><CONTEXT href=\"#o1\"/><LAYOUT href=\"#o2\"/></asx:values>"
    )
    sfpf = parse_sfpf_xml(sfpf_path)
    assert sfpf == {
        "header": {
            "VERSION": "1", "TYPE": "FORM", "INTERFACE": "Z_INTERFACE",
            "OFFLINEHANDLER": "", "DATAPROVIDER": "CLASS", "FRTYPE": "P",
            "CNTSET": "X", "FNTEMB": "N",
        },
        "context_text": "Form & text",
        "has_context_object": True,
        "has_layout_object": True,
        "context_xml": "", "layout_xml": "", "xdp": b"",
    }
    assert collect_sfpf_sources(tmp_path, "Z_FORM", "z_form", SourceSet).sfpf_meta == sfpf
    messages = capsys.readouterr().out
    assert "NOT transported" not in messages
    assert parse_sfpf_xml(tmp_path / "missing.xml")["header"] == {}

    sfpi_path = tmp_path / "z_interface.sfpi.xml"
    sfpi_path.write_text(
        "<asx:values><VERSION>1</VERSION><TYPE>INTERFACE</TYPE>"
        "<INTERFACET><FPINTERFACET><TEXT>Interface text</TEXT></FPINTERFACET></INTERFACET>"
        "<INTERFACE href=\"#o3\"/></asx:values>"
    )
    sfpi = parse_sfpi_xml(sfpi_path)
    assert sfpi == {
        "header": {"VERSION": "1", "TYPE": "INTERFACE"},
        "interface_text": "Interface text",
        "has_interface_object": True,
        "interface_xml": "",
    }
    assert collect_sfpi_sources(tmp_path, "Z_INTERFACE", "z_interface", SourceSet).sfpi_meta == sfpi
    assert "NOT transported" not in capsys.readouterr().out
    assert parse_sfpi_xml(tmp_path / "missing.xml")["header"] == {}
