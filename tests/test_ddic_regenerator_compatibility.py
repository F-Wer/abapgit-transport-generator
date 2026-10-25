"""Compatibility tests for extracted DDIC regeneration helpers."""

import abapgit_to_transport as legacy
from transport_regenerators import ddic


def test_data_element_helpers_remain_legacy_compatibility_exports() -> None:
    assert legacy._apply_dtel_row is ddic.apply_dtel_row
    assert legacy._fix_dtel_ddlanguage_key is ddic.fix_dtel_ddlanguage_key


def test_table_regenerator_remains_a_legacy_export() -> None:
    assert legacy._regenerate_tabl_rows is ddic.regenerate_tabl_rows


def test_view_regenerator_remains_a_legacy_export() -> None:
    assert legacy._regenerate_view_rows is ddic.regenerate_view_rows
