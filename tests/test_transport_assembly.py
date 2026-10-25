import pytest
from abapgit_to_transport import (
    _drop_task_and_renumber,
    _serialize_records,
    _set_object_counter,
)
from sap_transport_records import Record, iter_records, u16
from sap_transport_writer import decompress_container, parse_container
from transport_assembly import (
    drop_task_and_renumber,
    serialize_records,
    set_object_counter,
)
from transport_templates import TEMPLATES


def test_set_object_counter_rewrites_only_the_as4pos_value() -> None:
    payload = (
        b"x" * 12
        + "000002".encode("utf-16-le")
        + "R3TR".encode("utf-16-le")
        + b"tail"
    )
    record = Record(offset=7, rtype="C", payload=payload)

    updated = set_object_counter(record, 42)

    assert u16(updated.payload[12:24]) == "000042"
    assert updated.payload[24:] == record.payload[24:]
    assert updated.offset == 7


@pytest.mark.templates
def test_serialize_records_preserves_the_decompressed_record_stream() -> None:
    template_data = TEMPLATES["PROG"]["data"].read_bytes()
    container = parse_container(template_data)
    stream = decompress_container(container)

    rebuilt = serialize_records(iter_records(stream), container)

    assert decompress_container(parse_container(rebuilt)) == stream


def test_legacy_generator_assembly_imports_remain_available() -> None:
    assert _set_object_counter is set_object_counter
    assert _drop_task_and_renumber is drop_task_and_renumber
    assert _serialize_records is serialize_records
