"""Service-object regeneration helpers."""

from collections.abc import Callable

from sap_transport_records import Record

_helpers: dict[str, Callable] = {}


def configure_sicf_helpers(**helpers: Callable) -> None:
    """Configure shared facade helpers used by the SICF implementation."""
    _helpers.update(helpers)


def _helper(name: str) -> Callable:
    try:
        return _helpers[name]
    except KeyError as exc:
        raise RuntimeError(f"SICF helper {name!r} has not been configured") from exc


def _parse_nametabs(*args, **kwargs):
    return _helper("parse_nametabs")(*args, **kwargs)


def _find_block(*args, **kwargs):
    return _helper("find_block")(*args, **kwargs)


def _write_field_by_name(*args, **kwargs):
    return _helper("write_field_by_name")(*args, **kwargs)


def _write_dd04_field(*args, **kwargs):
    return _helper("write_dd04_field")(*args, **kwargs)


def _blank_row(*args, **kwargs):
    return _helper("blank_row")(*args, **kwargs)


def _replace_rows_in_block(*args, **kwargs):
    return _helper("replace_rows_in_block")(*args, **kwargs)


def _make_description(*args, **kwargs):
    return _helper("make_description")(*args, **kwargs)


# ICFSERVICE columns this module writes itself, or that identify the node.
_ICFSERVICE_OWN_COLUMNS = frozenset(
    ("ICF_NAME", "ICFPARGUID", "ICFNODGUID", "ORIG_NAME", "ICFALTNME",
     "ICFALTNME_ORIG"))
_CHAR_TYPES = frozenset("CNDTLGY")


def _icfservice_from_xml(row: Record, fields: list, values: dict) -> Record:
    """Give every character column its .sicf.xml value or its initial value.

    abapGit omits initial fields and clears the system-maintained ones
    (users, dates, clients, child counts) before serializing, so a column
    missing from the XML must not keep the template node's setting.
    """
    for name, _off, flen, ftype in fields:
        if ftype not in _CHAR_TYPES or name in _ICFSERVICE_OWN_COLUMNS:
            continue
        value = values.get(name, "")
        if not value and ftype in "DT":
            value = "0" * (flen // 2)
        row = _write_dd04_field(row, fields, name, value)
    return row


def regenerate_sicf_rows(records: list, obj_name: str, sicf_meta: dict) -> list:
    """
    Regenerate ICFSERVICE (header)/ICFDOCU (description)/ICFHANDLER (handler
    list, arbitrary count, promoted from a delete-sweep when the repo has
    any) from the repo's .sicf.xml. See the "ICF service (SICF) metadata"
    section above for the full reasoning.
    """
    nametabs = _parse_nametabs(records)

    # --- Split the compound object name into ICF_NAME (15 chars) /
    # ICFPARGUID (25 chars). obj_name comes straight from the repo's
    # filename (see detect_object_type) so this split is always exactly
    # right for a real abapGit-produced repo; a hand-edited repo with a
    # differently-shaped filename falls back to keeping the template's own
    # ICFPARGUID, with a clear warning rather than silently guessing. ---
    if len(obj_name) == 40:
        name_part = obj_name[:15].rstrip()
        guid_part = obj_name[15:]
    else:
        name_part = obj_name.strip()[:15]
        guid_part = None
        print(f"  WARNING: SICF object name {obj_name!r} is not the "
              f"expected 40-char compound shape (15-char name + 25-char "
              f"parent-guid hash) -- ICFPARGUID cannot be derived from it, "
              f"keeping the template's own value (see docs/sicf-support.md)")

    icf_name = sicf_meta.get("icf_name") or name_part
    orig_name = sicf_meta.get("orig_name") or icf_name
    ddlanguage = (sicf_meta.get("ddlanguage") or "D")[:1] or "D"
    ddtext = sicf_meta.get("ddtext") or _make_description(icf_name)
    handlers = sicf_meta.get("handlers") or []

    # --- ICFSERVICE: single header row. ---
    icfservice_fields = nametabs.get("ICFSERVICE")
    icfservice_blk = _find_block(records, "ICFSERVICE")
    if icfservice_blk is not None and icfservice_fields:
        for ridx in icfservice_blk[1]:
            row = _icfservice_from_xml(records[ridx], icfservice_fields,
                                       sicf_meta.get("icfservice") or {})
            row = _write_field_by_name(row, icfservice_fields,
                                       "ICF_NAME", icf_name)
            row = _write_field_by_name(row, icfservice_fields, "ORIG_NAME",
                                       orig_name)
            if guid_part is not None:
                row = _write_field_by_name(row, icfservice_fields,
                                           "ICFPARGUID", guid_part)
                # the node's own GUID: the template's would be shared by
                # every generated service
                row = _write_field_by_name(row, icfservice_fields,
                                           "ICFNODGUID",
                                           sicf_node_guid(obj_name))
            if sicf_meta.get("icfaltnme"):
                row = _write_field_by_name(row, icfservice_fields,
                                           "ICFALTNME", sicf_meta["icfaltnme"])
                row = _write_field_by_name(
                    row, icfservice_fields, "ICFALTNME_ORIG",
                    sicf_meta.get("icfaltnme_orig") or sicf_meta["icfaltnme"])
            records[ridx] = row
    elif icfservice_fields is None:
        print("  WARNING: template has no ICFSERVICE nametab -- "
              "service header cannot be regenerated")

    # --- ICFDOCU: single row, description text. ---
    icfdocu_fields = nametabs.get("ICFDOCU")
    icfdocu_blk = _find_block(records, "ICFDOCU")
    if icfdocu_blk is not None and icfdocu_fields:
        for ridx in icfdocu_blk[1]:
            row = _write_field_by_name(records[ridx], icfdocu_fields,
                                       "ICF_NAME", icf_name)
            if guid_part is not None:
                row = _write_field_by_name(row, icfdocu_fields, "ICFPARGUID",
                                           guid_part)
            row = _write_field_by_name(row, icfdocu_fields, "ICF_LANGU",
                                       ddlanguage)
            row = _write_field_by_name(row, icfdocu_fields, "ICF_DOCU", ddtext)
            records[ridx] = row

    # --- ICFHANDLER: the real reference object has none, so the template
    # carries only a 0-row '00DELL' delete-sweep block for this table (see
    # the module docstring's "ICFHANDLER" note). When the repo supplies
    # handlers, promote that block to '00REPC' and populate it -- mirrors
    # TOBJ's own OBJT delete-sweep-to-insert promotion. Left as the
    # template's own 0-row DELL block when the repo has none, matching the
    # real reference object's own shape exactly. ---
    icfhandler_fields = nametabs.get("ICFHANDLER")
    icfhandler_blk = _find_block(records, "ICFHANDLER")
    if handlers and icfhandler_blk is not None and icfhandler_fields:
        h_idx, row_idxs, e_idx = icfhandler_blk
        new_rows = []
        for h in handlers:
            row = _blank_row(icfhandler_fields)
            row = _write_field_by_name(row, icfhandler_fields, "ICF_NAME",
                                       icf_name)
            if guid_part is not None:
                row = _write_field_by_name(row, icfhandler_fields,
                                           "ICFPARGUID", guid_part)
            row = _write_dd04_field(row, icfhandler_fields, "ICFORDER",
                                    h.get("ICFORDER") or "1")
            row = _write_field_by_name(row, icfhandler_fields, "ICFTYP",
                                       h.get("ICFTYP", ""))
            row = _write_field_by_name(row, icfhandler_fields, "ICFHANDLER",
                                       h.get("ICFHANDLER", ""))
            new_rows.append(row)
        payload = bytearray(records[h_idx].payload)
        payload[38:44] = b"00REPC"
        records[h_idx] = Record(offset=records[h_idx].offset,
                                rtype=records[h_idx].rtype,
                                payload=bytes(payload),
                                fragments=records[h_idx].fragments)
        _replace_rows_in_block(records, (h_idx, row_idxs, e_idx), new_rows)
        print(f"  SICF handlers for {obj_name}: {len(new_rows)} "
              f"(template had a 0-row delete-sweep only, promoted to insert)")
    elif handlers:
        print("  WARNING: template has no ICFHANDLER block -- "
              "handlers cannot be regenerated")

    return records
