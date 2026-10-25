"""Compatibility tests for extracted metadata and query regenerators."""

import abapgit_to_transport as legacy
from transport_regenerators import metadata, query


def test_checkpoint_group_regenerator_remains_a_legacy_export() -> None:
    assert legacy._regenerate_acid_rows is metadata.regenerate_acid_rows


def test_api_state_regenerator_remains_a_legacy_export() -> None:
    assert legacy._regenerate_apis_rows is metadata.regenerate_apis_rows


def test_application_log_regenerator_remains_a_legacy_export() -> None:
    assert legacy._regenerate_aplo_rows is metadata.regenerate_aplo_rows


def test_query_regenerators_remain_legacy_exports() -> None:
    assert legacy._regenerate_aqbg_rows is query.regenerate_aqbg_rows
    assert legacy._regenerate_aqqu_rows is query.regenerate_aqqu_rows
    assert legacy._regenerate_aqsg_rows is query.regenerate_aqsg_rows
    assert legacy._write_aq_value is query.write_aq_value


def test_catalog_regenerators_remain_legacy_exports() -> None:
    assert legacy._regenerate_amsd_rows is metadata.regenerate_amsd_rows
    assert legacy._regenerate_asfc_rows is metadata.regenerate_asfc_rows


def test_authorization_regenerator_remains_a_legacy_export() -> None:
    assert legacy._regenerate_auth_rows is metadata.regenerate_auth_rows


def test_variant_regenerator_remains_a_legacy_export() -> None:
    assert legacy._regenerate_avar_rows is metadata.regenerate_avar_rows


def test_assignment_regenerator_remains_a_legacy_export() -> None:
    assert legacy._regenerate_avas_rows is metadata.regenerate_avas_rows


def test_classification_regenerator_remains_a_legacy_export() -> None:
    assert legacy._regenerate_char_rows is metadata.regenerate_char_rows
