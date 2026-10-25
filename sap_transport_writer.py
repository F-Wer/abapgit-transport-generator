#!/usr/bin/env python3
"""
sap_transport_writer.py

Serialization (writing) side of the SAP transport data-file format, plus the
round-trip gates that prove the writer is exactly inverse to the parser.

Run this against a known-good reference file before trusting any generated
transport:

    python sap_transport_writer.py --roundtrip R900001.DEV

CONTAINER FORMAT (solved)
-------------------------
An R<nnnnn>.<SID> data file is:

    [header record: 4B length + 1B cont + 1B type 'T' + payload]
    repeat per compressed block:
        [4B big-endian length = 9 + len(compressed)]
        [4B checksum        ]   <- block_checksum(), see below
        [compressed block   ]   <- 8B SAP compression header + LZH payload
        [1B 0x00 trailer    ]

Verified on both reference pairs: `len(header record) + sum(9 + len(block))`
equals the file size exactly, and every trailer byte is 0x00. R3trans
compresses the logical stream in fixed **16384-byte** chunks (every block
declares 16384 uncompressed bytes except the last).

RECORD FORMAT
-------------
See sap_transport_records.py. Writing is the mirror image: a logical payload
longer than 500 bytes is split into 500-byte fragments flagged 0x46 'F', with
the remainder in a final fragment flagged 0x20 ' '.

KNOWN UNKNOWNS
--------------
1. ~~The 4-byte per-block value.~~ SOLVED (2026-08-13): it is CRC-32 (IEEE
   polynomial 0x04C11DB7, reflected, init 0x00000000, no final XOR) computed
   over the compressed block **plus its 0x00 trailer byte**. Verified against
   all 38 blocks of 5 real R3trans data files. See `block_checksum()`.
   (R3trans enforces it: a wrong value aborts the import with ETW065
   "check-sum error in datafile", surfaced by tp as rc 16.)

2. Fragmentation of a payload whose length is an exact multiple of 500.
   No such record exists in either reference file (0 of 25,030), so it is
   undetermined whether R3trans emits a trailing empty final fragment or ends
   on the last 'F' fragment. This module ends on a final ' ' fragment
   carrying the full 500 bytes; `FRAGMENT_EXACT_MULTIPLE_EMITS_EMPTY_TAIL`
   switches to the other convention if that turns out to be wrong.
"""

from __future__ import annotations

import argparse
import struct
import sys
from dataclasses import dataclass
from pathlib import Path

import pysapcompress

CONT_LAST = 0x20
CONT_MORE = 0x46
FRAGMENT_PAYLOAD = 500
BLOCK_UNCOMPRESSED = 16384
TRAILER = b"\x00"
FRAMING_OVERHEAD = 9  # 4B length + 4B checksum + 1B trailer

# See "KNOWN UNKNOWNS" 2. Leave False unless a reference export proves otherwise.
FRAGMENT_EXACT_MULTIPLE_EMITS_EMPTY_TAIL = False


# --------------------------------------------------------------------------
# Record layer
# --------------------------------------------------------------------------

def serialize_record(rtype: str, payload: bytes) -> bytes:
    """
    Emit one logical record as its physical fragments. Inverse of
    sap_transport_records.iter_records().
    """
    type_byte = ord(rtype)
    out = bytearray()
    off = 0
    remaining = len(payload)

    while remaining > FRAGMENT_PAYLOAD or (
        remaining == FRAGMENT_PAYLOAD and FRAGMENT_EXACT_MULTIPLE_EMITS_EMPTY_TAIL
    ):
        chunk = payload[off:off + FRAGMENT_PAYLOAD]
        out += struct.pack(">I", 6 + len(chunk))
        out.append(CONT_MORE)
        out.append(type_byte)
        out += chunk
        off += FRAGMENT_PAYLOAD
        remaining -= FRAGMENT_PAYLOAD

    chunk = payload[off:]
    out += struct.pack(">I", 6 + len(chunk))
    out.append(CONT_LAST)
    out.append(type_byte)
    out += chunk
    return bytes(out)


def serialize_stream(records) -> bytes:
    """Serialize an iterable of parsed Records back into the logical stream."""
    out = bytearray()
    for r in records:
        out += serialize_record(r.rtype, r.payload)
    return bytes(out)


# --------------------------------------------------------------------------
# Container layer
# --------------------------------------------------------------------------

@dataclass
class ContainerBlock:
    checksum: int
    compressed: bytes    # 8-byte SAP compression header + LZH payload

    @property
    def declared_length(self) -> int:
        return pysapcompress._parse_header(self.compressed[:8])[0]


@dataclass
class Container:
    header_record: bytes            # the leading framed 'T' record, verbatim
    blocks: list[ContainerBlock]


def parse_container(data: bytes) -> Container:
    """
    Split a data file into its header record and compressed blocks. Raises if
    the framing does not account for every byte of the file.
    """
    hdr_len = struct.unpack_from(">I", data, 0)[0]
    if hdr_len < 6 or hdr_len > len(data):
        raise ValueError(f"implausible header record length {hdr_len}")
    header_record = data[:hdr_len]

    blocks: list[ContainerBlock] = []
    pos = hdr_len
    while pos < len(data):
        if pos + 8 > len(data):
            raise ValueError(f"truncated block framing at {pos:#x}")
        total = struct.unpack_from(">I", data, pos)[0]
        if total < FRAMING_OVERHEAD or pos + total > len(data):
            raise ValueError(f"bad block length {total} at {pos:#x}")
        checksum = struct.unpack_from(">I", data, pos + 4)[0]
        compressed = data[pos + 8:pos + total - 1]
        trailer = data[pos + total - 1:pos + total]
        if trailer != TRAILER:
            raise ValueError(f"unexpected trailer {trailer.hex()} at {pos:#x}")
        blocks.append(ContainerBlock(checksum=checksum, compressed=compressed))
        pos += total

    if pos != len(data):
        raise ValueError(f"{len(data) - pos} bytes left over after last block")
    return Container(header_record=header_record, blocks=blocks)


def block_checksum(compressed: bytes) -> int:
    """
    SAP's per-block checksum: CRC-32 (IEEE 0x04C11DB7, reflected, init
    0x00000000, no final XOR) over the compressed block plus its 0x00
    trailer byte. Verified against 38 blocks from 5 real R3trans files.
    """
    import zlib
    return zlib.crc32(compressed + TRAILER, 0xFFFFFFFF) ^ 0xFFFFFFFF


def build_container(container: Container) -> bytes:
    """Inverse of parse_container()."""
    out = bytearray(container.header_record)
    for b in container.blocks:
        out += struct.pack(">I", FRAMING_OVERHEAD + len(b.compressed))
        out += struct.pack(">I", b.checksum)
        out += b.compressed
        out += TRAILER
    return bytes(out)


def decompress_container(container: Container) -> bytes:
    """Reassemble the logical stream from a parsed container."""
    out = bytearray()
    for b in container.blocks:
        out += pysapcompress._LZHDecompress(b.compressed).decompress()
    return bytes(out)


def compress_stream(stream: bytes, chunk: int = BLOCK_UNCOMPRESSED) -> "list[bytes]":
    """
    Compress a logical stream into blocks the way R3trans does: fixed
    `chunk`-byte pieces, each LZH-compressed with its own 8-byte header.
    Returns the compressed blocks (header included), without framing.
    """
    blocks = []
    for off in range(0, len(stream), chunk):
        piece = stream[off:off + chunk]
        result = pysapcompress.compress(piece, pysapcompress.ALG_LZH)
        # pysapcompress.compress returns (status, out_length, out_bytes)
        payload = bytes(result[2]) if isinstance(result, tuple) else bytes(result)
        blocks.append(payload)
    return blocks


# --------------------------------------------------------------------------
# Round-trip gates
# --------------------------------------------------------------------------

def gate_a(stream: bytes) -> bool:
    """Record layer: parse -> serialize must be byte-identical."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from sap_transport_records import iter_records

    records = iter_records(stream)
    rebuilt = serialize_stream(records)
    ok = rebuilt == stream
    print(f"  logical records          : {len(records):,}")
    print(f"  re-serialized bytes      : {len(rebuilt):,} (original {len(stream):,})")
    if not ok:
        n = min(len(rebuilt), len(stream))
        first = next((i for i in range(n) if rebuilt[i] != stream[i]), n)
        print(f"  [!] first difference at offset {first:#x}")
        print(f"      original: {stream[first:first+24].hex(' ')}")
        print(f"      rebuilt : {rebuilt[first:first+24].hex(' ')}")
    print(f"  GATE A (record layer)    : {'PASS' if ok else 'FAIL'}")
    return ok


def gate_b1(data: bytes) -> "tuple[bool, Container]":
    """Container layer: parse -> build must be byte-identical."""
    c = parse_container(data)
    rebuilt = build_container(c)
    ok = rebuilt == data
    accounted = len(c.header_record) + sum(FRAMING_OVERHEAD + len(b.compressed)
                                          for b in c.blocks)
    print(f"  header record            : {len(c.header_record)} bytes, "
          f"type {chr(c.header_record[5])!r}")
    print(f"  blocks                   : {len(c.blocks)}")
    print(f"  bytes accounted for      : {accounted:,} of {len(data):,}")
    print(f"  GATE B1 (container)      : {'PASS' if ok else 'FAIL'}")
    return ok, c


def gate_b2(c: Container, stream: bytes) -> bool:
    """
    Compression: our own compressed blocks must decompress back to the exact
    logical stream, and must use the same chunking as R3trans.
    """
    ours = compress_stream(stream)
    rebuilt = bytearray()
    for blk in ours:
        rebuilt += pysapcompress._LZHDecompress(blk).decompress()
    ok = bytes(rebuilt) == stream

    theirs_declared = [b.declared_length for b in c.blocks]
    ours_declared = [pysapcompress._parse_header(b[:8])[0] for b in ours]
    chunking_ok = theirs_declared == ours_declared

    theirs_size = sum(len(b.compressed) for b in c.blocks)
    ours_size = sum(len(b) for b in ours)
    print(f"  our blocks               : {len(ours)} (R3trans: {len(c.blocks)})")
    print(f"  chunk sizes match        : {'yes' if chunking_ok else 'no'}")
    print(f"  our compressed total     : {ours_size:,} bytes "
          f"(R3trans: {theirs_size:,}, ratio {ours_size / max(theirs_size,1):.2f}x)")
    print(f"  decompresses to original : {'yes' if ok else 'no'}")
    print(f"  GATE B2 (compression)    : {'PASS' if ok and chunking_ok else 'FAIL'}")
    return ok and chunking_ok


def roundtrip(path: Path) -> int:
    data = path.read_bytes()
    print(f"=== {path.name} ({len(data):,} bytes)")
    print("\n--- Gate B1: container framing")
    b1, c = gate_b1(data)
    stream = decompress_container(c)
    print(f"  logical stream           : {len(stream):,} bytes")
    print("\n--- Gate A: record layer")
    a = gate_a(stream)
    print("\n--- Gate B2: compression")
    b2 = gate_b2(c, stream)

    print("\n--- Full write path")
    if b1 and a:
        # Rebuild the file end to end, carrying the original checksums through.
        rebuilt_stream = serialize_stream(
            __import__("sap_transport_records").iter_records(stream))
        rebuilt_file = build_container(Container(
            header_record=c.header_record,
            blocks=[ContainerBlock(b.checksum, b.compressed) for b in c.blocks]))
        full = rebuilt_file == data and rebuilt_stream == stream
        print(f"  file rebuilt byte-identical (original blocks): "
              f"{'yes' if full else 'no'}")
    failures = sum(0 if x else 1 for x in (a, b1, b2))
    print(f"\nFAILURES: {failures}")
    return failures


def make_probes(src: Path, outdir: Path) -> None:
    """
    Emit a matrix of probe files for `R3trans -l` to answer two questions
    without needing the checksum algorithm:

      1. Is the 4-byte per-block value actually validated on read?
      2. Does R3trans accept LZH blocks produced by pysapcompress?

    Run `R3trans -l <file>` on each and compare against the original.
    """
    import zlib

    outdir.mkdir(parents=True, exist_ok=True)
    data = src.read_bytes()
    c = parse_container(data)
    stream = decompress_container(c)
    sid = src.suffix.lstrip(".")
    written = []

    # (1) original file with a single checksum bit flipped in block 0 --
    #     isolates "is the checksum checked" from everything else.
    flipped = bytearray(data)
    flipped[len(c.header_record) + 4] ^= 0x01
    p = outdir / f"Rflip01.{sid}"
    p.write_bytes(bytes(flipped))
    written.append((p, "original blocks, block-0 checksum bit flipped"))

    # (2..4) our own compression, three checksum strategies.
    ours = compress_stream(stream)
    strategies = {
        "Rourorig": ("our compression, checksums copied from the original file "
                     "(wrong for our blocks)",
                     lambda i, blk: c.blocks[i].checksum if i < len(c.blocks) else 0),
        "Rourzero": ("our compression, checksums all zero",
                     lambda i, blk: 0),
        "Rourcrc3": ("our compression, checksums = SAP block_checksum()",
                     lambda i, blk: block_checksum(blk)),
    }
    for stem, (desc, fn) in strategies.items():
        cont = Container(header_record=c.header_record,
                         blocks=[ContainerBlock(fn(i, blk), blk)
                                 for i, blk in enumerate(ours)])
        p = outdir / f"{stem}.{sid}"
        p.write_bytes(build_container(cont))
        written.append((p, desc))

    lines = [
        "# R3trans probe matrix",
        "",
        f"Generated from `{src.name}` ({len(data):,} bytes, {len(c.blocks)} blocks).",
        "",
        "Run each through R3trans and record whether it lists the contents cleanly:",
        "",
        "```",
        f"R3trans -l {src.name}      # control: known-good, must succeed",
    ]
    lines += [f"R3trans -l {p.name}" for p, _ in written]
    lines += [
        "```",
        "",
        "| File | What it changes |",
        "| --- | --- |",
        f"| `{src.name}` | nothing — control |",
    ]
    lines += [f"| `{p.name}` | {desc} |" for p, desc in written]
    lines += [
        "",
        "## How to read the result",
        "",
        "- **`Rflip01` fails, control passes** → the 4-byte value *is* validated, so",
        "  the checksum algorithm must be cracked before a writer can emit new blocks.",
        "- **`Rflip01` passes** → the value is not checked (at least not by `-l`), so a",
        "  writer can put anything there and only compression remains in question.",
        "- **Any `Rour*` passes** → pysapcompress's LZH output is acceptable to R3trans,",
        "  which together with Gates A/B1/B2 means the whole write path is viable.",
        "  Whichever strategy passes tells us what to emit.",
        "- **All `Rour*` fail but `Rflip01` passes** → compression is the problem, not the",
        "  checksum; compare `pysapcompress.compress` options against SAP's encoder.",
        "",
        "`R3trans -l` only reads the file and should not need a database connection.",
        "If it insists on one, the same matrix works via a test import.",
    ]
    (outdir / "PROBES.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"Wrote {len(written)} probe files + PROBES.md to {outdir}")
    for p, desc in written:
        print(f"  {p.name:<16} {p.stat().st_size:>8,} bytes  {desc}")


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--roundtrip", type=Path, nargs="*", metavar="DATAFILE",
                    help="reference R<nnnnn>.<SID> file(s) to verify")
    ap.add_argument("--probes", type=Path, metavar="DATAFILE",
                    help="generate an R3trans probe matrix from this reference file")
    ap.add_argument("--outdir", type=Path, default=Path("probes"),
                    help="where --probes writes its files (default ./probes)")
    args = ap.parse_args()

    if not args.roundtrip and not args.probes:
        ap.error("give --roundtrip and/or --probes")

    total = 0
    for p in args.roundtrip or []:
        total += roundtrip(p)
        print()
    if args.probes:
        make_probes(args.probes, args.outdir)
    sys.exit(1 if total else 0)


if __name__ == "__main__":
    main()
