import sys

import pytest

import abapgit_to_transport as generator


@pytest.fixture
def generator_repo(tmp_path, monkeypatch):
    (tmp_path / "src").mkdir()
    monkeypatch.setattr(
        generator,
        "detect_object_type",
        lambda _src_dir: [{"type": "PROG", "name": "Z_TEST"}],
    )
    return tmp_path


@pytest.mark.parametrize(
    "args",
    [
        ["--request", "DEVK90090", "--sid", "DEV"],
        ["--request", "DEVK900900", "--sid", "D01"],
        ["--sid", "TOOL"],
    ],
)
def test_main_rejects_invalid_transport_identity(generator_repo, monkeypatch, capsys, args):
    monkeypatch.setattr(sys, "argv", ["abapgit_to_transport.py", str(generator_repo), *args])

    assert generator.main() == 2
    assert "ERROR:" in capsys.readouterr().out


@pytest.mark.parametrize(
    "args",
    [
        ["--package", "x'; touch /tmp/pwned; echo '"],
        ["--package", "C:/Program Files/Git/ACME/DEMO"],
        ["--author", "TOO_LONG_USER_NAME"],
    ],
)
def test_main_rejects_invalid_package_or_author(generator_repo, monkeypatch, capsys, args):
    monkeypatch.setattr(
        generator, "generate_transport_multi",
        lambda *_a, **_k: pytest.fail("generation must not start"))
    monkeypatch.setattr(sys, "argv", ["abapgit_to_transport.py", str(generator_repo),
                                      "--request", "DEVK900900", *args])

    assert generator.main() == 2
    assert "ERROR:" in capsys.readouterr().out


def test_main_canonicalizes_valid_identity_before_generating_files(
    generator_repo, monkeypatch, tmp_path
):
    output_dir = tmp_path / "output"
    captured = {}

    monkeypatch.setattr(generator, "collect_sources", lambda *_args: {})

    def generate(objects, request, *, sid, package, language="", author=""):
        captured["objects"] = objects
        captured["request"] = request
        captured["sid"] = sid
        captured["package"] = package
        return b"data", b"cofile"

    monkeypatch.setattr(generator, "generate_transport_multi", generate)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "abapgit_to_transport.py",
            str(generator_repo),
            "--request",
            "devk900900",
            "--sid",
            "dev",
            "--output",
            str(output_dir),
        ],
    )

    assert generator.main() == 0
    assert captured["request"] == "DEVK900900"
    assert captured["sid"] == "DEV"
    assert captured["package"] == ""
    assert (output_dir / "R900900.DEV").read_bytes() == b"data"
    assert (output_dir / "K900900.DEV").read_bytes() == b"cofile"
