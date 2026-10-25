"""Assembly helpers for SAP transport record streams."""

from sap_transport_records import Record, u16
from sap_transport_writer import (
    Container,
    ContainerBlock,
    block_checksum,
    build_container,
    compress_stream,
    serialize_stream,
)


def set_object_counter(record: Record, counter: int) -> Record:
    """Set the six-digit AS4POS-style counter before the R3TR marker."""
    payload = bytearray(record.payload)
    marker = "R3TR".encode("utf-16-le")
    index = payload.find(marker)
    if index < 12:
        raise ValueError(f"no R3TR marker in record {record.rtype!r}")
    payload[index - 12 : index] = f"{counter:06d}".encode("utf-16-le")
    return Record(
        offset=record.offset,
        rtype=record.rtype,
        payload=bytes(payload),
        fragments=record.fragments,
    )


def drop_task_and_renumber(records: list) -> None:
    """Drop inherited CORR/RELE rows and renumber a multi-object transport."""
    from transport_record_helpers import find_block

    block = find_block(records, "E071")
    if block is None or not block[1]:
        raise ValueError("no E071 block to normalize")

    for row_index in list(block[1]):
        row = u16(records[row_index].payload)
        if "CORR" in row and "RELE" in row:
            del records[row_index]

    block = find_block(records, "E071")
    if block is None:
        raise ValueError("E071 block lost during normalization")
    for position, row_index in enumerate(block[1], start=1):
        record = set_object_counter(records[row_index], position)
        payload = bytearray(record.payload)
        payload[310:312] = b"\x20\x00"
        records[row_index] = Record(
            offset=record.offset,
            rtype=record.rtype,
            payload=bytes(payload),
            fragments=record.fragments,
        )

    position = 1
    for index, record in enumerate(records):
        if record.rtype == "C":
            records[index] = set_object_counter(record, position)
            position += 1


def serialize_records(records, container: Container) -> bytes:
    """Serialize records into a checksum-correct R3trans container."""
    stream = serialize_stream(records)
    blocks = compress_stream(stream)
    rebuilt_blocks = [
        ContainerBlock(checksum=block_checksum(block), compressed=block)
        for block in blocks
    ]
    return build_container(
        Container(header_record=container.header_record, blocks=rebuilt_blocks)
    )
