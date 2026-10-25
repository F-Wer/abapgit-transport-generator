"""A generated request must name exactly the generated objects.

Regression: SPPF, SUCU and SUSC transports once kept their template's
object key, so importing them replaced and re-registered the template's
(SAP-delivered) object instead of creating the new one. Names are invented.
"""

import pytest

from abapgit_to_transport import collect_sources, generate_transport
from sap_transport_records import Record, iter_records, u16
from sap_transport_writer import decompress_container, parse_container
from transport_native_support import _check_object_list


def _c_record(obj_type: str, name: str) -> Record:
    text = "DEVK900001".ljust(20) + "000001" + "R3TR" + obj_type + name
    return Record(offset=0, rtype="C", payload=text.encode("utf-16-le"), fragments=1)


def test_object_list_check_accepts_the_generated_objects():
    _check_object_list([_c_record("SUSC", "ZDMO")], [("SUSC", "ZDMO")])


def test_object_list_check_rejects_a_template_object():
    with pytest.raises(ValueError, match="key was not replaced"):
        _check_object_list([_c_record("SUSC", "TMPL")], [("SUSC", "ZDMO")])


CASES = [
    ("SPPF", "ZDEMO_PF", "<abapGit><SPPF><TSP08><ORIENT>L</ORIENT><PGWIDTH>297</PGWIDTH>"
                         "<PGWIDTHU>MM</PGWIDTHU></TSP08></SPPF></abapGit>",
     "ZDEMO_PFL"),
    ("SUCU", "ZDEMO_GRP", "<abapGit><SUCU><TBRG_AUTH><item><OBJECT>S_DEMO</OBJECT></item>"
                          "</TBRG_AUTH></SUCU></abapGit>",
     "ZDEMO_GRP".ljust(30) + "S_DEMO"),
    ("SUSC", "ZDMO", "<abapGit><SUSC><TOBC><OCLSS>ZDMO</OCLSS></TOBC>"
                     "<TOBCT><LANGU>E</LANGU><CTEXT>Demo class</CTEXT></TOBCT></SUSC></abapGit>",
     "ZDMO"),
]


@pytest.mark.templates
@pytest.mark.parametrize(("obj_type", "name", "xml", "key"), CASES, ids=[c[0] for c in CASES])
def test_generated_request_names_the_new_object(tmp_path, obj_type, name, xml, key):
    from transport_native_support import _transport_object_name

    src = tmp_path / "src"
    src.mkdir()
    (src / f"{name.lower()}.{obj_type.lower()}.xml").write_text(xml, encoding="utf-8")
    sources = collect_sources(src, obj_type, name)
    transport_name = _transport_object_name(obj_type, name, sources)
    assert transport_name == key
    data, _ = generate_transport(obj_type, transport_name, sources, "DEVK900001",
                                 package="ZDEMO")
    records = iter_records(decompress_container(parse_container(data)))
    assert [u16(r.payload)[30:].rstrip() for r in records if r.rtype == "C"] == [
        obj_type + key.rstrip()]
