"""Type-group transport regeneration helpers."""

from collections.abc import Callable

from sap_transport_records import Record


_helpers: dict[str, Callable] = {}


def configure_type_helpers(**helpers: Callable) -> None:
    """Configure shared facade helpers used by the TYPE implementation."""
    _helpers.update(helpers)


def _helper(name: str) -> Callable:
    try:
        return _helpers[name]
    except KeyError as exc:
        raise RuntimeError(f"TYPE helper {name!r} has not been configured") from exc


def _write_field_by_name(*args, **kwargs):
    return _helper("write_field_by_name")(*args, **kwargs)


def _make_description(*args, **kwargs):
    return _helper("make_description")(*args, **kwargs)


def _make_type_pool_boilerplate(obj_name: str) -> str:
    """
    Synthesize the type group's auto-generated '%_C<name>' include
    ('TYPE-POOL <name> .') from the object's own name -- verified byte-
    exact against the real template export ('TYPE-POOL <name> .'). Same
    "regenerate boilerplate from identity, don't rename a template
    string" pattern _make_enho_master_include_source already established
    for ENHO's master include.
    """
    return f"TYPE-POOL {obj_name} ."


def _apply_type_row(row: Record, fields: list, type_fields: dict,
                    obj_name: str) -> Record:
    """
    Overwrite a DDTYPET row's TYPEGROUP/DDLANGUAGE/DDTEXT. Called AFTER the
    generic per-row rename has already touched TYPEGROUP (via the object
    name substitution every row goes through) -- this fills in content
    that is genuinely new per object: TYPEGROUP set explicitly from the
    object's own name (belt-and-braces, in case the generic rename ever
    misses it), DDLANGUAGE defaulted to 'D' (see _parse_type_xml -- no
    per-object language signal exists in a real .type.xml), and DDTEXT
    from the repo's own <DDTEXT> (falling back to a name-derived
    description when absent, matching DTEL/TTYP's own text-fallback
    convention).
    """
    row = _write_field_by_name(row, fields, "TYPEGROUP", obj_name)
    row = _write_field_by_name(row, fields, "DDLANGUAGE",
                               type_fields.get("DDLANGUAGE") or "D")
    ddtext = type_fields.get("DDTEXT") or _make_description(obj_name)
    row = _write_field_by_name(row, fields, "DDTEXT", ddtext)
    return row


def _fix_type_ddlanguage_key(h_rec: Record, new_lang: str) -> Record:
    """
    DDTYPET's H-record key packs TYPEGROUP + DDLANGUAGE(1) + '*' (verified
    against the real template: '<name>D*' -- TYPEGROUP is exactly 5 chars
    wide with no padding needed, unlike DTEL's 30-char ROLLNAME). The
    generic rename only touches the TYPEGROUP portion, so the language
    character would otherwise still read the template's original language
    -- same class of bug DTEL's D5/TTYP's own fix already addressed for
    their own per-language H-record keys; this is TYPE's own copy of that
    fix (see _fix_dtel_ddlanguage_key / _fix_ttyp_ddlanguage_key).
    """
    if not new_lang:
        return h_rec
    key_area = h_rec.payload[48:]
    text = key_area.decode("latin-1")
    star = text.rfind("*")
    if star < 1:
        return h_rec
    lang_char = text[star - 1]
    if not ("A" <= lang_char <= "Z"):
        return h_rec
    text = text[:star - 1] + new_lang[0] + text[star:]
    payload = bytearray(h_rec.payload)
    payload[48:] = text.encode("latin-1")
    return Record(offset=h_rec.offset, rtype=h_rec.rtype,
                  payload=bytes(payload), fragments=h_rec.fragments)



make_type_pool_boilerplate = _make_type_pool_boilerplate
apply_type_row = _apply_type_row
fix_type_ddlanguage_key = _fix_type_ddlanguage_key
