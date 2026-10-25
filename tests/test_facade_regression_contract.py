"""Characterization contracts for the final compatibility facade."""

from __future__ import annotations

import pytest
import sys

import abapgit_to_transport as facade
from sap_transport_records import iter_records, u16
from sap_transport_writer import decompress_container, parse_container


def _objects(source_dir):
    (source_dir / "z_first.prog.abap").write_text(
        "REPORT z_first.", encoding="utf-8"
    )
    (source_dir / "z_second.intf.abap").write_text(
        "INTERFACE z_second.\nENDINTERFACE.", encoding="utf-8"
    )
    return [
        (
            "PROG",
            "Z_FIRST",
            facade.collect_sources(source_dir, "PROG", "Z_FIRST"),
            "",
        ),
        (
            "INTF",
            "Z_SECOND",
            facade.collect_sources(source_dir, "INTF", "Z_SECOND"),
            "",
        ),
    ]


@pytest.mark.templates
def test_public_generation_api_preserves_multi_object_input_order(tmp_path) -> None:
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    data_bytes, cofile_bytes = facade.generate_transport_multi(
        _objects(source_dir), "DEVK901111", sid="DEV", package="ZFACADE"
    )

    assert cofile_bytes
    records = iter_records(decompress_container(parse_container(data_bytes)))
    object_keys = [u16(record.payload) for record in records if record.rtype == "C"]
    assert len(object_keys) == 2
    assert "Z_FIRST" in object_keys[0]
    assert "Z_SECOND" in object_keys[1]


def test_cli_list_and_empty_repo_paths_are_stable(tmp_path, monkeypatch, capsys) -> None:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    detected = [{"type": "PROG", "name": "Z_LIST"}]
    monkeypatch.setattr(facade, "detect_object_type", lambda _: detected)
    monkeypatch.setattr(sys, "argv", ["abapgit_to_transport.py", str(repo), "--list"])

    assert facade.main() == 0
    assert "PROG   Z_LIST" in capsys.readouterr().out

    monkeypatch.setattr(facade, "detect_object_type", lambda _: [])
    monkeypatch.setattr(sys, "argv", ["abapgit_to_transport.py", str(repo)])

    assert facade.main() == 1
    assert "ERROR: no ABAP objects found" in capsys.readouterr().out


def test_cli_uses_canonical_output_filenames(tmp_path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    output = tmp_path / "output"
    monkeypatch.setattr(
        facade,
        "detect_object_type",
        lambda _: [{"type": "PROG", "name": "Z_FILE"}],
    )
    monkeypatch.setattr(facade, "collect_sources", lambda *_: {})
    monkeypatch.setattr(
        facade,
        "generate_transport_multi",
        lambda *_args, **_kwargs: (b"data", b"cofile"),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "abapgit_to_transport.py",
            str(repo),
            "--request",
            "devk901112",
            "--sid",
            "dev",
            "--output",
            str(output),
        ],
    )

    assert facade.main() == 0
    assert (output / "R901112.DEV").read_bytes() == b"data"
    assert (output / "K901112.DEV").read_bytes() == b"cofile"


def test_generation_api_and_legacy_support_symbols_remain_exported() -> None:
    assert callable(facade.generate_transport)
    assert callable(facade.generate_transport_multi)
    assert callable(facade.collect_sources)
    assert callable(facade._pick_template)
    assert callable(facade._map_function_modules)

    sources = facade.SourceSet()
    assert sources.fugr_areat == ""
    assert sources.fugr_functions == []
