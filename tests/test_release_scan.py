"""The public-release identifier scan (names here are invented)."""

import json

from tools.release_scan import main


def _banned(tmp_path, *patterns):
    path = tmp_path / "banned.txt"
    path.write_text("# private list\n" + "\n".join(patterns) + "\n", encoding="utf-8")
    return path


def _templates(tmp_path):
    directory = tmp_path / "templates"
    directory.mkdir()
    (directory / "templates.json").write_text(json.dumps({"PROG": {
        "cofile": "k", "data": "r", "object": "ZACME_DONOR",
        "request": "QQQK900001", "description": "Acme donor report"}}), encoding="utf-8")
    return directory


def _tree(tmp_path, files):
    root = tmp_path / "public"
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content) if isinstance(content, bytes) else path.write_text(content, encoding="utf-8")
    return root


def test_clean_tree_passes(tmp_path, capsys):
    root = _tree(tmp_path, {"a.py": "print('hello')\n", "docs/b.md": "# Docs\n"})
    assert main(["--banned", str(_banned(tmp_path, "acmecorp")), str(root)]) == 0
    assert capsys.readouterr().out == ""


def test_banned_text_is_found_case_insensitively(tmp_path, capsys):
    root = _tree(tmp_path, {"a.py": "x = 1\n# made for AcmeCorp\n"})
    assert main(["--banned", str(_banned(tmp_path, "acmecorp")), str(root)]) == 1
    assert "a.py:2: acmecorp" in capsys.readouterr().out


def test_template_identifiers_are_banned(tmp_path, capsys):
    root = _tree(tmp_path, {"a.md": "Uses zacme_donor from qqqk900001.\n"
                                    "An Acme donor report.\nA donor is fine.\n"})
    rc = main(["--banned", str(_banned(tmp_path, "acmecorp")),
               "--templates", str(_templates(tmp_path)), str(root)])
    out = capsys.readouterr().out
    assert rc == 1
    assert "a.md:1: ZACME_DONOR" in out and "a.md:1: QQQK900001" in out
    assert "a.md:2: Acme\\ donor\\ report" in out
    assert "a.md:3" not in out


def test_binaries_and_banned_file_names_are_rejected(tmp_path, capsys):
    root = _tree(tmp_path, {"data.bin": b"\x00\x01", "acmecorp_notes.txt": "ok\n"})
    assert main(["--banned", str(_banned(tmp_path, "acmecorp")), str(root)]) == 1
    out = capsys.readouterr().out
    assert "data.bin: binary file not allowed" in out
    assert "acmecorp_notes.txt: file name matches acmecorp" in out


def test_manifest_exclusions_drop_files_and_directories(tmp_path, capsys, monkeypatch):
    root = _tree(tmp_path, {"pkg/ok.py": "ok\n", "pkg/private.py": "acmecorp\n",
                            "pkg/inner/notes.txt": "acmecorp\n"})
    (root / "manifest.txt").write_text("pkg\n!pkg/private.py\n!pkg/inner\n", encoding="utf-8")
    monkeypatch.chdir(root)
    assert main(["--banned", str(_banned(tmp_path, "acmecorp")),
                 "--manifest", "manifest.txt"]) == 0


def test_manifest_lists_candidates_and_reports_missing_ones(tmp_path, capsys, monkeypatch):
    root = _tree(tmp_path, {"keep.py": "ok\n"})
    manifest = root / "manifest.txt"
    manifest.write_text("# candidates\nkeep.py\nmissing.py  # gone\n", encoding="utf-8")
    monkeypatch.chdir(root)
    assert main(["--banned", str(_banned(tmp_path, "acmecorp")),
                 "--manifest", "manifest.txt"]) == 1
    assert "missing.py: listed but missing" in capsys.readouterr().out
