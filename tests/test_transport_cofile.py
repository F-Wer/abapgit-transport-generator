import pytest
from transport_cofile import generate_cofile
from transport_templates import TEMPLATES


def _header_tokens(cofile: bytes) -> list[str]:
    return cofile.decode("latin-1").splitlines()[0].split()


@pytest.mark.templates
def test_generate_cofile_updates_import_phase_counters() -> None:
    template = TEMPLATES["PROG"]["cofile"].read_bytes()

    generated = generate_cofile(template, ["DOMA"] * 4 + ["PROG"] * 8)

    assert _header_tokens(generated)[4] == "4"
    assert _header_tokens(generated)[5] == "12"
    assert _header_tokens(generated)[12] == "12"
    assert generated.split(b"\n", 1)[1] == template.split(b"\n", 1)[1]


def test_legacy_generator_import_remains_available() -> None:
    from abapgit_to_transport import _generate_cofile

    assert _generate_cofile is generate_cofile
