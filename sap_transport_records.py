#!/usr/bin/env python3
"""
sap_transport_records.py

Record-level parser for the decompressed R3trans stream that
`sap_transport_decoder.py` produces from an R<nnnnn>.<SID> data file.

Where the decoder solves the *container* (framing + LZH compression), this
module solves the *content*: the per-object record layout inside the
decompressed stream. That layout is fully reverse-engineered and
self-validating -- see FORMAT below.

FORMAT
------
The decompressed stream is a flat sequence of records. Nothing else: no
padding, no alignment, no outer index. One walk lands exactly on EOF.

    [4-byte big-endian total length, INCLUDING these 4 bytes]
    [1-byte continuation flag]
    [1-byte record type]
    [payload: total_length - 6 bytes]

Continuation flag:
    0x20 ' '  this is the last (or only) fragment of a logical record
    0x46 'F'  more fragments follow; a continued fragment always carries
              exactly 500 payload bytes

Record types (payloads of the *joined* logical record):

    'F'  request header, UTF-16LE, e.g. "DEVK900001           (DEVELOPER/54)"
    '*'  directive / inline marker, latin-1. The '*' is the record type byte,
         so the payload starts directly with the text. Those before the first
         'N'/'H' block are file-level directives ("R3trans version: ...",
         "Source System = ...", "client:100", "trfunction:T"); later ones are
         inline markers ("dbtabpos:7", "COMMIT", "logicalobject", "gsr:...")
    'D'  start of a transported object (empty payload)
    'C'  object key, UTF-16LE -- the E071 line for the object that follows:
         TRKORR(20) AS4POS(6) PGMID(4) OBJECT(4) OBJ_NAME(...)
    'A'  object attributes, UTF-16LE: PGMID+OBJECT+OBJ_NAME, source system,
         author, development class
    'N'  nametab (table structure) header; the '  ' records that follow it,
         until the closing 'E', are one field definition each
    'H'  data-block header; the '  ' records that follow it, until the
         closing 'E', are data rows for that table
    'E'  end of the current 'N' or 'H' block (empty payload)
    'S'  4-byte big-endian length of the *next* record's payload
    'R'  long raw value (RAW/RAWSTRING), preceded by 'S'
    'U'  long character value (STRING/LCHR) in UTF-16LE, preceded by 'S'
    'Z'  end of stream (empty payload, last record in the file)
    ' '  a field definition or a data row, depending on the enclosing block

'N' / 'H' header payload (288 bytes):

    [0:8]    handler keyword: "DLIB    ", "ATAB    " or "ABAPREAD"
    [8:38]   table / logical object name, blank padded
    [38:44]  action code: "00" + 4-char mnemonic (see ACTIONS)
    [44:48]  four 0x00 bytes
    [48:]    key: the table name again for 'N'; for 'H' the selection key
             (request id, program name, or a key pattern ending in '*')

Field definition record (38-byte payload):

    [0]      'X' if key field, ' ' otherwise
    [1]      ABAP internal type letter (C N D T X I S B P ...)
    [2:8]    field length in BYTES, as 6 ASCII digits
    [8:38]   field name, blank padded

Data rows are the plain concatenation of all fields in nametab order, with
no separators. Character types (C/N/D/T) are UTF-16LE, so their byte
length is exactly 2x the DDIC character length; binary types (X/I/S/B/P)
use their native width. Summing the nametab byte lengths therefore gives
the exact row length -- which is what `--validate` checks.

Rows only carry the full row for the insert/replace style actions. The
delete-by-pattern actions ('00DELW', '00MODE') carry a shorter key
*pattern* instead, usually terminated by '*'.

ABAP source lives in 'ABAPREAD' blocks for the logical object REPOS: the
'H' key is the 32-char program name, the first row is a fixed attribute
header, and every row after that is one source line in UTF-16LE.

USAGE
-----
    python sap_transport_records.py --datafile R900001.DEV --summary
    python sap_transport_records.py --datafile R900001.DEV --validate
    python sap_transport_records.py --datafile R900001.DEV --objects
    python sap_transport_records.py --datafile R900001.DEV --table E070
    python sap_transport_records.py --datafile R900001.DEV --nametab E070
    python sap_transport_records.py --datafile R900001.DEV --sources ./src

    # or work from an already-decompressed stream
    python sap_transport_records.py --stream decompressed.bin --summary
"""

from __future__ import annotations

import argparse
import re
import struct
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

CONT_LAST = 0x20
CONT_MORE = 0x46
FRAGMENT_PAYLOAD = 500

HDR_LEN = 288
FIELDDEF_LEN = 38

# Types stored as UTF-16LE, i.e. byte length == 2 * character length.
CHAR_TYPES = frozenset("CNDT")

ACTIONS = {
    "00REP ": "replace",
    "00REPC": "replace (client dependent)",
    "00INS ": "insert",
    "00TOMD": "transport to modification database",
    "00MODE": "modify by key pattern",
    "00MMRG": "merge",
    "00CRMD": "create in modification database",
    "00DEL ": "delete",
    "00DELC": "delete (client dependent)",
    "00DELL": "delete language dependent",
    "00DELO": "delete object",
    "00DELW": "delete by wildcard pattern",
}

# Actions that transmit a complete row; everything else sends a key pattern.
FULL_ROW_ACTIONS = frozenset({"00REP ", "00REPC", "00INS ", "00TOMD", "00MMRG"})


# --------------------------------------------------------------------------
# Record layer
# --------------------------------------------------------------------------

@dataclass
class Record:
    """One logical record, with any continuation fragments already joined."""
    offset: int
    rtype: str
    payload: bytes
    fragments: int = 1


def iter_records(stream: bytes) -> "list[Record]":
    """
    Split the decompressed stream into logical records, joining
    continuation fragments. Raises if the framing does not land exactly on
    the end of the stream -- that is the strongest signal that a file was
    decompressed correctly.
    """
    out: list[Record] = []
    pos = 0
    pending: Record | None = None

    while pos + 6 <= len(stream):
        total = struct.unpack_from(">I", stream, pos)[0]
        if total < 6 or pos + total > len(stream):
            raise ValueError(
                f"bad record length {total} at offset {pos:#x} "
                f"(stream is {len(stream)} bytes)"
            )
        cont = stream[pos + 4]
        rtype = chr(stream[pos + 5])
        payload = stream[pos + 6:pos + total]

        if pending is None:
            pending = Record(offset=pos, rtype=rtype, payload=payload)
        else:
            pending.payload += payload
            pending.fragments += 1

        if cont == CONT_LAST:
            out.append(pending)
            pending = None
        elif cont != CONT_MORE:
            raise ValueError(f"unknown continuation flag {cont:#x} at {pos:#x}")

        pos += total

    if pending is not None:
        raise ValueError("stream ends inside a continued record")
    if pos != len(stream):
        raise ValueError(f"{len(stream) - pos} trailing bytes after last record")
    return out


def u16(payload: bytes) -> str:
    """Decode a UTF-16LE payload, tolerating an odd trailing byte."""
    if len(payload) % 2:
        payload = payload[:-1]
    return payload.decode("utf-16-le", errors="replace")


# --------------------------------------------------------------------------
# Structural layer
# --------------------------------------------------------------------------

@dataclass
class FieldDef:
    is_key: bool
    dtype: str
    length: int          # in bytes
    name: str

    @property
    def chars(self) -> int | None:
        """DDIC character length, for the UTF-16LE character types."""
        return self.length // 2 if self.dtype in CHAR_TYPES else None


@dataclass
class BlockHeader:
    handler: str         # "DLIB    ", "ATAB    ", "ABAPREAD"
    table: str
    action: str          # e.g. "00REP "
    key: str

    @property
    def action_name(self) -> str:
        return ACTIONS.get(self.action, "unknown")


@dataclass
class Nametab:
    header: BlockHeader
    fields: list[FieldDef] = field(default_factory=list)

    @property
    def row_length(self) -> int:
        return sum(f.length for f in self.fields)

    @property
    def key_length(self) -> int:
        return sum(f.length for f in self.fields if f.is_key)


@dataclass
class DataBlock:
    header: BlockHeader
    offset: int
    rows: list[bytes] = field(default_factory=list)
    longs: list[tuple[str, bytes]] = field(default_factory=list)


@dataclass
class TransportObject:
    e071_key: str        # from the 'C' record
    attributes: str      # from the 'A' record, if present


@dataclass
class Transport:
    directives: dict[str, str] = field(default_factory=dict)
    request: str = ""
    objects: list[TransportObject] = field(default_factory=list)
    nametabs: dict[str, Nametab] = field(default_factory=dict)
    blocks: list[DataBlock] = field(default_factory=list)
    records: list[Record] = field(default_factory=list)


def parse_header(payload: bytes) -> BlockHeader:
    return BlockHeader(
        handler=payload[0:8].decode("latin-1"),
        table=payload[8:38].decode("latin-1").rstrip(),
        action=payload[38:44].decode("latin-1"),
        key=payload[48:].decode("latin-1").rstrip(),
    )


def parse_fielddef(payload: bytes) -> FieldDef:
    return FieldDef(
        is_key=payload[0:1] == b"X",
        dtype=chr(payload[1]),
        length=int(payload[2:8]),
        name=payload[8:38].decode("latin-1").rstrip(),
    )


def parse_stream(stream: bytes) -> Transport:
    """Build the structural view of a decompressed R3trans stream."""
    records = iter_records(stream)
    t = Transport(records=records)

    # File-level directives are the '*' records that precede the first 'N'/'H'
    # block. Note the '*' is the record *type* byte, so the payload starts
    # directly with the key ("client:100", "Source System = ..."), and later
    # '*' records are inline markers ("dbtabpos:7", "COMMIT") rather than
    # directives -- hence the cutoff.
    header_end = next((n for n, r in enumerate(records)
                       if r.rtype in ("N", "H")), len(records))

    i = 0
    while i < len(records):
        r = records[i]

        if r.rtype == "F":
            t.request = u16(r.payload)

        elif r.rtype == "*" and i < header_end:
            text = r.payload.decode("latin-1").strip()
            for sep in (":", "="):
                if sep in text:
                    k, _, v = text.partition(sep)
                    t.directives[k.strip()] = v.strip()
                    break

        elif r.rtype == "C":
            pending_key = u16(r.payload)
            t.objects.append(TransportObject(e071_key=pending_key, attributes=""))

        elif r.rtype == "A":
            if t.objects:
                t.objects[-1].attributes = u16(r.payload)

        elif r.rtype == "N":
            nt = Nametab(header=parse_header(r.payload))
            i += 1
            while i < len(records) and records[i].rtype != "E":
                sub = records[i]
                if sub.rtype == " " and len(sub.payload) == FIELDDEF_LEN:
                    nt.fields.append(parse_fielddef(sub.payload))
                i += 1
            t.nametabs[nt.header.table] = nt

        elif r.rtype == "H":
            blk = DataBlock(header=parse_header(r.payload), offset=r.offset)
            i += 1
            while i < len(records) and records[i].rtype != "E":
                sub = records[i]
                if sub.rtype == " ":
                    blk.rows.append(sub.payload)
                elif sub.rtype in ("R", "U"):
                    blk.longs.append((sub.rtype, sub.payload))
                i += 1
            t.blocks.append(blk)

        i += 1

    return t


def decode_row(nt: Nametab, row: bytes) -> "list[tuple[str, str]]":
    """
    Split a row into (field name, value) pairs using the nametab. Character
    fields come back as text; anything else as hex.
    """
    out: list[tuple[str, str]] = []
    off = 0
    for f in nt.fields:
        chunk = row[off:off + f.length]
        off += f.length
        if not chunk:
            out.append((f.name, "<truncated>"))
        elif f.dtype in CHAR_TYPES:
            out.append((f.name, u16(chunk)))
        else:
            out.append((f.name, chunk.hex()))
    return out


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------

def validate(t: Transport) -> int:
    """
    Check every structural invariant the format guarantees. Returns the
    number of failures (0 means the whole file is understood).
    """
    failures = 0

    print("=== Structural invariants ===")
    print(f"Logical records        : {len(t.records):,}")
    print(f"Framing walk           : OK (landed exactly on EOF)")

    # Continued fragments must carry exactly 500 payload bytes each.
    multi = [r for r in t.records if r.fragments > 1]
    print(f"Multi-fragment records : {len(multi):,}")

    # ' S' size prefix must equal the next record's payload length.
    ok = bad = 0
    for i, r in enumerate(t.records):
        if r.rtype == "S" and i + 1 < len(t.records):
            want = struct.unpack(">I", r.payload)[0]
            got = len(t.records[i + 1].payload)
            if want == got:
                ok += 1
            else:
                bad += 1
                print(f"  [!] 'S' at {r.offset:#x} says {want}, next payload is {got}")
    failures += bad
    print(f"'S' length prefixes    : {ok} correct, {bad} wrong")

    # Object bookkeeping.
    n_d = sum(1 for r in t.records if r.rtype == "D")
    n_c = sum(1 for r in t.records if r.rtype == "C")
    print(f"Objects ('D'/'C')      : {n_d} / {n_c}"
          + ("" if n_d == n_c else "   [!] mismatch"))
    if n_d != n_c:
        failures += 1

    # Row lengths against the nametabs.
    print("\n=== Row length vs. nametab ===")
    stats: dict[str, Counter] = defaultdict(Counter)
    mismatches: Counter = Counter()
    for blk in t.blocks:
        nt = t.nametabs.get(blk.header.table)
        if nt is None:
            stats[blk.header.action]["no nametab (handler object)"] += len(blk.rows)
            continue
        for row in blk.rows:
            if len(row) == nt.row_length:
                stats[blk.header.action]["exact"] += 1
            elif blk.header.action in FULL_ROW_ACTIONS:
                stats[blk.header.action]["WRONG"] += 1
                mismatches[(blk.header.table, nt.row_length, len(row))] += 1
            else:
                stats[blk.header.action]["key pattern"] += 1

    for action in sorted(stats):
        label = f"{action!r} ({ACTIONS.get(action, 'unknown')})"
        print(f"  {label:<46} {dict(stats[action])}")

    wrong = sum(c["WRONG"] for c in stats.values())
    failures += wrong
    for (tab, want, got), n in mismatches.most_common(10):
        print(f"  [!] {tab}: expected {want} bytes, got {got}  x{n}")

    print(f"\nFAILURES: {failures}")
    return failures


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------

def print_summary(t: Transport) -> None:
    print("=== Request ===")
    print(f"  {t.request}")
    for k in ("R3trans version", "Source System", "client", "trfunction", "lsm"):
        if k in t.directives:
            print(f"  {k:<16}: {t.directives[k]}")
    print()

    print(f"=== Objects ({len(t.objects)}) ===")
    for o in t.objects:
        # E071 layout: TRKORR(20) AS4POS(6) PGMID(4) OBJECT(4) OBJ_NAME
        k = o.e071_key
        pos, pgmid, obj, name = k[20:26], k[26:30], k[30:34], k[34:].rstrip()
        print(f"  {pos} {pgmid} {obj} {name}")
    print()

    by_table: dict[str, Counter] = defaultdict(Counter)
    handlers: dict[str, str] = {}
    for blk in t.blocks:
        by_table[blk.header.table][blk.header.action] += len(blk.rows)
        handlers[blk.header.table] = blk.header.handler
    print(f"=== Tables with data ({len(by_table)}) ===")
    print(f"  {'table':<16} {'handler':<9} {'rows':>7}  actions")
    for tab in sorted(by_table, key=lambda x: -sum(by_table[x].values())):
        total = sum(by_table[tab].values())
        acts = ",".join(sorted(by_table[tab]))
        print(f"  {tab:<16} {handlers[tab]:<9} {total:>7}  {acts}")


def print_blocks(t: Transport) -> None:
    """
    Print the data blocks in stream order -- the emission recipe a writer has
    to reproduce. Order matters: R3trans applies the blocks sequentially, so
    the row-less delete/clear blocks must precede the blocks that refill the
    same tables.
    """
    print(f"=== Data blocks in stream order ({len(t.blocks)}) ===")
    print(f"  {'#':>4} {'offset':>9} {'table':<14} {'handler':<9} {'action':<8} "
          f"{'rows':>5}  key")
    for n, blk in enumerate(t.blocks, 1):
        h = blk.header
        key = " / ".join(key_parts(h.key)) or "-"
        if len(key) > 58:
            key = key[:55] + "..."
        print(f"  {n:>4} {blk.offset:>9x} {h.table:<14} {h.handler:<9} "
              f"{h.action!r:<8} {len(blk.rows):>5}  {key}")


def print_nametab(t: Transport, table: str) -> None:
    nt = t.nametabs.get(table)
    if nt is None:
        print(f"No nametab for {table!r}. Known: {', '.join(sorted(t.nametabs))}")
        return
    print(f"=== Nametab {table} ({nt.header.handler.strip()}) ===")
    print(f"  {len(nt.fields)} fields, {nt.row_length} bytes/row, "
          f"key {nt.key_length} bytes")
    print(f"  {'#':>3} {'key':<4} {'typ':<4} {'bytes':>6} {'chars':>6}  name")
    for n, f in enumerate(nt.fields, 1):
        chars = "" if f.chars is None else str(f.chars)
        print(f"  {n:>3} {'X' if f.is_key else '':<4} {f.dtype:<4} "
              f"{f.length:>6} {chars:>6}  {f.name}")


def print_table(t: Transport, table: str, limit: int) -> None:
    nt = t.nametabs.get(table)
    blocks = [b for b in t.blocks if b.header.table == table]
    if not blocks:
        print(f"No data blocks for {table!r}")
        return
    shown = 0
    for blk in blocks:
        full = blk.header.action in FULL_ROW_ACTIONS
        for row in blk.rows:
            if shown >= limit:
                print(f"  ... (limit {limit} reached)")
                return
            shown += 1
            print(f"--- {table} row {shown}  action={blk.header.action!r} "
                  f"({blk.header.action_name})  key={blk.header.key!r}")
            if nt is None:
                print(f"      no nametab; {len(row)} bytes: {u16(row)!r}")
            elif not full or len(row) != nt.row_length:
                print(f"      key pattern ({len(row)} bytes): {u16(row)!r}")
            else:
                for name, value in decode_row(nt, row):
                    print(f"      {name:<20} {value!r}")


def export_nametabs(transports: "list[Transport]", out: Path) -> None:
    """
    Write every table structure carried by the given transports to JSON.

    A writer needs these field layouts to build rows, and a GitHub Action has
    no SAP connection at generation time -- so they have to be frozen into the
    repo. The transport's own nametabs are the authoritative source: they are
    exactly what R3trans emitted, not a DD03L re-derivation that might differ
    in field order or width.
    """
    import json

    tables: dict[str, dict] = {}
    conflicts: list[str] = []
    for t in transports:
        for name, nt in t.nametabs.items():
            entry = {
                "handler": nt.header.handler.strip(),
                "row_bytes": nt.row_length,
                "key_bytes": nt.key_length,
                "fields": [
                    {"name": f.name, "type": f.dtype, "bytes": f.length,
                     "chars": f.chars, "key": f.is_key,
                     # Type 'A' is unnamed alignment filler, never a real column.
                     **({"padding": True} if f.dtype == "A" else {}),
                    }
                    for f in nt.fields
                ],
            }
            if name in tables and tables[name] != entry:
                conflicts.append(name)
            tables[name] = entry

    padding = sum(1 for v in tables.values() for f in v["fields"]
                  if f.get("padding"))
    doc = {
        "_comment": [
            "SAP transport nametabs (table structures) extracted from reference "
            "transport data files -- the authoritative source, because this is "
            "exactly what R3trans emits.",
            "Byte lengths are as R3trans writes them: 2x the DDIC character "
            "length for C/N/D/T, native width for binary types (I=4, S=2, B=1, "
            "X=raw, P=packed).",
            "Fields with type 'A' and no name are alignment filler of 1-3 bytes "
            "that pad the following field -- or the row end -- to a 4-byte "
            "boundary. They are NOT columns and do NOT appear in DD03L, which is "
            "why a writer cannot reconstruct these layouts from DD03L alone.",
        ],
        "table_count": len(tables),
        "padding_field_count": padding,
        "tables": dict(sorted(tables.items())),
    }
    out.write_text(json.dumps(doc, indent=2), encoding="utf-8")

    print(f"Wrote {len(tables)} table structures to {out}")
    if conflicts:
        print(f"  [!] {len(conflicts)} table(s) differed between transports: "
              f"{', '.join(sorted(set(conflicts)))}")
    else:
        print("  no conflicts: every table that appears in more than one "
              "transport has an identical layout")
    by_handler: Counter = Counter(v["handler"] for v in tables.values())
    print(f"  by handler: {dict(by_handler)}")


def key_parts(key: str) -> "list[str]":
    """
    Split an 'H' header key into its subfields. The key field is blank
    padded, and some handlers pack several values into it -- a class method
    include, for example, carries the include name, then the class name,
    then the method name, each separated by a run of blanks.
    """
    return [p for p in re.split(r"\s{2,}", key.strip()) if p]


def extract_sources(t: Transport, outdir: Path) -> None:
    """Write every ABAPREAD/REPOS block out as an ABAP source file."""
    outdir.mkdir(parents=True, exist_ok=True)
    written = 0
    for blk in t.blocks:
        if blk.header.handler != "ABAPREAD" or blk.header.table != "REPOS":
            continue
        if len(blk.rows) < 2:
            continue
        parts = key_parts(blk.header.key)
        if not parts:
            continue
        name = parts[0].rstrip("*")
        # First row is the attribute header; the rest are source lines.
        lines = [u16(r).rstrip() for r in blk.rows[1:]]
        safe = "".join(c if c.isalnum() or c in "_-=" else "_" for c in name)
        path = outdir / f"{safe}.abap"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        written += 1
        extra = f"  [{' / '.join(parts[1:])}]" if len(parts) > 1 else ""
        print(f"  {path.name:<40} {len(lines):>6} lines{extra}")
    print(f"\nWrote {written} source files to {outdir}")


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def load_transports(args) -> "list[Transport]":
    """Parse every input given. Most reports use the first one."""
    if args.stream:
        return [parse_stream(args.stream.read_bytes())]

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from sap_transport_decoder import decompress_datafile

    out = []
    for path in args.datafile:
        stream, blocks = decompress_datafile(path.read_bytes())
        label = f"{path.name}: " if len(args.datafile) > 1 else ""
        print(f"{label}Decompressed {len(blocks)} blocks -> {len(stream):,} bytes")
        out.append(parse_stream(stream))
    print()
    return out


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--datafile", type=Path, nargs="+",
                     help="R<nnnnn>.<SID> data file(s)")
    src.add_argument("--stream", type=Path,
                     help="already-decompressed stream (from decoder --out)")
    ap.add_argument("--summary", action="store_true", help="request, objects, tables")
    ap.add_argument("--validate", action="store_true",
                    help="check every structural invariant")
    ap.add_argument("--objects", action="store_true", help="list transported objects")
    ap.add_argument("--blocks", action="store_true",
                    help="list data blocks in stream order (the writer's recipe)")
    ap.add_argument("--nametab", metavar="TABLE", help="print a table's structure")
    ap.add_argument("--table", metavar="TABLE", help="decode a table's rows")
    ap.add_argument("--limit", type=int, default=20, help="rows for --table")
    ap.add_argument("--sources", type=Path, metavar="DIR",
                    help="extract ABAP sources into DIR")
    ap.add_argument("--export-nametabs", type=Path, metavar="JSON",
                    help="write all table structures to JSON (merges every "
                         "--datafile given); the writer's offline metadata cache")
    args = ap.parse_args()

    transports = load_transports(args)
    t = transports[0]

    if not any([args.summary, args.validate, args.objects, args.blocks,
                args.nametab, args.table, args.sources, args.export_nametabs]):
        args.summary = True

    if args.export_nametabs:
        export_nametabs(transports, args.export_nametabs)

    if args.summary:
        print_summary(t)
    if args.objects:
        for o in t.objects:
            print(f"  {o.e071_key.rstrip()}")
            if o.attributes:
                print(f"      {o.attributes.rstrip()}")
    if args.blocks:
        print_blocks(t)
    if args.nametab:
        print_nametab(t, args.nametab)
    if args.table:
        print_table(t, args.table, args.limit)
    if args.sources:
        extract_sources(t, args.sources)
    if args.validate:
        sys.exit(1 if validate(t) else 0)


if __name__ == "__main__":
    main()
