"""Class and interface member parsing plus SEO row serialization."""

from __future__ import annotations

import re
import struct

from sap_transport_records import Record
from transport_record_renames import RenameRule, replace_in_record, replace_in_row
from transport_source_blocks import extract_class_blocks


_INTF_METHOD_RE = re.compile(
    r"^\s*(?:CLASS-)?METHODS\s+([\w~]+)", re.IGNORECASE | re.MULTILINE)
_CONSTANT_RE = re.compile(
    r"^\s*CONSTANTS\s+([\w~]+)\s+TYPE\s+([\w~/]+)\s+VALUE\s+'([^']*)'",
    re.IGNORECASE | re.MULTILINE)


def parse_interface_members(source: str) -> list[dict]:
    """
    Extract interface members from an .intf.abap source. Every member needs
    a SEOCOMPO/SEOCOMPODF/SEOCOMPOTX row -- constants are components too
    (verified: the real export lists GC_VERSION).
    """
    return _parse_seo_declarations(source)["members"]


# EXPOSURE (SEOCOMPODF, N(1)): '0' private, '1' protected, '2' public.
_SECTION_EXPOSURE = {"PUBLIC": "2", "PROTECTED": "1", "PRIVATE": "0"}
_CLASS_METHODS_RE = re.compile(
    r"^\s*(CLASS-)?METHODS\s+([\w~]+)\b", re.IGNORECASE)
_CLASS_SECTION_RE = re.compile(
    r"^\s*(PUBLIC|PROTECTED|PRIVATE)\s+SECTION\b", re.IGNORECASE)


def parse_class_members(source: str) -> list[dict]:
    """Extract class methods/constants from an ABAP class definition."""
    definition, _implementation = _extract_class_blocks(source)
    if not definition:
        return []
    return _parse_seo_declarations(definition)["members"]


def put_field(payload: bytearray, fields: list, field_name: str,
               value: str) -> None:
    """
    Write one field by NAME into a row -- offset 120 is CMPTYPE in SEOCOMPO
    but LANGU in SEOCOMPOTX, so fixed offsets would clobber the wrong field.
    """
    for fname, off, flen, _ftype in fields or []:
        if fname != field_name or off + flen > len(payload):
            continue
        encoded = value.encode("utf-16-le")[:flen]
        payload[off:off + flen] = (
            encoded + b"\x20\x00" * ((flen - len(encoded)) // 2))
        return


def build_component_row(tmpl_row: Record, rule: RenameRule,
                         member: dict, fields: list = None) -> Record:
    """
    Clone a template SEO row for one interface member. Offsets from the
    template's own nametabs: CMPNAME@60, SEOCOMPO.CMPTYPE@120 ('0' constant /
    '1' method), SEOCOMPODF.ATTVALUE@386, TYPTYPE@664, TYPE@666 (C, 264B each).
    """
    if fields:
        row = replace_in_row(tmpl_row, rule, fields)
    else:
        row = replace_in_record(tmpl_row, rule)
    payload = bytearray(row.payload)

    put_field(payload, fields, "CMPNAME", member["name"])
    if member["kind"] == "const":
        put_field(payload, fields, "CMPTYPE", "0")  # 0 = attribute/constant
        put_field(payload, fields, "ATTVALUE", f"'{member['value']}'")
        put_field(payload, fields, "TYPTYPE", "1")
        put_field(payload, fields, "TYPE", member["type"])
    else:
        put_field(payload, fields, "CMPTYPE", "1")  # 1 = method
    put_field(payload, fields, "DESCRIPT", "")      # SAP leaves this empty
    return Record(offset=row.offset, rtype=row.rtype,
                  payload=bytes(payload), fragments=row.fragments)


def build_class_member_row(tmpl_row: Record, rule: RenameRule,
                            member: dict, fields: list,
                            editorder: int) -> Record:
    """
    Clone a template SEO row for one class member.

    Fields are written BY NAME via the nametab (never by fixed offset).
    Method rows additionally carry MTDTYPE (SEOCOMPO) / MTDDECLTYP and
    EXPOSURE (SEOCOMPODF); EDITORDER is an INT4 and is written as binary.
    Everything else keeps the template's values (VERSION, STATE, AUTHOR,
    R3RELEASE, ...). TYPESRC stays empty -- verified against the real
    export: 69/69 method rows carry an empty signature blob, so parameter
    signatures are simply not part of the transport.
    """
    if fields:
        row = replace_in_row(tmpl_row, rule, fields)
    else:
        row = replace_in_record(tmpl_row, rule)
    payload = bytearray(row.payload)

    put_field(payload, fields, "CMPNAME", member["name"])
    if member["kind"] == "const":
        put_field(payload, fields, "CMPTYPE", "0")  # 0 = attribute/constant
        put_field(payload, fields, "ATTVALUE", f"'{member['value']}'")
        put_field(payload, fields, "TYPTYPE", "1")
        put_field(payload, fields, "TYPE", member["type"])
    else:
        put_field(payload, fields, "CMPTYPE", "1")  # 1 = method
        put_field(payload, fields, "MTDTYPE", member.get("mtdtype", "0"))
        put_field(payload, fields, "MTDDECLTYP",
                   member.get("mtddecltyp", "0"))
    put_field(payload, fields, "EXPOSURE", member.get("exposure", "2"))
    put_field(payload, fields, "DESCRIPT", "")      # SAP leaves this empty
    for fname, off, flen, _ftype in fields or []:
        if fname == "EDITORDER" and flen >= 4 and off + 4 <= len(payload):
            payload[off:off + 4] = struct.pack(">I", editorder)
            break
    return Record(offset=row.offset, rtype=row.rtype,
                  payload=bytes(payload), fragments=row.fragments)
