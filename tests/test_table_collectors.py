"""abapGit XML collectors for the table-content object types.

These parse repository XML into the metadata the regenerators consume and
need no templates. Every name below is invented.
"""

import importlib

import pytest


class _SourceSet(dict):
    """Stand-in for the generator's source sets (they carry attributes)."""


def _xml(body: str) -> str:
    return ('<?xml version="1.0" encoding="utf-8"?><abapGit version="v1.0.0">'
            '<asx:abap xmlns:asx="http://www.sap.com/abapxml" version="1.0">'
            f"<asx:values>{body}</asx:values></asx:abap></abapGit>")


CASES = [
    ("cus0", "<CUS0><HEADER><ACTIVITY>ZDEMO_ACT</ACTIVITY><TCODE>ZDEMO</TCODE></HEADER>"
             "<TEXTS><item><SPRAS>E</SPRAS><TEXT>Demo &amp; text</TEXT></item></TEXTS></CUS0>",
     {"header": {"ACTIVITY": "ZDEMO_ACT", "TCODE": "ZDEMO"},
      "texts": [{"SPRAS": "E", "TEXT": "Demo & text"}]}),
    ("cus1", "<CUS1><ACTIVITY_HEADER><ACT_ID>ZDEMO</ACT_ID></ACTIVITY_HEADER>"
             "<ACTIVITY_CUSTOMER_EXIT><EXIT>ZDEMO_EXIT</EXIT></ACTIVITY_CUSTOMER_EXIT>"
             "<ACTIVITY_TITLE><item><SPRAS>E</SPRAS><TEXT>Title</TEXT></item></ACTIVITY_TITLE>"
             "<OBJECTS><item><OBJECTNAME>ZDEMO_OBJ</OBJECTNAME></item></OBJECTS>"
             "<OBJECTS_TITLE><item><TEXT>Object</TEXT></item></OBJECTS_TITLE></CUS1>",
     {"header": {"ACT_ID": "ZDEMO"}, "exit": {"EXIT": "ZDEMO_EXIT"},
      "titles": [{"SPRAS": "E", "TEXT": "Title"}],
      "objects": [{"OBJECTNAME": "ZDEMO_OBJ"}], "object_titles": [{"TEXT": "Object"}]}),
    ("cus2", "<CUS2><HEADER><ATTR_ID>ZDEMO</ATTR_ID></HEADER>"
             "<TITLES><item><TEXT>Attribute</TEXT></item></TITLES>"
             "<COUNTRIES><item><LAND1>DE</LAND1></item></COUNTRIES>"
             "<COMPONENTS><item><COMPONENT>BC</COMPONENT></item></COMPONENTS></CUS2>",
     {"header": {"ATTR_ID": "ZDEMO"}, "titles": [{"TEXT": "Attribute"}],
      "countries": [{"LAND1": "DE"}], "components": [{"COMPONENT": "BC"}]}),
    ("nrob", "<NROB><ATTRIBUTES><OBJECT>ZDEMO_NR</OBJECT><DOMLEN>CHAR10</DOMLEN></ATTRIBUTES>"
             "<TEXT><LANGU>E</LANGU><TXT>Numbers</TXT></TEXT></NROB>",
     {"attributes": {"OBJECT": "ZDEMO_NR", "DOMLEN": "CHAR10"},
      "text": {"LANGU": "E", "TXT": "Numbers"}}),
    ("otgr", "<OTGR><CLS_TYPE_GROUP><NAME>ZDEMO_GRP</NAME></CLS_TYPE_GROUP>"
             "<TEXTS><item><LANGU>E</LANGU><TEXT>Group</TEXT></item></TEXTS>"
             "<ELEMENTS><item><TYPE>CLAS</TYPE></item></ELEMENTS></OTGR>"
             "<PARENTS><item><PARENT>ZDEMO_TOP</PARENT></item></PARENTS>",
     {"header": {"NAME": "ZDEMO_GRP"}, "texts": [{"LANGU": "E", "TEXT": "Group"}],
      "elements": [{"TYPE": "CLAS"}], "parents": [{"PARENT": "ZDEMO_TOP"}]}),
    ("para", "<PARA><TPARA><PARAMID>ZDM</PARAMID></TPARA>"
             "<TPARAT><SPRACHE>E</SPRACHE><PARTEXT>Demo</PARTEXT></TPARAT></PARA>",
     {"tpara": {"PARAMID": "ZDM"}, "tparat": {"SPRACHE": "E", "PARTEXT": "Demo"}}),
    ("pers", "<PERS><PERS_REG><PERS_KEY>ZDEMO</PERS_KEY></PERS_REG>"
             "<PERS_REG_TEXT><TEXT>Settings</TEXT></PERS_REG_TEXT></PERS>",
     {"header": {"PERS_KEY": "ZDEMO"}, "text": {"TEXT": "Settings"}}),
    ("pinf", "<PINF><ATTRIBUTES><INTF_NAME>ZDEMO_IF</INTF_NAME></ATTRIBUTES>"
             "<ELEMENTS><item><ELEM_TYPE>CLAS</ELEM_TYPE><ELEM_KEY>ZCL_DEMO</ELEM_KEY></item>"
             "</ELEMENTS></PINF>",
     {"attributes": {"INTF_NAME": "ZDEMO_IF"},
      "elements": [{"ELEM_TYPE": "CLAS", "ELEM_KEY": "ZCL_DEMO"}]}),
    ("prag", "<PRAG><PRAGMA>ZDEMO</PRAGMA><DESCRIPTION>Demo &lt;pragma&gt;</DESCRIPTION></PRAG>",
     {"PRAGMA": "ZDEMO", "DESCRIPTION": "Demo <pragma>"}),
    ("scvi", "<SCVI><SHDSVCI><SCVARIANT>ZDEMO_V</SCVARIANT></SHDSVCI>"
             "<SHDSVTXCI><item><LANGU>E</LANGU><SCVTEXT>Variant</SCVTEXT></item></SHDSVTXCI>"
             "<SHDSVFVCI><item><FIELDNAME>F1</FIELDNAME></item></SHDSVFVCI>"
             "<SHDGUIXT><item><GUIXT>X</GUIXT></item></SHDGUIXT>"
             "<SHDGXTCODE><item><TCODE>ZDEMO</TCODE></item></SHDGXTCODE></SCVI>",
     {"header": {"SCVARIANT": "ZDEMO_V"}, "texts": [{"LANGU": "E", "SCVTEXT": "Variant"}],
      "values": [{"FIELDNAME": "F1"}], "guixt": [{"GUIXT": "X"}], "tcodes": [{"TCODE": "ZDEMO"}]}),
    ("splo", "<SPLO><TSPLD><PAART>ZDEMO</PAART></TSPLD>"
             "<TSPLT><item><SPRAS>E</SPRAS><PTEXT>Layout</PTEXT></item></TSPLT>"
             "<TSP0P><PDNAME>ZDEMO</PDNAME></TSP0P></SPLO>",
     {"header": {"PAART": "ZDEMO"}, "texts": [{"SPRAS": "E", "PTEXT": "Layout"}],
      "output": {"PDNAME": "ZDEMO"}}),
    ("sppf", "<SPPF><TSP08><PAPART>ZDEMO</PAPART><PWIDTH>210</PWIDTH></TSP08></SPPF>",
     {"PAPART": "ZDEMO", "PWIDTH": "210"}),
    ("sucu", "<SUCU><TBRG_AUTH><item><BRGRU>ZDM</BRGRU></item></TBRG_AUTH>"
             "<TBRG_AUTHT><item><TEXT>Group</TEXT></item></TBRG_AUTHT></SUCU>",
     {"auth": [{"BRGRU": "ZDM"}], "texts": [{"TEXT": "Group"}]}),
    ("susc", "<SUSC><TOBC><OCLSS>ZDM</OCLSS></TOBC><TOBCT><LANGU>E</LANGU></TOBCT></SUSC>",
     {"tobc": {"OCLSS": "ZDM"}, "tobct": {"LANGU": "E"}}),
]


def _collect(tmp_path, kind):
    module = importlib.import_module(f"object_handlers.{kind}")
    return getattr(module, f"collect_{kind}_sources")(tmp_path, "ZDEMO", "zdemo", _SourceSet)


@pytest.mark.parametrize(("kind", "body", "expected"), CASES, ids=[c[0] for c in CASES])
def test_collector_reads_its_tables(tmp_path, kind, body, expected):
    (tmp_path / f"zdemo.{kind}.xml").write_text(_xml(body), encoding="utf-8")
    assert getattr(_collect(tmp_path, kind), f"{kind}_meta") == expected


@pytest.mark.parametrize("kind", [c[0] for c in CASES])
def test_collector_without_xml_returns_empty_metadata(tmp_path, kind):
    meta = getattr(_collect(tmp_path, kind), f"{kind}_meta")
    assert all(not value for value in (meta.values() if isinstance(meta, dict) else [meta]))


def test_splo_accepts_a_single_text_row(tmp_path):
    (tmp_path / "zdemo.splo.xml").write_text(
        _xml("<SPLO><TSPLT><SPRAS>E</SPRAS><PTEXT>Layout</PTEXT></TSPLT></SPLO>"), encoding="utf-8")
    assert _collect(tmp_path, "splo").splo_meta["texts"] == [{"SPRAS": "E", "PTEXT": "Layout"}]


def test_suso_reads_authorization_object_graph(tmp_path):
    (tmp_path / "zdemo.suso.xml").write_text(_xml(
        "<SUSO><TOBJ><OBJCT>ZDEMO</OBJCT></TOBJ><TOBJT><TTEXT>Object</TTEXT></TOBJT>"
        "<TOBJVORFLG><OBJCT>ZDEMO</OBJCT></TOBJVORFLG>"
        "<TACTZ><TACTZ><ACTVT>03</ACTVT></TACTZ></TACTZ>"
        "<TOBJVORDAT><TOBJVORDAT><FIELD>F1</FIELD></TOBJVORDAT></TOBJVORDAT>"
        "<TOBJVOR><TOBJVOR><VALUE>V</VALUE></TOBJVOR></TOBJVOR>"
        "<ABAP_LANGUAGE_VERSION>5</ABAP_LANGUAGE_VERSION></SUSO>"), encoding="utf-8")
    meta = _collect(tmp_path, "suso").suso_meta
    assert meta["tobj"] == {"OBJCT": "ZDEMO"} and meta["tobjt"] == {"TTEXT": "Object"}
    assert meta["flags"] == {"OBJCT": "ZDEMO"}
    assert meta["tactz"] == [{"ACTVT": "03"}]
    assert meta["vordat"] == [{"FIELD": "F1"}] and meta["vor"] == [{"VALUE": "V"}]
    assert meta["abap_language_version"] == "5"


def test_avas_and_avar_read_header_values_and_ids(tmp_path):
    (tmp_path / "zdemo.avas.xml").write_text(_xml(
        "<AVAS><HEADER><GUID>0123</GUID><ATTRIBUTE><NAME>ZDEMO_ATTR</NAME></ATTRIBUTE></HEADER>"
        "<VALUES><item><VALUE>V1</VALUE></item></VALUES></AVAS>"), encoding="utf-8")
    assert _collect(tmp_path, "avas").avas_meta == {
        "header": {"GUID": "0123", "NAME": "ZDEMO_ATTR"}, "values": [{"VALUE": "V1"}]}
    (tmp_path / "zdemo.avar.xml").write_text(_xml(
        "<AVAR><DESCRIPTION>Variant</DESCRIPTION><IDS><item><NAME>ZDEMO</NAME></item>"
        "<item/></IDS></AVAR>"), encoding="utf-8")
    assert _collect(tmp_path, "avar").avar_meta == {"description": "Variant",
                                                    "ids": [{"NAME": "ZDEMO"}]}


def test_generic_table_collectors_accept_direct_and_item_rows(tmp_path):
    (tmp_path / "zdemo.asfc.xml").write_text(_xml(
        "<AIND_STR1><ARCHINDEX>ZDEMO</ARCHINDEX></AIND_STR1>"
        "<AIND_STR1T><item><TEXT>A</TEXT></item><item><TEXT>B</TEXT></item></AIND_STR1T>"),
        encoding="utf-8")
    assert _collect(tmp_path, "asfc").asfc_meta == {
        "AIND_STR1": [{"ARCHINDEX": "ZDEMO"}], "AIND_STR1T": [{"TEXT": "A"}, {"TEXT": "B"}]}
    (tmp_path / "zdemo.aqqu.xml").write_text(_xml(
        "<AQGQCAT><item><NUM>ZDEMO</NUM></item></AQGQCAT><AQGTQ><TEXT>Query</TEXT></AQGTQ>"),
        encoding="utf-8")
    assert _collect(tmp_path, "aqqu").aqqu_meta == {
        "AQGQCAT": [{"NUM": "ZDEMO"}], "AQGTQ": [{"TEXT": "Query"}]}
    (tmp_path / "zdemo.aqsg.xml").write_text(_xml(
        "<AQGSCAT><NUM>ZDEMO</NUM></AQGSCAT><AQGDB><item><RELID>AQ</RELID></item></AQGDB>"),
        encoding="utf-8")
    assert _collect(tmp_path, "aqsg").aqsg_meta == {
        "AQGSCAT": [{"NUM": "ZDEMO"}], "AQGDB": [{"RELID": "AQ"}]}


def test_apis_and_auth_read_their_fields(tmp_path, capsys):
    (tmp_path / "zdemo.apis.xml").write_text(_xml(
        "<APIS><OBJECT_TYPE>CLAS</OBJECT_TYPE><API_STATES><item><STATE>R</STATE></item>"
        "</API_STATES></APIS>"), encoding="utf-8")
    assert _collect(tmp_path, "apis").apis_meta == {"header": {"OBJECT_TYPE": "CLAS"},
                                                    "states": [{"STATE": "R"}]}
    (tmp_path / "zdemo.auth.xml").write_text(_xml("<AUTHX><FIELDNAME>ZDEMO</FIELDNAME></AUTHX>"),
                                             encoding="utf-8")
    assert _collect(tmp_path, "auth").auth_meta == {"FIELDNAME": "ZDEMO"}
    (tmp_path / "zdemo.apis.xml").unlink()
    assert _collect(tmp_path, "apis").apis_meta == {"header": {}, "states": []}
    assert "no <APIS> metadata" in capsys.readouterr().out


@pytest.mark.parametrize("kind", ["asfc", "aqqu", "aqsg", "avar", "avas", "apis", "auth", "prag"])
def test_malformed_xml_is_reported_not_raised(tmp_path, capsys, kind):
    (tmp_path / f"zdemo.{kind}.xml").write_text("<abapGit><unclosed>", encoding="utf-8")
    _collect(tmp_path, kind)
    assert "could not parse" in capsys.readouterr().out
