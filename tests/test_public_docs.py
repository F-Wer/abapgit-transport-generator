"""Keep the public support page in step with the registry."""

import re
from pathlib import Path

from transport_object_registry import OBJECT_FILE_RULES

SUPPORT = Path(__file__).resolve().parents[1] / "docs" / "support.md"


def test_support_page_lists_exactly_the_registered_types():
    listed = set(re.findall(r"^\| ([A-Z0-9]{4}) \|", SUPPORT.read_text(encoding="utf-8"), re.M))
    # PROG is detected from .prog.xml by the scanner, not by a file rule.
    assert listed == {rule.object_type for rule in OBJECT_FILE_RULES} | {"PROG"}
