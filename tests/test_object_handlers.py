from pathlib import Path

from object_handlers.acid import collect_acid_sources, parse_acid_xml
from object_handlers.doma import collect_doma_sources, parse_doma_xml
from object_handlers.tobj import collect_tobj_sources, parse_tobj_xml


class SourceSet:
    pass


def write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_acid_parser_and_collector(tmp_path: Path, capsys) -> None:
    path = write(
        tmp_path / "z_checkpoint.acid.xml",
        "<abapGit><DESCRIPTION>A &amp; B</DESCRIPTION></abapGit>",
    )

    assert parse_acid_xml(path) == {"description": "A & B"}
    sources = collect_acid_sources(tmp_path, "Z_CHECKPOINT", "z_checkpoint", SourceSet)
    assert sources.acid_meta == {"description": "A & B"}

    sources = collect_acid_sources(tmp_path, "Z_MISSING", "z_missing", SourceSet)
    assert sources.acid_meta == {"description": ""}
    assert "no <DESCRIPTION>" in capsys.readouterr().out


def test_doma_parser_reads_header_and_fixed_values(tmp_path: Path, capsys) -> None:
    path = write(
        tmp_path / "z_domain.doma.xml",
        """
        <abapGit>
          <DD01V><DOMNAME>Z_DOMAIN</DOMNAME><DATATYPE>CHAR</DATATYPE><LENG>4</LENG></DD01V>
          <DD07V_TAB>
            <DD07V><DOMNAME>Z_DOMAIN</DOMNAME><VALPOS>0001</VALPOS><DOMVALUE_L>A</DOMVALUE_L></DD07V>
          </DD07V_TAB>
        </abapGit>
        """,
    )

    assert parse_doma_xml(path) == {
        "header": {"DATATYPE": "CHAR", "LENG": "4"},
        "values": [{"VALPOS": "0001", "DOMVALUE_L": "A"}],
    }
    assert collect_doma_sources(tmp_path, "Z_DOMAIN", "z_domain", SourceSet).doma_meta["header"]

    assert parse_doma_xml(write(tmp_path / "invalid.doma.xml", "<broken>")) == {
        "header": {},
        "values": [],
    }
    collect_doma_sources(tmp_path, "Z_MISSING", "missing", SourceSet)
    assert "no <DD01V>" in capsys.readouterr().out


def test_tobj_parser_and_collector(tmp_path: Path, capsys) -> None:
    path = write(
        tmp_path / "z_view.tobj.xml",
        """
        <abapGit>
          <OBJH><OBJECTNAME>Z_VIEW</OBJECTNAME></OBJH>
          <OBJT><OBJECTNAME>Z_VIEW</OBJECTNAME><TEXT>View text</TEXT></OBJT>
          <OBJS><OBJS><OBJECTNAME>Z_VIEW</OBJECTNAME><TABNAME>Z_TABLE</TABNAME></OBJS></OBJS>
          <TOBJ><TDDAT><OBJTAB>Z_TABLE</OBJTAB></TDDAT><TVDIR><AREA>ZA</AREA></TVDIR></TOBJ>
        </abapGit>
        """,
    )

    parsed = parse_tobj_xml(path)
    assert parsed["objh"] == {"OBJECTNAME": "Z_VIEW"}
    assert parsed["objs_rows"] == [{"OBJECTNAME": "Z_VIEW", "TABNAME": "Z_TABLE"}]
    assert parsed["tddat"] == {"OBJTAB": "Z_TABLE"}
    assert parsed["tvdir"] == {"AREA": "ZA"}

    assert collect_tobj_sources(tmp_path, "Z_VIEW", "z_view", SourceSet).tobj_meta["objt"]["TEXT"] == "View text"
    collect_tobj_sources(tmp_path, "Z_MISSING", "missing", SourceSet)
    assert "no <OBJH>" in capsys.readouterr().out
