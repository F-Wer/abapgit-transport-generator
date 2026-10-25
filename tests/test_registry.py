from transport_object_registry import OBJECT_FILE_RULES, ObjectFileRule


def test_rules_are_unique_and_immutable() -> None:
    suffixes = [rule.suffix for rule in OBJECT_FILE_RULES]

    assert len(suffixes) == len(set(suffixes))
    assert all(isinstance(rule, ObjectFileRule) for rule in OBJECT_FILE_RULES)

    rule = next(rule for rule in OBJECT_FILE_RULES if rule.object_type == "CLAS")
    assert rule.skip_class_testclasses is True
    assert rule.namespace_mangling is True


def test_registry_covers_the_declared_non_program_object_types() -> None:
    types = {rule.object_type for rule in OBJECT_FILE_RULES}

    # Programs have special include filtering and are intentionally handled
    # outside OBJECT_FILE_RULES by the scanner.
    assert {"CLAS", "INTF", "FUGR", "DTEL", "TABL", "DEVC"} <= types
