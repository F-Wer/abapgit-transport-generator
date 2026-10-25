#!/usr/bin/env python3
"""
sap_transport_decoder.py

Reusable analyzer for SAP transport files (the K<nnnnn>.<SID> "cofile" and
R<nnnnn>.<SID> "data file" pair found in /usr/sap/trans/{cofiles,data}).

WHAT IT DOES
------------
1. Cofile (K-file):
   Plain ASCII. Parses the header line and the per-step log lines
   (system / step-code / return-code / timestamp / host / user).

2. Data file (R-file):
   Starts with a small plain-text/binary framing record, then a sequence
   of SAP-compressed blocks. Each block is:

       [ framing: 4-byte length + N-byte payload + 1 trailer byte ]
       [ 8-byte SAP compression header: <4B out_len><1B alg><2B magic 1F9D><1B extra> ]
       [ LZH-compressed payload ]

   This script walks the whole file block by block, decompresses every
   block with pysap's LZH implementation, and reassembles the full
   R3trans stream. It also extracts the "NDLIB <table>" markers that
   R3trans emits before each table's row data, giving you a quick table
   of what objects/tables the transport actually touched.

DEPENDENCY
----------
Needs pysap's pure-Python LZH/LZC codec (pysapcompress):

    pip install pysap

PyPI's pysap 0.2.0 is a pure-Python py3-none-any wheel shipping
pysapcompress.py, so no compiler and no source install are required.

USAGE
-----
    python3 sap_transport_decoder.py --cofile K900001.DEV --datafile R900001.DEV \
        --out decompressed.bin

    # cofile or datafile alone also work:
    python3 sap_transport_decoder.py --cofile K900001.DEV
    python3 sap_transport_decoder.py --datafile R900001.DEV --out decompressed.bin

NOTE
----
This module only handles the *container*: cofile parsing and block
decompression. For the record layout inside the decompressed stream
(objects, table structures, rows, ABAP source) use the companion module
sap_transport_records.py, which imports decompress_datafile() from here.

Neither module writes transport files yet. See SAP_TRANSPORT_PROJECT.md for
the format spec and what a writer still needs.
"""

from __future__ import annotations

import argparse
import struct
import sys
from dataclasses import dataclass, field
from pathlib import Path

try:
    import pysapcompress
except ImportError:
    sys.exit(
        "Missing dependency 'pysapcompress'.\n"
        "Install it with:\n"
        "  pip install pysap"
    )

MAGIC = b"\x1f\x9d"


# --------------------------------------------------------------------------
# Cofile parsing (plain text)
# --------------------------------------------------------------------------

@dataclass
class CofileStep:
    system: str
    step_code: str
    return_code: str
    timestamp: str
    host: str
    user: str


@dataclass
class CofileInfo:
    header_line: str
    steps: list[CofileStep] = field(default_factory=list)


def parse_cofile(path: Path) -> CofileInfo:
    """Parse a K<nnnnn>.<SID> cofile (plain ASCII, one record per line)."""
    text = path.read_text(errors="replace")
    lines = [l for l in text.splitlines() if l.strip()]

    header_line = lines[0] if lines else ""
    steps: list[CofileStep] = []

    for line in lines:
        parts = line.split()
        # Step lines look like: "DEV f 0000 20260101120000 devhost devadm"
        # i.e. 6 whitespace-separated fields, 3rd field is a 4-digit RC,
        # 4th field is a 14-digit timestamp.
        if len(parts) == 6 and parts[2].isdigit() and len(parts[2]) == 4 \
                and parts[3].isdigit() and len(parts[3]) == 14:
            steps.append(CofileStep(
                system=parts[0],
                step_code=parts[1],
                return_code=parts[2],
                timestamp=parts[3],
                host=parts[4],
                user=parts[5],
            ))

    return CofileInfo(header_line=header_line, steps=steps)


def print_cofile(info: CofileInfo) -> None:
    print("=== Cofile ===")
    print(f"Header : {info.header_line.strip()}")
    print(f"Steps  : {len(info.steps)}")
    for s in info.steps:
        rc_flag = "  <-- non-zero RC" if s.return_code != "0000" else ""
        ts = f"{s.timestamp[:4]}-{s.timestamp[4:6]}-{s.timestamp[6:8]} " \
             f"{s.timestamp[8:10]}:{s.timestamp[10:12]}:{s.timestamp[12:14]}"
        print(f"  {s.system:<6} step={s.step_code:<3} rc={s.return_code} "
              f"{ts} host={s.host} user={s.user}{rc_flag}")


# --------------------------------------------------------------------------
# Data file parsing (compressed blocks)
# --------------------------------------------------------------------------

@dataclass
class BlockInfo:
    index: int
    offset: int
    framing: bytes
    declared_out_len: int
    actual_out_len: int
    compressed_bytes: int


def find_first_header_offset(data: bytes) -> int:
    """
    Locate the offset of the 8-byte compression header that precedes the
    first LZH block. The data file opens with a short text/binary framing
    record (length-prefixed) before the first compressed block; we find it
    by locating the first MAGIC (0x1F9D) occurrence and stepping back 5
    bytes (header layout: 4B len, 1B alg, 2B magic, 1B extra).
    """
    idx = data.find(MAGIC)
    if idx == -1:
        raise ValueError("No SAP compression magic (1F 9D) found in file")
    return idx - 5


def find_next_header_offset(data: bytes, search_from: int, search_limit: int = 32) -> int | None:
    """Find the next block header after `search_from`, or None if not found."""
    idx = data.find(MAGIC, search_from, search_from + search_limit + 2)
    if idx == -1:
        return None
    hdr_start = idx - 5
    if hdr_start < search_from:
        return None
    return hdr_start


def decompress_datafile(data: bytes) -> tuple[bytes, list[BlockInfo]]:
    """
    Walk every compressed block in a data file and return the fully
    reassembled decompressed stream, plus per-block metadata.
    """
    pos = find_first_header_offset(data)
    out = bytearray()
    blocks: list[BlockInfo] = []
    i = 0

    while True:
        hdr_start = find_next_header_offset(data, pos)
        if hdr_start is None:
            break

        framing = bytes(data[pos:hdr_start])

        try:
            declared_len, alg_id, _alg_ver, _extra = pysapcompress._parse_header(
                data[hdr_start:hdr_start + 8]
            )
        except Exception:
            break

        decoder = pysapcompress._LZHDecompress(data[hdr_start:])
        try:
            result = decoder.decompress()
        except Exception as exc:
            print(f"  [!] decompress failed at block {i} (offset {hex(hdr_start)}): {exc}",
                  file=sys.stderr)
            break

        consumed = decoder._reader.bytes_read
        blocks.append(BlockInfo(
            index=i,
            offset=hdr_start,
            framing=framing,
            declared_out_len=declared_len,
            actual_out_len=len(result),
            compressed_bytes=consumed,
        ))
        out += result
        pos = hdr_start + consumed
        i += 1

    trailing = len(data) - pos
    if trailing > 4:
        print(f"  [!] {trailing} unparsed trailing bytes after last block "
              f"(offset {hex(pos)})", file=sys.stderr)

    return bytes(out), blocks


def extract_table_markers(decompressed: bytes) -> list[str]:
    """
    R3trans marks the start of each table's exported rows with an
    'NDLIB <tabname> ...' record. Pulling these out gives a quick summary
    of which tables/objects the transport actually contains data for.
    """
    tables: list[str] = []
    pos = 0
    marker = b"NDLIB"
    while True:
        idx = decompressed.find(marker, pos)
        if idx == -1:
            break
        chunk = decompressed[idx + len(marker):idx + len(marker) + 40]
        name = chunk.split(b" ")[0].strip(b"\x00 ").decode("ascii", "replace")
        # skip leading padding-only splits
        if not name:
            parts = chunk.replace(b"\x00", b" ").split()
            name = parts[0].decode("ascii", "replace") if parts else "?"
        tables.append(name)
        pos = idx + len(marker)
    return tables


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cofile", type=Path, help="Path to the K<nnnnn>.<SID> cofile")
    ap.add_argument("--datafile", type=Path, help="Path to the R<nnnnn>.<SID> data file")
    ap.add_argument("--out", type=Path, help="Where to write the decompressed data stream")
    args = ap.parse_args()

    if not args.cofile and not args.datafile:
        ap.error("Provide --cofile and/or --datafile")

    if args.cofile:
        info = parse_cofile(args.cofile)
        print_cofile(info)
        print()

    if args.datafile:
        data = args.datafile.read_bytes()
        print("=== Data file ===")
        print(f"File size        : {len(data):,} bytes")

        decompressed, blocks = decompress_datafile(data)
        total_compressed = sum(b.compressed_bytes for b in blocks)
        print(f"Blocks decoded   : {len(blocks)}")
        print(f"Decompressed size: {len(decompressed):,} bytes "
              f"(ratio ~{len(decompressed) / max(total_compressed, 1):.1f}:1)")

        tables = extract_table_markers(decompressed)
        if tables:
            print(f"Tables/objects referenced ({len(tables)} markers, "
                  f"{len(set(tables))} distinct):")
            seen = []
            for t in tables:
                if t not in seen:
                    seen.append(t)
            for t in seen:
                print(f"  - {t}")

        if args.out:
            args.out.write_bytes(decompressed)
            print(f"\nWrote decompressed stream to {args.out}")


if __name__ == "__main__":
    main()
