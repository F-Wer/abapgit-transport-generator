"""Compatibility tests for extracted message-class regeneration helpers."""

import abapgit_to_transport as legacy
from transport_regenerators import messages


def test_message_class_helpers_remain_legacy_compatibility_exports() -> None:
    assert legacy._fix_msag_language_key is messages.fix_msag_language_key
    assert legacy._regenerate_msag_rows is messages.regenerate_msag_rows
