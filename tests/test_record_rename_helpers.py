"""Characterization tests for generic transport record rename helpers."""

from abapgit_to_transport import (
    A_DEVCLASS_LEN,
    A_DEVCLASS_OFF,
    RenameRule,
    _apply_rename_to_key,
    _rename_a_record,
    _rename_h_key,
    _rename_key_preserving_width,
    _replace_in_record,
    _replace_in_row,
)
from sap_transport_records import Record, u16
from transport_record_renames import (
    RenameRule as ModuleRenameRule,
    rename_a_record,
    replace_in_record,
    replace_in_row,
)


def _rule() -> RenameRule:
    return RenameRule(
        old_name="Z_OLD",
        new_name="Z_NEW_LONG",
        old_request="DEVK900001",
        new_request="DEVK900002",
        old_task="DEVK900001",
        new_task="DEVK900002",
        old_descs=["Z OLD"],
        new_desc="Z NEW LONG",
        fm_pairs=[("Z_OLD_FM", "Z_NEW_FM")],
    )


def test_fixed_width_row_rename_keeps_following_fields_in_place() -> None:
    fields = [("NAME", 0, 30, "C"), ("LANGU", 30, 2, "C")]
    payload = "Z_OLD".ljust(15).encode("utf-16-le") + "D".ljust(1).encode("utf-16-le")
    row = _replace_in_row(Record(0, " ", payload, 1), _rule(), fields)
    assert u16(row.payload[:30]).rstrip() == "Z_NEW_LONG"
    assert u16(row.payload[30:32]) == "D"


def test_key_helpers_preserve_padding_wildcards_and_repos_suffixes() -> None:
    rule = _rule()
    assert _rename_key_preserving_width("Z_OLD     *", rule) == "Z_NEW_LONG*"
    assert _apply_rename_to_key("Z_OLD=========================TT", rule) == "Z_NEW_LONG".ljust(30, "=") + "TT"


def test_h_and_a_records_keep_record_shape_and_package_offset() -> None:
    rule = _rule()
    h_payload = b"ATAB    " + b" " * 40 + b"Z_OLD     *".ljust(32)
    original_h = Record(0, "H", h_payload, 1)
    renamed_h = _rename_h_key(original_h, original_h, rule)
    assert renamed_h.payload[48:].decode("latin-1").rstrip() == "Z_NEW_LONG*"

    a_text = ("R3TRPROG" + "Z_OLD".ljust(50) + "DEV".ljust(10) +
              "DEVELOPER".ljust(13) + "ZOLD".ljust(30))
    original_a = Record(0, "A", a_text.encode("utf-16-le"), 1)
    renamed_a = _rename_a_record(original_a, rule, package="ZNEW")
    decoded = u16(renamed_a.payload)
    assert decoded[8:58].rstrip() == "Z_NEW_LONG"
    assert decoded[A_DEVCLASS_OFF:A_DEVCLASS_OFF + A_DEVCLASS_LEN].rstrip() == "ZNEW"


def test_generic_record_rename_preserves_fixed_byte_length() -> None:
    record = Record(0, " ", "Z_OLD DEVK900001 Z OLD".encode("utf-16-le"), 1)
    renamed = _replace_in_record(record, _rule())
    assert len(renamed.payload) == len(record.payload)


def test_record_rename_helpers_remain_compatibly_reexported() -> None:
    assert RenameRule is ModuleRenameRule
    assert _replace_in_row is replace_in_row
    assert _replace_in_record is replace_in_record
    assert _rename_a_record is rename_a_record
