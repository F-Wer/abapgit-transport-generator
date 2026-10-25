import pytest

from transport_request import (
    normalize_author,
    normalize_package,
    normalize_request,
    normalize_sid,
    validate_transport_identity,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("$tmp", "$TMP"),
        ("zdemo_devc", "ZDEMO_DEVC"),
        ("/acme/demo_package", "/ACME/DEMO_PACKAGE"),
    ],
)
def test_normalize_package_canonicalizes_valid_names(value, expected):
    assert normalize_package(value) == expected


@pytest.mark.parametrize(
    "value",
    (
        "",
        "Z" * 31,
        "C:/ACME/DEMO",
        "x'; touch /tmp/pwned; echo '",
        "Z$PKG",
        "/ACME/",
        "Z PKG",
    ),
)
def test_normalize_package_rejects_other_values(value):
    with pytest.raises(ValueError, match="package"):
        normalize_package(value)


def test_normalize_author_accepts_sap_user_names():
    assert normalize_author(" developer ") == "DEVELOPER"


@pytest.mark.parametrize("value", ("", "A" * 13, "DEV USER", "DEV\tX"))
def test_normalize_author_rejects_other_values(value):
    with pytest.raises(ValueError, match="author"):
        normalize_author(value)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("dev", "DEV"),
        (" DEV ", "DEV"),
        ("a1b", "A1B"),
    ],
)
def test_normalize_sid_accepts_three_alphanumeric_characters(value, expected):
    assert normalize_sid(value) == expected


@pytest.mark.parametrize("value", ("", "X6", "DEV1", "X-1", "X!1"))
def test_normalize_sid_rejects_other_values(value):
    with pytest.raises(ValueError, match="three uppercase letters or digits"):
        normalize_sid(value)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("devk900900", "DEVK900900"),
        (" DEVw000001 ", "DEVW000001"),
    ],
)
def test_normalize_request_canonicalizes_valid_request_ids(value, expected):
    assert normalize_request(value) == expected


@pytest.mark.parametrize(
    "value",
    ("", "DEVK90090", "DEVK9009000", "DEV!900900", "DEVKABCDEF"),
)
def test_normalize_request_rejects_malformed_values(value):
    with pytest.raises(ValueError, match="transport request must match"):
        normalize_request(value)


def test_validate_transport_identity_requires_request_sid_to_match_selected_sid():
    assert validate_transport_identity("devk900900", "DEV") == ("DEVK900900", "DEV")

    with pytest.raises(ValueError, match="belongs to SID"):
        validate_transport_identity("DEVK900900", "D01")
