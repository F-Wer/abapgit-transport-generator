#!/usr/bin/env python3
"""
Generic structural verification of a generated transport data file.

    python test_transport.py <datafile> <request> [package]

Checks (everything a real import has ever rejected, and more):
  1. container framing accounts for every byte
  2. every block checksum matches SAP's CRC-32 (block_checksum)
  3. record layer round-trips byte-identically
  4. E071 rows match the CTS request shape (a workbench request has a
     CORR/RELE task row; a transport of copies stores objects directly)
  5. exactly one E07T row; F record entry count == E071 rows
  6. 'A' records: name/source system/author/package fields
  7. no template leftovers
  8. cofile (same basename with K) has object-count token 13 ==
     number of objects

Exit code 0 = intact, 1 = problems found. Used by the CI loop and by
test_action_local.py-style checks for CLAS/FUGR outputs.
"""
import re
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sap_transport_writer import (parse_container, decompress_container,
                                  block_checksum, serialize_stream)
from sap_transport_records import iter_records, u16

_MIN_LEFTOVER = 6


def template_leftovers(skip_request: str = "") -> tuple[str, ...]:
    """Template identities that must not survive into a generated file.

    Every template's object name (the first part of a compound key; the
    rest names a parent the generated object may share), request, texts
    and string ``names`` from the configured templates.json. Values shorter
    than six characters are skipped so common words stay usable, and the
    template whose request is `skip_request` is skipped (that file is the
    template itself). Without a usable template directory there is
    nothing to compare.
    """
    from transport_templates import TEMPLATES, TemplateError
    try:
        entries = [e for e in TEMPLATES.values() if e["request"] != skip_request]
    except TemplateError:
        return ()
    found = set()
    for entry in entries:
        found.update(entry["object"].split()[:1])
        found.add(entry["request"])
        found.update(text.strip() for text in
                     (entry["description"], *entry["descriptions"]))
        found.update(v for v in entry["names"].values() if isinstance(v, str))
    return tuple(sorted(v for v in found if len(v) >= _MIN_LEFTOVER))


def _contains_identifier(text: str, value: str) -> bool:
    """`value` occurs in `text` and is not part of a longer identifier."""
    pattern = r"(?<![A-Za-z0-9_/])" + re.escape(value) + r"(?![A-Za-z0-9_])"
    return re.search(pattern, text) is not None


def verify(datafile: Path, request: str, package: str = "") -> list[str]:
    issues = []
    raw = datafile.read_bytes()
    try:
        container = parse_container(raw)
    except ValueError as exc:
        return [f"container: {exc}"]
    blocks = container.blocks
    bad = [i for i, b in enumerate(blocks)
           if block_checksum(b.compressed) != b.checksum]
    if bad:
        issues.append(f"checksum errors in blocks {bad[:5]}")

    stream = decompress_container(container)
    records = iter_records(stream)
    if serialize_stream(records) != stream:
        issues.append("record round-trip not byte-identical")

    def block_rows(table):
        n = table.encode("latin-1")
        for i, r in enumerate(records):
            if (r.rtype == "H" and r.payload[8:8 + len(n)] == n
                    and r.payload[8 + len(n):9 + len(n)] == b" "):
                rows, j = [], i + 1
                while j < len(records) and records[j].rtype != "E":
                    if records[j].rtype == " ":
                        rows.append(u16(records[j].payload))
                    j += 1
                return rows
        return []

    e071 = block_rows("E071")
    e070 = block_rows("E070")
    if not e070:
        issues.append("E070 rows = 0, expected 1")
        is_transport_of_copies = False
    else:
        # E070.TRFUNCTION follows the CHAR-20 transport request number.
        is_transport_of_copies = len(e070[0]) > 20 and e070[0][20] == "T"
    cs = [r for r in records if r.rtype == "C"]
    ds = [r for r in records if r.rtype == "D"]
    corr_rele = [row for row in e071 if "CORR" in row and "RELE" in row]
    # A single-object transport keeps the template's native CORR/RELE task
    # row (E071 rows == object sections + 1) â€” a genuine single-object SAP
    # export always has this shape (verified byte-for-byte against a real
    # independently-exported single-object transport; R3trans HALTs with
    # "exists already with different contents. E071=1/file=2" if the row is
    # missing). A multi-object merge drops it (E071 rows == object sections,
    # no CORR/RELE row) â€” verified against a real multi-object export.
    if is_transport_of_copies:
        if len(e071) != len(cs):
            issues.append(f"transport-of-copies E071 rows {len(e071)} != "
                          f"object sections {len(cs)}")
        if corr_rele:
            issues.append("transport of copies unexpectedly carries a CORR/RELE task row")
    elif len(cs) == 1:
        if len(e071) != 2:
            issues.append(f"single-object E071 rows {len(e071)}, expected 2 "
                          f"(1 CORR/RELE task row + 1 object row)")
        if len(corr_rele) != 1:
            issues.append("single-object E071 missing its CORR/RELE task row")
    else:
        if len(e071) != len(cs):
            issues.append(f"E071 rows {len(e071)} != object sections {len(cs)}")
        if corr_rele:
            issues.append("multi-object E071 still carries a CORR/RELE task row")
    counts = [re.search(r"/(\d+)\)", r.payload.decode("utf-16-le", "replace"))
              for r in records if r.rtype == "F"]
    if len(counts) != 1 or not counts[0]:
        issues.append("no readable F record (request/owner/entry count)")
    elif int(counts[0].group(1)) != len(e071):
        issues.append(f"F record announces {counts[0].group(1)} request "
                      f"entries, E071 has {len(e071)} rows")
    if len(cs) != len(ds):
        issues.append(f"C {len(cs)} != D {len(ds)}")
    if len(block_rows("E07T")) != 1:
        issues.append(f"E07T rows = {len(block_rows('E07T'))}, expected 1")

    text = "\n".join(u16(r.payload) for r in records)
    # Long fields (STRING/RAWSTRING, nametab type U/R, 8-byte slot in the
    # row): every row is followed by one 'S' length record + value record
    # per long field. A row without them makes R3trans HALT ("Input buffer
    # ... too short").
    layouts, i = {}, 0
    while i < len(records):
        r = records[i]
        if r.rtype == "N":
            table, fields, j = r.payload[8:38].rstrip(), [], i + 1
            while records[j].rtype != "E":
                f = records[j].payload
                if records[j].rtype == " " and len(f) == 38:
                    fields.append((chr(f[1]), int(f[2:8])))
                j += 1
            layouts[table] = (sum(n for _t, n in fields),
                              sum(1 for t, n in fields if t in "UR" and n == 8))
        elif r.rtype == "H" and layouts.get(r.payload[8:38].rstrip(), (0, 0))[1]:
            width, longs = layouts[r.payload[8:38].rstrip()]
            j = i + 1
            while records[j].rtype != "E":
                if records[j].rtype == " " and len(records[j].payload) == width:
                    got = sum(1 for k in range(longs)
                              if records[j + 1 + 2 * k].rtype == "S")
                    if got != longs:
                        issues.append(
                            f"{r.payload[8:38].decode('latin-1').rstrip()} row "
                            f"has {got} long-field value(s), expected {longs}")
                j += 1
        i += 1

    for lo in template_leftovers(skip_request=request):
        if _contains_identifier(text, lo):
            issues.append(f"template leftover: {lo}")

    for a in [u16(r.payload) for r in records if r.rtype == "A"]:
        name, src, auth, devc = (a[8:58].rstrip(), a[58:68].rstrip(),
                                 a[68:80].rstrip(), a[81:111].rstrip())
        # The generator stores package names in uppercase, as SAP does.
        expected_package = name if a[4:8] == "DEVC" else package.strip().upper()
        if expected_package and devc != expected_package:
            issues.append(f"A record package {devc!r} != {expected_package!r}")
        # A generated transport names the request's own system as the
        # objects' original system; a real export (the native probes of
        # SAP-delivered objects) carries whatever TADIR says.
        valid_source = bool(src) if is_transport_of_copies else src == request[:3]
        if not name or not valid_source or not auth:
            issues.append(f"A record looks misaligned: name={name!r} "
                          f"src={src!r} auth={auth!r}")

    cofile = datafile.with_name("K" + datafile.name[1:])
    if cofile.is_file():
        toks = [t for t in cofile.read_text().splitlines()[0].split() if t]
        # token 13 is the total object count (tokens 5/6/9 count the
        # dictionary / generated / after-import objects among them)
        if len(toks) > 12 and toks[12] != str(len(cs)):
            issues.append(f"cofile object counter {toks[12]} "
                          f"!= {len(cs)} objects")
    return issues


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    datafile = Path(sys.argv[1])
    request = sys.argv[2]
    package = sys.argv[3] if len(sys.argv) > 3 else ""
    issues = verify(datafile, request, package)
    print(f"{datafile.name}: {len(issues)} issue(s)")
    for i in issues:
        print(f"  - {i}")
    return 0 if not issues else 1


if __name__ == "__main__":
    sys.exit(main())
