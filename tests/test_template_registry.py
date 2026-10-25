"""Template directory loading: validation, selection and CLI use."""

import json
import shutil
import sys

import pytest

import abapgit_to_transport as generator
import transport_templates as templates
from transport_templates import (
    TEMPLATES,
    TemplateError,
    check_templates,
    configure_templates,
    load_manifest,
)


# Copied templates come from the directory configured for this test run
# (ABAPGIT_TRANSPORT_TEMPLATES or the bundled default), read before any
# test resets the configuration.
_SOURCE_DIR = templates.template_dir()


@pytest.fixture(autouse=True)
def default_templates(monkeypatch):
    monkeypatch.delenv(templates.ENV_VAR, raising=False)
    configure_templates(None)
    yield
    configure_templates(None)


def _user_dir(tmp_path, key="PROG", **overrides):
    """A user template directory holding a copy of one bundled template."""
    source = load_manifest(_SOURCE_DIR)[key]
    directory = tmp_path / "my-templates"
    directory.mkdir()
    for name in ("cofile", "data"):
        shutil.copy(source[name], directory / f"{name}.bin")
    entry = {"cofile": "cofile.bin", "data": "data.bin",
             "object": source["object"], "request": source["request"],
             "description": source["description"]}
    entry.update(overrides)
    (directory / "templates.json").write_text(json.dumps({key: entry}), encoding="utf-8")
    return directory


def test_missing_manifest_explains_how_to_supply_templates(tmp_path):
    with pytest.raises(TemplateError, match="--templates DIR or ABAPGIT_TRANSPORT_TEMPLATES"):
        load_manifest(tmp_path)


@pytest.mark.templates
@pytest.mark.parametrize(("overrides", "message"), [
    ({"object": ""}, "lacks object"),
    ({"data": "../outside.bin"}, "leaves the template directory"),
    ({"cofile": "absent.bin"}, "not found"),
    ({"descriptions": "text"}, "list of strings"),
])
def test_invalid_entries_are_rejected(tmp_path, overrides, message):
    with pytest.raises(TemplateError, match=message):
        load_manifest(_user_dir(tmp_path, **overrides))


def test_malformed_json_is_rejected(tmp_path):
    (tmp_path / "templates.json").write_text("{", encoding="utf-8")
    with pytest.raises(TemplateError, match="unreadable manifest"):
        load_manifest(tmp_path)


def test_selection_order_is_override_then_environment_then_default(tmp_path, monkeypatch):
    assert templates.template_dir() == templates._DEFAULT_DIR
    monkeypatch.setenv(templates.ENV_VAR, str(tmp_path / "env"))
    assert templates.template_dir() == tmp_path / "env"
    configure_templates(tmp_path / "flag")
    assert templates.template_dir() == tmp_path / "flag"


@pytest.mark.templates
def test_registry_reads_the_configured_directory(tmp_path):
    configure_templates(_user_dir(tmp_path))
    assert list(TEMPLATES) == ["PROG"]
    assert TEMPLATES["PROG"]["data"].name == "data.bin"


@pytest.mark.templates
def test_check_reports_a_request_mismatch(tmp_path):
    problems = check_templates(_user_dir(tmp_path, request="ABCK900001"))
    assert len(problems) == 1 and "manifest says ABCK900001" in problems[0]


@pytest.mark.templates
def test_check_reports_an_export_that_holds_another_object(tmp_path):
    problems = check_templates(_user_dir(tmp_path, object="ZDEMO_OTHER"))
    assert len(problems) == 1 and "manifest expects one PROG 'ZDEMO_OTHER'" in problems[0]


@pytest.mark.templates
def test_check_reports_a_template_without_its_content_tables(tmp_path):
    directory = _user_dir(tmp_path)
    manifest = directory / "templates.json"
    entry = json.loads(manifest.read_text(encoding="utf-8"))["PROG"]
    manifest.write_text(json.dumps({"SUSC": entry}), encoding="utf-8")
    problems = check_templates(directory)
    assert any("SUSC: template lacks TOBC, TOBCT" in p for p in problems)


@pytest.mark.templates
def test_bundled_templates_pass_the_check():
    assert check_templates(_SOURCE_DIR) == []


@pytest.mark.templates
def test_cli_check_templates_exit_codes(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["abapgit_to_transport.py", "--check-templates",
                                      "--templates", str(_user_dir(tmp_path))])
    assert generator.main() == 0
    assert "Templates OK: 1" in capsys.readouterr().out

    monkeypatch.setattr(sys, "argv", ["abapgit_to_transport.py", "--check-templates",
                                      "--templates", str(tmp_path / "none")])
    assert generator.main() == 2


def test_icf_nodes_come_from_the_template_directory(tmp_path):
    from object_handlers.sicf import sicf_object_name

    configure_templates(tmp_path)
    assert templates.icf_nodes() == {}
    with pytest.raises(ValueError, match="not in icf_nodes.json"):
        sicf_object_name("zdemo_svc", {"icf_name": "ZDEMO_SVC", "url": "/demo/parent/"})

    (tmp_path / "icf_nodes.json").write_text(
        json.dumps({"/Demo/Parent/": "abcdefghijklmnopqrstuvwxy"}), encoding="utf-8")
    assert templates.icf_nodes() == {"/demo/parent": "ABCDEFGHIJKLMNOPQRSTUVWXY"}
    assert sicf_object_name("zdemo_svc", {"icf_name": "ZDEMO_SVC", "url": "/demo/parent/"}) \
        == "ZDEMO_SVC      ABCDEFGHIJKLMNOPQRSTUVWXY"


@pytest.mark.templates
def test_malformed_icf_nodes_are_reported_by_the_check(tmp_path):
    directory = _user_dir(tmp_path)
    (directory / "icf_nodes.json").write_text(json.dumps({"/demo": "short"}), encoding="utf-8")
    with pytest.raises(TemplateError, match="25-character GUID"):
        templates.icf_nodes(directory)
    assert any("25-character GUID" in p for p in check_templates(directory))


@pytest.mark.templates
def test_generation_uses_user_templates_and_reports_missing_types(tmp_path, monkeypatch, capsys):
    repo = tmp_path / "repo" / "src"
    repo.mkdir(parents=True)
    (repo / "zdemo_report.prog.xml").write_text(
        "<abapGit><asx:abap xmlns:asx='http://www.sap.com/abapxml'><asx:values>"
        "<PROGDIR><NAME>ZDEMO_REPORT</NAME><SUBC>1</SUBC></PROGDIR>"
        "</asx:values></asx:abap></abapGit>", encoding="utf-8")
    (repo / "zdemo_report.prog.abap").write_text("REPORT zdemo_report.\n", encoding="utf-8")
    out = tmp_path / "out"
    base = ["abapgit_to_transport.py", str(repo.parent), "--request", "ABCK900001",
            "--sid", "ABC", "--output", str(out)]

    monkeypatch.setattr(sys, "argv", base + ["--templates", str(_user_dir(tmp_path))])
    assert generator.main() == 0
    assert (out / "R900001.ABC").is_file()

    other = tmp_path / "other"
    other.mkdir()
    shutil.copytree(_user_dir(other, key="TABL"), tmp_path / "tabl-only")
    monkeypatch.setattr(sys, "argv", base + ["--templates", str(tmp_path / "tabl-only")])
    assert generator.main() == 2
    assert "No template for type PROG" in capsys.readouterr().out
