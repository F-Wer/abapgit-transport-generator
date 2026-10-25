import importlib
from pathlib import Path

import pytest
from defusedxml.common import DefusedXmlException

from devc_helpers import parse_devc_xml
from object_handlers.acid import parse_acid_xml


MALICIOUS_XML = """<!DOCTYPE root [
<!ENTITY local SYSTEM "file:///etc/passwd">
]>
<ROOT><DESCRIPTION>&local;</DESCRIPTION><TDEVCT><DDTEXT>&local;</DDTEXT></TDEVCT></ROOT>
"""


def test_xml_parsers_reject_external_entities_without_reading_local_files(tmp_path):
    xml_path = tmp_path / "malicious.xml"
    xml_path.write_text(MALICIOUS_XML, encoding="utf-8")

    assert parse_acid_xml(xml_path) == {"description": ""}
    assert parse_devc_xml(xml_path) == {"description": "", "TDEVC": {}, "TDEVCT": {}}


def test_all_xml_entry_points_use_defusedxml():
    root = Path(__file__).resolve().parents[1]
    modules = (
        "abapgit_to_transport.py",
        "devc_helpers.py",
        "object_handlers/acid.py",
        "object_handlers/amsd.py",
        "object_handlers/apis.py",
        "object_handlers/aplo.py",
        "object_handlers/aqbg.py",
        "object_handlers/aqqu.py",
        "object_handlers/asfc.py",
        "object_handlers/auth.py",
        "object_handlers/avar.py",
        "object_handlers/avas.py",
        "object_handlers/char.py",
        "object_handlers/doma.py",
        "object_handlers/enho.py",
        "object_handlers/enqu.py",
        "object_handlers/msag.py",
        "object_handlers/shlp.py",
        "object_handlers/sicf.py",
        "object_handlers/tabl.py",
        "object_handlers/tobj.py",
        "object_handlers/view.py",
        "object_handlers/xslt.py",
    )

    for relative_path in modules:
        source = (root / relative_path).read_text(encoding="utf-8")
        assert "from defusedxml import ElementTree as ET" in source
        assert "xml.etree.ElementTree" not in source


def test_no_runtime_module_parses_xml_without_defusedxml():
    """Discovered, not listed: a list let 15 newer collectors slip past."""
    root = Path(__file__).resolve().parents[1]
    runtime = [*root.glob("*.py"), *root.glob("object_handlers/*.py"),
               *root.glob("transport_regenerators/*.py")]
    offenders = sorted(p.relative_to(root).as_posix() for p in runtime
                       if not p.name.startswith(("test_", "build_"))
                       and any(api in p.read_text(encoding="utf-8")
                               for api in ("xml.etree", "xml.dom", "xml.sax")))
    assert offenders == []


ENTITY_BOMB = """<?xml version="1.0"?>
<!DOCTYPE root [<!ENTITY a "xxxxxxxxxx"><!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">]>
<abapGit><asx:abap xmlns:asx="http://www.sap.com/abapxml"><asx:values>&b;</asx:values></asx:abap></abapGit>
"""


class _SourceSet(dict):
    """Stand-in for the generator's source sets (they carry attributes)."""


@pytest.mark.parametrize("kind", ["cus0", "cus1", "cus2", "nrob", "otgr", "para", "pers",
                                  "pinf", "prag", "scvi", "splo", "sppf", "sucu", "susc", "suso"])
def test_table_collectors_refuse_entity_declarations(tmp_path, kind):
    module = importlib.import_module(f"object_handlers.{kind}")
    collect = getattr(module, f"collect_{kind}_sources")
    (tmp_path / f"zdemo.{kind}.xml").write_text(ENTITY_BOMB, encoding="utf-8")
    with pytest.raises(DefusedXmlException):
        collect(tmp_path, "ZDEMO", "zdemo", _SourceSet)
