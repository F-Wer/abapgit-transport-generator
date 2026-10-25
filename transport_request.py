"""Validation helpers for SAP transport identifiers supplied by the caller."""

from __future__ import annotations

import re

SID_PATTERN = re.compile(r"[A-Z0-9]{3}\Z")
REQUEST_PATTERN = re.compile(r"[A-Z0-9]{3}[A-Z][0-9]{6}\Z")
# DEVCLASS is CHAR 30: a local `$` package, an optional /NAMESPACE/ prefix,
# then letters, digits and underscores.
PACKAGE_PATTERN = re.compile(r"(?:\$|/[A-Z0-9_]+/)?[A-Z0-9_]+\Z")
PACKAGE_LENGTH = 30
# SAP user names are CHAR 12 and are written into fixed-width columns.
USER_PATTERN = re.compile(r"[!-~]{1,12}\Z")


def normalize_package(value: str) -> str:
    """Return a canonical ABAP package name or raise ValueError."""
    package = str(value).strip().upper()
    if len(package) > PACKAGE_LENGTH or not PACKAGE_PATTERN.fullmatch(package):
        raise ValueError(
            f"package {value!r} must be at most {PACKAGE_LENGTH} characters: "
            "an optional $ or /NAMESPACE/ prefix, then letters, digits or _"
        )
    return package


def normalize_author(value: str) -> str:
    """Return a canonical SAP user name or raise ValueError."""
    author = str(value).strip().upper()
    if not USER_PATTERN.fullmatch(author):
        raise ValueError(
            f"author {value!r} must be an SAP user name of 1-12 characters "
            "without spaces"
        )
    return author


def normalize_sid(value: str) -> str:
    """Return a canonical three-character SAP system ID or raise ValueError."""
    sid = str(value).strip().upper()
    if not SID_PATTERN.fullmatch(sid):
        raise ValueError(
            "SAP system ID must contain exactly three uppercase letters or digits"
        )
    return sid


def normalize_request(value: str) -> str:
    """Return a canonical SAP transport request ID or raise ValueError."""
    request = str(value).strip().upper()
    if not REQUEST_PATTERN.fullmatch(request):
        raise ValueError(
            "transport request must match <SID><type><six digits>, e.g. DEVK900001"
        )
    return request


def validate_transport_identity(request: str, sid: str) -> tuple[str, str]:
    """Validate a request and SID pair and ensure both identify one system."""
    normalized_sid = normalize_sid(sid)
    normalized_request = normalize_request(request)
    if normalized_request[:3] != normalized_sid:
        raise ValueError(
            f"transport request {normalized_request!r} belongs to SID "
            f"{normalized_request[:3]!r}, not {normalized_sid!r}"
        )
    return normalized_request, normalized_sid
