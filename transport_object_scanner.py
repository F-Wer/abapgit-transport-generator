"""abapGit repository object detection for transport generation."""

from pathlib import Path

from transport_object_registry import OBJECT_FILE_RULES, ObjectFileRule


def _object_name_from_filename(name: str, suffix: str) -> str:
    return name[:-len(suffix)].replace("#", "/").upper()


def _object_name_for_rule(name: str, rule: ObjectFileRule) -> str:
    stem = name[:-len(rule.suffix)]
    if rule.namespace_mangling:
        return stem.replace("#", "/").upper()
    return stem.upper()


def detect_object_type(src_dir: Path) -> list[dict]:
    """Scan an abapGit src/ directory and return object specs for generation."""
    objects = []
    # abapGit puts sub-packages into sub-folders (PREFIX/FULL folder logic),
    # so objects can live at any depth below the starting folder.
    for file_path in sorted(p for p in src_dir.rglob("*") if p.is_file()):
        name = file_path.name.lower()
        if name.endswith(".prog.xml"):
            obj_name = _object_name_from_filename(name, ".prog.xml")
            # includes (SUBC = I) are R3TR PROG objects of their own
            objects.append({"type": "PROG", "name": obj_name, "xml": file_path})
            continue
        for rule in OBJECT_FILE_RULES:
            if name.endswith(rule.suffix):
                if rule.object_type == "PROG":
                    break
                obj_name = _object_name_for_rule(name, rule)
                if rule.skip_class_testclasses and ".testclasses" in name.lower():
                    break
                objects.append({"type": rule.object_type, "name": obj_name, "xml": file_path})
                break
    return objects


def unsupported_files(src_dir: Path) -> list[Path]:
    """Return abapGit object XML files no generator rule recognizes."""
    known = tuple(rule.suffix for rule in OBJECT_FILE_RULES) + (".prog.xml",)
    files = [p for p in sorted(src_dir.rglob("*")) if p.is_file()]
    names = {p.name.lower() for p in files}
    out = [p for p in files if p.name.lower().endswith(".xml")
           and not p.name.lower().endswith(known)]
    # source files without their object's XML are not detected as objects
    for p in files:
        parts = p.name.lower().split(".")
        if (parts[-1] == "abap" and len(parts) >= 3
                and f"{parts[0]}.{parts[1]}.xml" not in names):
            out.append(p)
    return sorted(out)
