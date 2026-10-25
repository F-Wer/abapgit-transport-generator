from pathlib import Path

from transport_object_scanner import detect_object_type


def touch(src_dir: Path, name: str) -> None:
    (src_dir / name).write_text("", encoding="utf-8")


def detected(src_dir: Path) -> list[tuple[str, str]]:
    return [(item["type"], item["name"]) for item in detect_object_type(src_dir)]


def test_detects_supported_objects_and_namespace_names(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    touch(src, "z_report.prog.xml")
    touch(src, "#acme#domain.doma.xml")
    touch(src, "#acme#service.sicf.xml")
    touch(src, "z_class.clas.xml")
    touch(src, "z_class.clas.testclasses.abap")

    assert detected(src) == [
        ("DOMA", "/ACME/DOMAIN"),
        ("SICF", "#ACME#SERVICE"),
        ("CLAS", "Z_CLASS"),
        ("PROG", "Z_REPORT"),
    ]


def test_includes_are_independent_programs_and_class_test_classes_are_ignored(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    for name in (
        "z_report.prog.xml",
        "z_report_top.prog.xml",
        "z_report_f01.prog.xml",
        "z_report_scr.prog.xml",
        "z_report_t99.prog.xml",
        "z_class.clas.testclasses.xml",
    ):
        touch(src, name)

    assert detected(src) == [("PROG", name) for name in (
        "Z_REPORT", "Z_REPORT_F01", "Z_REPORT_SCR", "Z_REPORT_T99", "Z_REPORT_TOP")]


def test_returns_no_objects_for_empty_directory(tmp_path: Path) -> None:
    assert detect_object_type(tmp_path) == []
