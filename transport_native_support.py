"""Shared native-import corrections used by the modular generator.

The compatibility facade configures shared dependencies after imports, following
the existing regenerator helper boundary and avoiding reverse imports.
"""
import base64
import binascii
import html
import re
import struct
import zlib
from pathlib import Path
from typing import Optional
from defusedxml import ElementTree as ET
from sap_transport_records import Record, u16

def configure_helpers(**helpers):
    globals().update(helpers)

def _set_meta_subc(meta_rec: Record, subc: str) -> Record:
    """Write the program type (TRDIR-SUBC: 1 executable, I include, ...)
    into a REPOS attribute row -- character 14, where the templates carry
    '1' (report), 'I' (includes), 'F' (function pool), 'K' (class pool)."""
    payload = bytearray(meta_rec.payload)
    payload[28:30] = subc[:1].encode("utf-16-le")
    return Record(offset=meta_rec.offset, rtype=meta_rec.rtype,
                  payload=bytes(payload), fragments=meta_rec.fragments)

def _split_definition_sections(definition: str) -> "tuple[str, str, str]":
    """
    Split a global class's DEFINITION block into the three section includes
    a class pool is built from: CU (header + PUBLIC SECTION), CO (PROTECTED
    SECTION) and CI (PRIVATE SECTION). The closing ENDCLASS is NOT part of
    any of them -- it lives in the CP include, after `include ...ci.`
    (see the CLAS template's own CP). Shipping it inside a section include
    as well gives the class two ENDCLASS statements: the pool only compiles
    with a hand-rolled CP, and SE24/ADT show a broken class.
    """
    lines = definition.split("\n")
    end = max(i for i, l in enumerate(lines) if _ENDCLASS_RE.match(l))
    lines = lines[:end]
    parts = {"PUBLIC": [], "PROTECTED": [], "PRIVATE": []}
    cur = "PUBLIC"
    for line in lines:
        m = _SECTION_RE.match(line)
        if m:
            cur = m.group(1).upper()
        parts[cur].append(line)

    def text(name: str) -> str:
        body = parts[name]
        while body and not body[-1].strip():
            body.pop()
        return "\n".join(body) if body else f"  {name} SECTION."
    return text("PUBLIC"), text("PROTECTED"), text("PRIVATE")

def _drop_object_index(records: list) -> list:
    """
    Turn an "optimized" data file (SAP_BASIS 816 exports) into the classic
    sequential layout. Such a file announces `optimized_datafile=yes` and
    carries an __INDEX_INFORMATION table of object file positions; any
    generated content moves those positions and R3trans HALTs with "object
    header not found". Without the announcement and the index it reads the
    file front to back, like every older export.
    """
    out = []
    i = 0
    while i < len(records):
        rec = records[i]
        if rec.rtype == "*" and rec.payload.startswith(
                (b"optimized_datafile", b"End-of-index", b"object_start:")):
            i += 1
            continue
        if (rec.rtype in ("N", "H")
                and rec.payload[8:38].rstrip() == b"__INDEX_INFORMATION"):
            while records[i].rtype != "E":
                i += 1
            i += 1
            continue
        out.append(rec)
        i += 1
    return out

def _textpool_block(repos_h: Record, program: str, language: str,
                    entries: list) -> list:
    """
    Build an `ABAPREAD REPOT<language>` block: a program's text pool in one
    language (text symbols, selection texts, title).

    All entries are packed into a single row, each as
        <LENGTH as one character><ID><KEY, 8 chars><text, LENGTH chars>
    (decoded from real exports: the PROG template's lone title entry and a
    multi-entry report text pool). The H record is a REPOS one with the
    table name and key swapped -- the layout is identical.
    """
    payload = bytearray(repos_h.payload)
    payload[8:38] = f"REPOT{language}".ljust(30).encode("latin-1")
    payload[38:44] = b"00REP "
    payload[48:] = program.encode("latin-1").ljust(len(payload) - 48)
    row = "".join(
        chr(length) + tid[:1] + key.ljust(8)[:8] + entry.ljust(length)[:length]
        for tid, key, entry, length in entries)
    return [Record(offset=0, rtype="H", payload=bytes(payload), fragments=1),
            Record(offset=0, rtype=" ", payload=row.encode("utf-16-le"),
                   fragments=1),
            Record(offset=0, rtype="*", payload=b"COMMIT", fragments=1),
            Record(offset=0, rtype="E", payload=b"", fragments=1)]

def _apply_fm_interfaces(records: list, interfaces: dict) -> None:
    """
    Write each function module's parameter interface (FUPARAREF) and
    processing type (TFDIR/ENLFDIR) from the repo's .fugr.xml.

    The FUGR template's function module has no parameters, so all the
    template offers per module is an empty `00DELL <FM> A*` FUPARAREF sweep
    -- shipped as is, every imported module lost its whole interface. The
    sweep becomes a `00REPC` block carrying the module's parameter rows.
    """
    nametabs = _parse_nametabs(records)
    para_fields = nametabs.get("FUPARAREF")
    i = 0
    while i < len(records):
        rec = records[i]
        if rec.rtype != "H":
            i += 1
            continue
        table = rec.payload[8:38].decode("latin-1").rstrip()
        key = rec.payload[48:].decode("latin-1").rstrip()
        fm = key[:30].rstrip() if table == "FUPARAREF" else key
        iface = interfaces.get(fm)
        if iface is None:
            i += 1
            continue
        if table == "FUPARAREF" and para_fields and iface["params"]:
            position = {}
            rows = []
            for prm in iface["params"]:
                ptype = prm["PARAMTYPE"]
                position[ptype] = position.get(ptype, 0) + 1
                typed = prm.get("TYP") or prm.get("DBSTRUCT") or ""
                rows.append(_seo_row(para_fields, {
                    "FUNCNAME": fm, "R3STATE": "A",
                    "PARAMETER": prm.get("PARAMETER") or prm.get("EXCEPTION", ""),
                    "PARAMTYPE": ptype,
                    "STRUCTURE": prm.get("DBFIELD") or typed,
                    "DEFAULTVAL": prm.get("DEFAULT", ""),
                    # TABLES parameters are always passed by reference
                    "REFERENCE": "X" if ptype == "T" else prm.get("REFERENCE", ""),
                    "PPOSITION": position[ptype],
                    # a default value makes the parameter optional
                    "OPTIONAL": "X" if prm.get("DEFAULT") else prm.get("OPTIONAL", ""),
                    # typed with TYPE (X) rather than LIKE/STRUCTURE (blank)
                    "TYPE": "X" if prm.get("TYP") else "",
                    "CLASS": ("X" if ptype == "X" and iface.get("exception_classes")
                              else prm.get("CLASS", "")),
                    "REF_CLASS": prm.get("REF_CLASS", ""),
                    "LINE_OF": prm.get("LINE_OF", ""),
                    "TABLE_OF": prm.get("TABLE_OF", ""),
                }))
            payload = bytearray(rec.payload)
            payload[38:44] = b"00REPC"
            records[i] = Record(offset=rec.offset, rtype=rec.rtype,
                                payload=bytes(payload), fragments=rec.fragments)
            records[i + 1:i + 1] = rows
            i += len(rows)
        elif table in ("TFDIR", "ENLFDIR"):
            fields = nametabs.get(table)
            j = i + 1
            while j < len(records) and records[j].rtype != "E":
                if records[j].rtype == " " and fields:
                    row = records[j]
                    if table == "TFDIR":
                        row = _write_field_by_name(
                            row, fields, "FMODE", iface["remote_call"])
                        row = _write_field_by_name(
                            row, fields, "UTASK", iface["update_task"])
                    else:
                        row = _write_field_by_name(
                            row, fields, "GLOBAL", iface["global_flag"])
                    records[j] = row
                j += 1
        i += 1

def _row_with_long_values(row: Record, fields: list, values: dict) -> list:
    """
    Return `row` plus the records carrying its long field values.

    A STRING/RAWSTRING column (nametab type U/R) is an 8-byte slot in the
    row; its value follows the row as an 'S' record (4-byte big-endian
    length) and a 'U' (UTF-16LE text) or 'R' (raw) record -- one pair per
    long column, in column order, also when the value is empty. The slot
    says which: 14 00 00 00 + 0/1 (text/raw) for an empty value, else the
    little-endian pair (n + 1, 0xFEFFFFFE - n) for the row's n-th non-empty
    long value. Decoded from 338 rows of native probe exports.
    """
    payload = bytearray(row.payload)
    out = []
    filled = 0
    for fname, off, flen, ftype in fields:
        if ftype not in "UR" or flen != 8:
            continue
        value = values.get(fname) or ""
        data = (value.encode("utf-16-le") if ftype == "U"
                else bytes(value) if not isinstance(value, str) else b"")
        if data:
            filled += 1
            payload[off:off + 8] = struct.pack("<II", filled + 1,
                                               0xFEFFFFFE - filled)
        else:
            payload[off:off + 8] = struct.pack("<II", 0x14,
                                               0 if ftype == "U" else 1)
        out.append(Record(offset=0, rtype="S",
                          payload=struct.pack(">I", len(data)), fragments=1))
        out.append(Record(offset=0, rtype=ftype, payload=data, fragments=1))
    return [Record(offset=row.offset, rtype=row.rtype, payload=bytes(payload),
                   fragments=row.fragments)] + out

def _regenerate_adobe_form_rows(records: list, obj_type: str, obj_name: str,
                                meta: dict) -> list:
    """Write SFPF/SFPI rows from abapGit's serialized ABAP XML.

    Native exports carry the form context, layout, interface and XDP as
    RAW long values.  abapGit keeps the same ABAP XML graph, so the only
    transformation needed is splitting the form's two heap roots into their
    respective transport columns.  This intentionally rejects an incomplete
    graph instead of falling back to a template value (which would create a
    form referring to the template object).
    """
    if obj_type == "SFPF":
        context = meta.get("context_xml") or ""
        layout = meta.get("layout_xml") or ""
        xdp = meta.get("xdp") or b""
        if not context or not layout:
            raise ValueError(f"SFPF {obj_name}: .sfpf.xml must contain both "
                             "CONTEXT and LAYOUT heap roots")
        if not xdp:
            raise ValueError(f"SFPF {obj_name}: companion .sfpf.xdp is "
                             "required when LAYOUT is present")
        header = meta.get("header") or {}
        lang = "E"
        content = {
            "FPCONTEXT": [{"NAME": obj_name, "STATE": "A",
                            "TYPE": header.get("TYPE") or "A",
                            "INTERFACE": header.get("INTERFACE") or "",
                            "OFFLINE_HANDLER": header.get("OFFLINEHANDLER") or "",
                            "DATAPROVIDER": header.get("DATAPROVIDER") or "",
                            "FRTYPE": header.get("FRTYPE") or "",
                            "CNTSET": header.get("CNTSET") or "",
                            "CONTEXT": context.encode("utf-8")}],
            "FPCONTEXTT": [{"NAME": obj_name, "STATE": "A", "LANGUAGE": lang,
                             "ID": "D", "TEXT": meta.get("context_text") or ""}],
            "FPLAYOUT": [{"NAME": obj_name, "STATE": "A", "FORMTECH": "SAP",
                           "TYPE": header.get("TYPE") or "A",
                           "LAYOUT": layout.encode("utf-8")}],
            "FPLAYOUTT": [{"NAME": obj_name, "STATE": "A", "LANGUAGE": lang,
                            "ID": "D", "LAYOUT": xdp, "LAYOUTM": xdp}],
        }
    else:
        interface = meta.get("interface_xml") or ""
        if not interface:
            raise ValueError(f"SFPI {obj_name}: .sfpi.xml must contain an "
                             "INTERFACE heap root")
        header = meta.get("header") or {}
        content = {
            "FPINTERFACE": [{"NAME": obj_name, "STATE": "A",
                             "INTERFACE_TYPE": header.get("TYPE") or "A",
                             "INTERFACE": interface.encode("utf-8")}],
            "FPINTERFACET": [{"NAME": obj_name, "STATE": "A", "LANGUAGE": "E",
                               "ID": "D", "TEXT": meta.get("interface_text") or ""}],
        }
    result = _regenerate_table_content(records, obj_name, content)
    print(f"  {obj_type} {obj_name}: regenerated {', '.join(content)} from "
          "abapGit serialized XML")
    return result

def _write_typed_value(row: Record, fields: list, name: str, value,
                       table: str = "") -> Record:
    """Write one value by column name in the column's own representation:
    text as UTF-16LE (NUMC zero-padded), RAW from base64 (or bytes),
    integers big-endian -- the byte order of a data file on any platform."""
    field = next((entry for entry in fields if entry[0] == name), None)
    if field is None:
        return row
    _field, offset, length, dtype = field
    if dtype in _CHAR_TYPES:
        return _write_dd04_field(row, fields, name, str(value))
    if dtype in "UR" and length == 8:
        return row                      # long value, see _row_with_long_values
    if dtype in "ISb8":
        try:
            raw = int(value or "0").to_bytes(length, "big", signed=True)
        except (ValueError, OverflowError) as exc:
            raise ValueError(
                f"{table}-{name} must be an integer: {value!r}") from exc
    elif isinstance(value, (bytes, bytearray)):
        raw = bytes(value)
    else:
        try:
            raw = base64.b64decode(value or "")
        except (ValueError, TypeError, binascii.Error) as exc:
            raise ValueError(f"{table}-{name} must be base64: {exc}") from exc
    return _write_raw_field_by_name(row, fields, name, raw)

def _key_columns(records: list, table: str) -> frozenset:
    """Names of `table`'s key columns (key flag 'X' in its nametab)."""
    needle = table.encode("latin-1").ljust(30)
    for i, rec in enumerate(records):
        if rec.rtype == "N" and rec.payload[8:38] == needle:
            out, j = set(), i + 1
            while records[j].rtype != "E":
                f = records[j].payload
                if records[j].rtype == " " and len(f) == 38 and f[:1] == b"X":
                    out.add(f[8:38].decode("latin-1").rstrip())
                j += 1
            return frozenset(out)
    return frozenset()

def _fresh_row(donor: "Record | None", fields: list, obj_name: str,
               values: dict, table: str = "",
               keys: frozenset = frozenset()) -> Record:
    """
    An initial row carrying `values` (by column name). Of the template row
    only two things survive: character columns that hold the object's own
    name (its key), and binary columns the repo has no value for.
    """
    payload = bytearray()
    for name, off, flen, ftype in fields:
        if ftype in _CHAR_TYPES:
            kept = ""
            if donor is not None and name not in values:
                old = donor.payload[off:off + flen].decode(
                    "utf-16-le", "replace").rstrip()
                # key columns the repo does not name (an activation state,
                # a version) must stay inside the block's key pattern
                kept = old if old == obj_name or name in keys else ""
            if not kept and ftype in "NDT":
                kept = "0" * (flen // 2)
            enc = kept.encode("utf-16-le")[:flen]
            payload += enc + b"\x20\x00" * ((flen - len(enc)) // 2)
        elif donor is not None:
            payload += donor.payload[off:off + flen]
        else:
            payload += b"\x00" * flen
    row = Record(offset=0, rtype=" ", payload=bytes(payload), fragments=1)
    for name, value in values.items():
        row = _write_typed_value(row, fields, name, value, table)
    return row

_AUTHOR_COLUMNS = ("AS4USER", "AUTHOR", "BNAME", "FIRSTUSER", "LASTUSER",
                   "RESPUSER", "CHANGEDBY", "ICF_CUSER", "ICF_MUSER")
# User columns whose name is too generic to rewrite in every table.
_TABLE_AUTHOR_COLUMNS = {"T100U": ("NAME",)}


def _apply_author_to_metadata_rows(records: list, author: str) -> list:
    """Replace template-user metadata wherever its table layout exposes it.

    abapGit intentionally omits SAP-maintained authors from most XML files;
    leaving the donor values makes a newly generated DDIC object appear to be
    owned by the template developer.  Restrict this to explicitly named
    user columns and full nametab-shaped rows, so keys and delete patterns
    are never changed.
    """
    if not author:
        return records
    nametabs = _parse_nametabs(records)
    current = None
    for index, rec in enumerate(records):
        if rec.rtype == "H" and rec.payload[:8] in (b"ATAB    ", b"DLIB    "):
            current = rec.payload[8:38].decode("latin-1").rstrip()
        elif rec.rtype == "E":
            current = None
        elif rec.rtype == " " and current in nametabs:
            fields = nametabs[current]
            if len(rec.payload) != fields[-1][1] + fields[-1][2]:
                continue
            row = rec
            for name in (_AUTHOR_COLUMNS
                         + _TABLE_AUTHOR_COLUMNS.get(current, ())):
                row = _write_field_by_name(row, fields, name, author)
            records[index] = row
    return records

def _table_blocks(records: list, table: str) -> list:
    """All content blocks of `table` as (h_idx, row_idxs, e_idx), i.e.
    without the `00DEL ` language sweep."""
    needle = table.encode("latin-1").ljust(30)
    out = []
    for i, rec in enumerate(records):
        if (rec.rtype == "H" and rec.payload[8:38] == needle
                and rec.payload[38:44] in (b"00REP ", b"00REPC", b"00DELL")):
            j = i + 1
            while records[j].rtype != "E":
                j += 1
            out.append((i, [k for k in range(i + 1, j)
                            if records[k].rtype == " "], j))
    return out

def _set_block_rows(records: list, blk, groups: list) -> None:
    """Replace a block's rows (with their long-value records) by `groups`
    (one record list per row) and make the header's action fit: a block
    that now carries rows replaces (00REPC), one without deletes (00DELL).
    A `00REP ` header block keeps its action."""
    h_idx, _rows, e_idx = blk
    keep = [r for r in records[h_idx + 1:e_idx] if r.rtype not in " SUR"]
    h = records[h_idx]
    action = h.payload[38:44]
    if action != b"00REP ":
        action = b"00REPC" if groups else b"00DELL"
    records[h_idx] = Record(offset=h.offset, rtype=h.rtype,
                            payload=h.payload[:38] + action + h.payload[44:],
                            fragments=h.fragments)
    records[h_idx + 1:e_idx] = [r for g in groups for r in g] + keep

def _regenerate_table_content(records: list, obj_name: str, content: dict,
                              language: str = "") -> list:
    """
    Fill the template's blocks from `content` = {table: [row values, ...]}.

    Every table named in `content` ends up with exactly the given rows --
    an empty list empties it. A text table the template splits into one
    block per language (key `<language><name>`) keeps the blocks of the
    languages the repo has texts in; rows without a language value belong
    to `language`, the repo's master language.
    """
    for table, rows_meta in content.items():
        fields = _parse_nametabs(records).get(table)
        blocks = _table_blocks(records, table)
        if not fields or not blocks:
            if rows_meta:
                print(f"  WARNING: {obj_name}: template has no {table} "
                      f"block -- {len(rows_meta)} row(s) NOT transported")
            continue
        lang_col = next((f[0] for f in fields if f[3] == "L"), None)

        keys = _key_columns(records, table)

        def group(meta, donor):
            row = _fresh_row(donor, fields, obj_name, meta, table, keys)
            return _row_with_long_values(row, fields, meta)

        if len(blocks) == 1:
            blk = blocks[0]
            donor = records[blk[1][0]] if blk[1] else None
            _set_block_rows(records, blk,
                            [group(meta, donor) for meta in rows_meta])
            continue

        # one block per language, the language leading the block's key
        by_lang = {}
        for meta in rows_meta:
            lang = meta.get(lang_col) or language or "E"
            by_lang.setdefault(lang, []).append({**meta, lang_col: lang})
        donor = next((records[b[1][0]] for b in blocks if b[1]), None)
        # Retain the full block even if every donor language is removed.
        first_h, _, first_e = blocks[0]
        donor_block = records[first_h:first_e + 1]
        insert_at = first_h
        seen = set()
        for h_idx, _rows, _e in reversed(blocks):
            blk = next(b for b in _table_blocks(records, table)
                       if b[0] == h_idx)
            lang = chr(records[h_idx].payload[48])
            seen.add(lang)
            if lang in by_lang:
                _set_block_rows(records, blk,
                                [group(m, donor) for m in by_lang[lang]])
            else:
                del records[h_idx:blk[2] + 1]
        missing = sorted(set(by_lang) - seen)
        if missing:
            # clone the last language block for languages the template lacks
            blocks = _table_blocks(records, table)
            insert_at = blocks[-1][2] + 1 if blocks else insert_at
            for lang in missing:
                h = donor_block[0]
                payload = bytearray(h.payload)
                payload[48:49] = lang.encode("latin-1")
                payload[38:44] = b"00REPC"
                new = [Record(offset=0, rtype="H", payload=bytes(payload),
                              fragments=1)]
                new += [r for g in by_lang[lang] for r in group(g, donor)]
                new += [r for r in donor_block[1:-1]
                        if r.rtype not in " SUR"]
                new.append(donor_block[-1])
                records[insert_at:insert_at] = new
                insert_at += len(new)
    return records

def _first(rows) -> dict:
    return (rows or [{}])[0]

def _table_content(obj_type: str, obj_name: str, sources,
                   package: str = "") -> "dict | None":
    """Map a table-content object's parsed abapGit XML to {table: rows}.
    Returns None for other object types."""
    meta = getattr(sources, f"{obj_type.lower()}_meta", None) or {}
    if obj_type == "ACID":
        return {"AAB_ID_PROPT": [{"DESCRIPT": meta.get("description")
                                  or _make_description(obj_name)}]}
    if obj_type == "AMSD":
        text = meta.get("DESCRIPTION") or meta.get("DESCRIPT") or ""
        header = {k: v for k, v in meta.items()
                  if k not in ("DESCRIPTION", "DESCRIPT")}
        return {"AMDP_SCHEMA_DEF": [header],
                "AMDP_SCHEMA_DEFT": [{"DESCRIPTION": text}] if text else []}
    if obj_type == "APIS":
        return {"ARS_W_API": [meta.get("header") or {}],
                "ARS_W_API_STATE": meta.get("states") or []}
    if obj_type == "APLO":
        return {t: meta.get(t) or [] for t in
                ("BALOBJ", "BALOBJT", "BALSUB", "BALSUBT")}
    if obj_type == "AQBG":
        return {"AQGDBBG": [meta], "AQGTB": meta.get("AQGTB") or []}
    if obj_type == "AQQU":
        return {t: meta.get(t) or [] for t in ("AQGQCAT", "AQGDB", "AQGTQ")}
    if obj_type == "AQSG":
        return {t: meta.get(t) or [] for t in ("AQGSCAT", "AQGDB", "AQGTS")}
    if obj_type == "ASFC":
        return {t: meta.get(t) or [] for t in
                ("AIND_STR1", "AIND_STR1T", "AIND_STR3", "AIND_STR4",
                 "AIND_STR6", "AIND_STR7")}
    if obj_type == "AUTH":
        return {"AUTHX": [meta], "AUTHX_ATTR": [{}]}
    if obj_type == "AVAR":
        return {
            # LOCAL: the user of a user-specific variant -- none here
            "AAB_VAR_PROP": [{"LOCAL": ""}],
            "AAB_VAR_PROPT": [{"LOCAL": "",
                               "DESCRIPT": meta.get("description", "")}],
            "AAB_VAR_ID": [
                {"LOCAL": "", "ID_NAME": item.get("NAME", ""),
                 "IS_PROGRAM": item.get("OBJECT", ""),
                 "ID_ACTMODE": bytes([int(item.get("ACTMODE") or 0)])}
                for item in meta.get("ids") or []],
        }
    if obj_type == "AVAS":
        header = meta.get("header") or {}
        return {"CLS_ASSIGNMENT": [
            {**{k: header.get(k, "") for k in
                ("GUID", "TROBJTYPE", "SOBJ_NAME", "OBJECT_TYPE", "SUB_KEY",
                 "ATTRIBUTE")},
             "VALUE": value.get("VALUE", ""),
             "REMARK": value.get("REMARK", "")}
            for value in meta.get("values") or [{}]]}
    if obj_type == "CHAR":
        activation = _first(meta.get("CLS_ATTRIBUTE")).get("ACTIVATION_STATE", "A")
        keys = {"NAME": obj_name, "ACTIVATION_STATE": activation}
        return {t: [{**keys, **row} for row in meta.get(t) or []] for t in
                ("CLS_ATTRIBUTE", "CLS_ATTRIBUTET", "CLS_ATTR_VALUE",
                 "CLS_ATTR_VALUET")}
    if obj_type == "PRAG":
        return {"TRPRAGMA": [{"PRAGMA": obj_name,
                                "EXT": meta.get("EXTENSION", ""),
                                "SIGNATURE": meta.get("SIGNATURE", "")}],
                "TRPRAGMAT": [{"LANGU": "E", "PRAGMA": obj_name,
                                 "DESCR": meta.get("DESCRIPTION", "")}]}
    if obj_type == "OTGR":
        header = {"NAME": obj_name, "ACTIVATION_STATE": "A",
                  "PROXY_FLAG": (meta.get("header") or {}).get("PROXY_FLAG", "")}
        base = {"OBJ_TYPE_GROUP": obj_name, "ACTIVATION_STATE": "A"}
        return {"CLS_TYPE_GROUP": [header],
                "CLS_TYGR_ELEMENT": [{**base, **row} for row in meta.get("elements") or []],
                "CLS_TYGR_PARENT": [{**base, **row} for row in meta.get("parents") or []],
                "CLS_TYPE_GROUPT": [{"NAME": obj_name, "ACTIVATION_STATE": "A", **row} for row in meta.get("texts") or []]}
    if obj_type == "PINF":
        attrs = meta.get("attributes") or {}
        elements = meta.get("elements") or []
        # The XML's DESCRIPT is stored separately in INTFTEXT.  Do not let
        # the donor package leak into the generated interface header.
        header_fields = ("PINFTYPE", "RESTRICTED", "DEFAULT_IF", "DEF_SEVER",
                         "ACL_FLAG", "PIFSTABLTY", "SUPPRESS_TRANSL",
                         "RELEASE_STATUS")
        header = {"INTF_NAME": obj_name,
                  "PACK_NAME": package or attrs.get("PACK_NAME", "")}
        header.update({field: attrs.get(field, "") for field in header_fields})
        description = attrs.get("DESCRIPT", "")
        texts = ([{"INTF_NAME": obj_name, "LANGU": "E",
                   "DESCRIPT": description}] if description else [])
        short = [{"INTF_NAME": obj_name, **row} for row in elements if len(row.get("ELEM_KEY", "")) <= 40]
        long = [{"INTF_NAME": obj_name, **row} for row in elements if len(row.get("ELEM_KEY", "")) > 40]
        return {"INTF": [header], "INTFTEXT": texts, "IFOBJSHORT": short, "IFOBJLONG": long}
    if obj_type == "NROB":
        attributes = dict(meta.get("attributes") or {})
        text = dict(meta.get("text") or {})
        attributes["OBJECT"] = obj_name
        text["OBJECT"] = obj_name
        return {"TNROS": [attributes], "TNROST": [text]}
    if obj_type == "PARA":
        tpara = dict(meta.get("tpara") or {})
        tparat = dict(meta.get("tparat") or {})
        tpara["PARAMID"] = obj_name
        tparat["PARAMID"] = obj_name
        return {"TPARA": [tpara], "TPARAT": [tparat]}
    if obj_type == "SUSC":
        tobc = dict(meta.get("tobc") or {})
        tobct = dict(meta.get("tobct") or {})
        tobc["OCLSS"] = obj_name
        tobct["OCLSS"] = obj_name
        return {"TOBC": [tobc], "TOBCT": [tobct]}
    if obj_type == "SUCU":
        group = obj_name[:30].rstrip()     # transport key: BRGRU (30) + OBJECT
        auth = [{"BRGRU": group, **row} for row in meta.get("auth") or []]
        texts = [{"BRGRU": group, **row} for row in meta.get("texts") or []]
        return {"TBRG_AUTH": auth, "TBRG_AUTHT": texts}
    if obj_type == "SPPF":
        row = dict(meta)
        row["PFORMAT"] = obj_name[:8].rstrip()   # transport key: PFORMAT (8) + ORIENT
        return {"TSP08": [row]}
    if obj_type == "SPLO":
        header = {"PAPART": obj_name, **(meta.get("header") or {})}
        output = {"PDPAPER": obj_name, **(meta.get("output") or {})}
        texts = [{"PAPART": obj_name, **row}
                 for row in meta.get("texts") or []]
        return {"TSP1D": [header], "TSP1T": texts, "TSP0P": [output]}
    if obj_type == "SUSO":
        tobj = {"OBJCT": obj_name, **(meta.get("tobj") or {})}
        tobj["OBJCT"] = obj_name
        # abapGit clears the SAP-maintained editor; do not retain the template
        # user's BNAME while building a fresh authorization object.
        tobj["BNAME"] = ""
        tobjt = {"OBJECT": obj_name, **(meta.get("tobjt") or {})}
        flags = {"OBJCT": obj_name, **(meta.get("flags") or {})}
        tactz = [{"BROBJ": obj_name, **row} for row in meta.get("tactz") or []]
        vordat = [{"OBJCT": obj_name, **row} for row in meta.get("vordat") or []]
        vor = [{"OBJCT": obj_name, **row} for row in meta.get("vor") or []]
        attr = [{"OBJCT": obj_name, "ABAP_LANGUAGE_VERSION":
                 meta.get("abap_language_version", "")}]
        return {"TOBJ": [tobj], "TOBJT": [tobjt], "TOBJVORFLG": [flags],
                "TACTZ": tactz, "TOBJVORDAT": vordat, "TOBJVOR": vor,
                "TOBJ_ATTR": attr, "TOBJ_FLD_EXT": []}
    if obj_type == "CUS0":
        header = {"ACTIVITY": obj_name, **(meta.get("header") or {})}
        header["ACTIVITY"] = obj_name
        texts = [{"ACTIVITY": obj_name, **row}
                 for row in meta.get("texts") or []]
        return {"CUS_IMGACH": [header], "CUS_IMGACT": texts,
                "CUS_IMGACTC": []}
    if obj_type == "CUS2":
        header = {"ATTR_ID": obj_name, **(meta.get("header") or {})}
        header["ATTR_ID"] = obj_name
        titles = [{"ATTR_ID": obj_name, **row} for row in meta.get("titles") or []]
        countries = [{"ATTR_ID": obj_name, **row} for row in meta.get("countries") or []]
        components = [{"DOKNAME": obj_name, **row} for row in meta.get("components") or []]
        return {"CUS_ATRH": [header], "CUS_ATRT": titles,
                "CUS_ATRCOU": countries, "TFM18": components}
    if obj_type == "CUS1":
        header = {"ACT_ID": obj_name, **(meta.get("header") or {})}
        header["ACT_ID"] = obj_name
        exit_meta = meta.get("exit") or {}
        exit_rows = ([{"ACT_ID": obj_name, **exit_meta}] if exit_meta else [])
        titles = [{"ACT_ID": obj_name, **row} for row in meta.get("titles") or []]
        objects = [{"ACT_ID": obj_name, **row} for row in meta.get("objects") or []]
        object_titles = [{"ACT_ID": obj_name, **row}
                         for row in meta.get("object_titles") or []]
        return {"CUS_ACTH": [header], "CUS_ACTEXT": exit_rows,
                "CUS_ACTT": titles, "CUS_ACTOBJ": objects,
                "CUS_ACTOBT": object_titles}
    if obj_type == "PERS":
        header = {"PERS_KEY": obj_name, **(meta.get("header") or {})}; header["PERS_KEY"] = obj_name
        text = {"PERS_KEY": obj_name, **(meta.get("text") or {})}
        return {"SPERS_REG": [header], "SPERS_REGT": [text], "SPERS_REGA": []}
    if obj_type == "SCVI":
        h={"SCVARIANT":obj_name,**(meta.get("header") or {})}; h["SCVARIANT"]=obj_name
        def rows(key): return [{"SCVARIANT":obj_name,**x} for x in meta.get(key) or []]
        return {"SHDSVCI":[h],"SHDSVTXCI":rows("texts"),"SHDSVFVCI":rows("values"),"SHDGUIXT":rows("guixt"),"SHDGXTCODE":rows("tcodes")}
    return None

def _apply_xml_columns(row: Record, fields: list, values: dict,
                       keep=()) -> Record:
    """
    Fill a DDIC row from an abapGit XML element: every character-like column
    gets the XML's value, or its initial value when the XML has no such tag
    -- abapGit never serializes initial fields, so "not in the XML" means
    initial, and leaving the template's value there ships another object's
    setting. `keep` names the columns to leave alone (the row's key, and
    whatever the caller writes itself); system columns are always kept.
    """
    for fname, _off, _flen, ftype in fields or []:
        if (ftype not in _CHAR_TYPES or fname in keep
                or fname in _DDIC_SYSTEM_COLUMNS):
            continue
        row = _write_dd04_field(row, fields, fname, values.get(fname, ""))
    return row

def _replace_xslt_source_table(decompressed: bytes, source: str,
                               obj_name: str) -> bytes:
    """Replace the source-line table of a decompressed XSLT cluster with
    the lines of `source` (any number of lines)."""
    head = decompressed.find(_XSLT_TABLE_HEAD)
    body = head + len(_XSLT_TABLE_HEAD) + 4
    if head < 0 or decompressed[body:body + 5] != _XSLT_ROW_HEAD:
        raise ValueError(f"XSLT {obj_name}: no source-line table found in "
                         f"the template's cluster")
    old_rows = struct.unpack_from(">I", decompressed, body - 4)[0]
    row_len = len(_XSLT_ROW_HEAD) + _XSLT_LINE_BYTES + 1
    end = body + old_rows * row_len
    if decompressed[end:end + 1] != b"\xbf":
        raise ValueError(f"XSLT {obj_name}: unexpected source-line table "
                         f"layout in the template's cluster")
    lines = source.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if lines and lines[-1] == "":
        lines.pop()                      # the file's final newline
    too_long = [n for n, line in enumerate(lines, start=1)
                if len(line) > _XSLT_LINE_CHARS]
    if too_long:
        raise ValueError(
            f"XSLT {obj_name}: source line(s) {too_long[:5]} are longer "
            f"than {_XSLT_LINE_CHARS} characters -- a transformation is "
            f"stored as lines of at most that length")
    rows = b"".join(
        _XSLT_ROW_HEAD + line.ljust(_XSLT_LINE_CHARS).encode("utf-16-le")
        + b"\xbd" for line in lines)
    return (decompressed[:body - 4] + struct.pack(">I", len(lines))
            + rows + decompressed[end:])

def _split_outside_literals(text: str, sep: str) -> list:
    """Split `text` at `sep`, ignoring separators inside '..', `..`, |..|."""
    parts, buf, quote = [], [], None
    for ch in text:
        if quote:
            if ch == quote:
                quote = None
        elif ch in "'`|":
            quote = ch
        elif ch == sep:
            parts.append("".join(buf))
            buf = []
            continue
        buf.append(ch)
    parts.append("".join(buf))
    return parts

def _abap_statements(source: str) -> list:
    """
    Split ABAP declaration source into statements: comments removed, each
    statement on one line, chained statements (`METHODS: a, b.`) expanded
    into one statement per chain element. Declarations span lines and are
    routinely chained, so nothing line-based can find their names reliably.
    """
    raw, buf = [], []
    for line in source.replace("\r", "").split("\n"):
        if line.startswith("*"):
            continue
        quote = None
        for i, ch in enumerate(line):
            if quote:
                buf.append(ch)
                if ch == quote:
                    quote = None
            elif ch == '"':
                break
            elif ch in "'`|":
                quote = ch
                buf.append(ch)
            elif ch == "." and (i + 1 == len(line) or line[i + 1].isspace()):
                raw.append("".join(buf))
                buf = []
            else:
                buf.append(ch)
        buf.append(" ")
    statements = []
    for stmt in raw:
        head = _split_outside_literals(stmt, ":")
        if len(head) > 1:
            prefix, rest = head[0], ":".join(head[1:])
            chain = [f"{prefix} {part}"
                     for part in _split_outside_literals(rest, ",")]
        else:
            chain = [stmt]
        statements += [c.strip() for c in chain if c.strip()]
    return statements

def _parse_seo_declarations(declaration: str) -> dict:
    """
    Read what the class builder's tables model from a CLASS ... DEFINITION /
    INTERFACE declaration: the header options, the implemented interfaces,
    and the members (methods plus simple quoted-value constants).
    """
    out = {"final": False, "abstract": False, "exposure": "2",
           "super": "", "interfaces": [], "members": []}
    seen = set()
    section = "PUBLIC"
    for n, stmt in enumerate(_abap_statements(declaration)):
        toks = stmt.split()
        up = [t.upper() for t in toks]
        if n == 0 and up[0] == "CLASS":
            out["final"] = "FINAL" in up
            out["abstract"] = "ABSTRACT" in up
            if "CREATE" in up[:-1]:
                out["exposure"] = _SECTION_EXPOSURE.get(
                    up[up.index("CREATE") + 1], "2")
            if "INHERITING" in up[:-2]:
                out["super"] = up[up.index("INHERITING") + 2]
            continue
        if len(up) == 2 and up[1] == "SECTION" and up[0] in _SECTION_EXPOSURE:
            section = up[0]
            continue
        if up[0] == "INTERFACES" and len(up) > 1:
            if up[1] not in out["interfaces"]:
                out["interfaces"].append(up[1])
            continue
        if up[0] in ("METHODS", "CLASS-METHODS") and len(up) > 1:
            name = up[1]
            # A redefinition (inherited or interface method) is not a
            # component of this class -- it belongs to SEOREDEF.
            if "REDEFINITION" in up or "~" in name or name in seen:
                continue
            seen.add(name)
            out["members"].append({
                "kind": "method", "name": name,
                "mtddecltyp": "1" if up[0] == "CLASS-METHODS" else "0",
                "mtdtype": ("2" if name in ("CONSTRUCTOR", "CLASS_CONSTRUCTOR")
                            else "0"),
                "exposure": _SECTION_EXPOSURE[section],
            })
            continue
        c = _CONSTANT_RE.match(stmt)
        if c and c.group(1).upper() not in seen:
            seen.add(c.group(1).upper())
            out["members"].append({
                "kind": "const", "name": c.group(1).upper(),
                "type": c.group(2).upper(), "value": c.group(3),
                "exposure": _SECTION_EXPOSURE[section],
            })
    return out

def _seo_row(fields: list, values: dict) -> Record:
    """Build a table row from scratch: character fields space-filled,
    binary fields zeroed, then `values` written by field name. An INT4
    value is given as int, everything else as text."""
    payload = bytearray()
    for fname, _off, flen, ftype in fields:
        value = values.get(fname)
        if ftype in _CHAR_TYPES:
            text = "" if value is None else str(value)
            if ftype in "ND" and not text:
                text = "0" * (flen // 2)
            enc = text.encode("utf-16-le")[:flen]
            payload += enc + b"\x20\x00" * ((flen - len(enc)) // 2)
        else:
            payload += int(value or 0).to_bytes(flen, "big")
    return Record(offset=0, rtype=" ", payload=bytes(payload), fragments=1)

def _apply_seo_header(records: list, obj_type: str, obj_name: str,
                      declaration: str, seo_meta: dict) -> None:
    """
    Make the class builder's header tables describe the repo's object
    instead of the template's: SEOCLASSDF flags (.clas.xml/.intf.xml plus
    FINAL/ABSTRACT/CREATE from the source), the SEOCLASSTX short text, and
    SEOMETAREL (superclass + implemented interfaces), which the template
    only carries as an empty delete.
    """
    nametabs = _parse_nametabs(records)
    decl = _parse_seo_declarations(declaration)

    # SEOCLASS.UUID is the template class's GUID; every generated class
    # would share it. Initial is valid (thousands of SAP classes carry it).
    blk = _find_block(records, "SEOCLASS")
    fields = nametabs.get("SEOCLASS")
    if blk and fields:
        width = next((f[2] for f in fields if f[0] == "UUID"), 0)
        for ridx in blk[1]:
            if width:
                records[ridx] = _write_raw_field_by_name(
                    records[ridx], fields, "UUID", b"\x00" * width)

    blk = _find_block(records, "SEOCLASSDF")
    fields = nametabs.get("SEOCLASSDF")
    if blk and blk[1] and fields:
        names = {f[0] for f in fields}
        values = dict(_SEO_HEADER_DEFAULTS)
        values.update({k: v for k, v in seo_meta.items()
                       if k in _SEO_HEADER_DEFAULTS})
        if obj_type == "CLAS":
            values.update(CLSFINAL="X" if decl["final"] else "",
                          CLSABSTRCT="X" if decl["abstract"] else "",
                          EXPOSURE=decl["exposure"])
        else:
            values["EXPOSURE"] = seo_meta.get("EXPOSURE", "2")
        row = records[blk[1][0]]
        for fname, value in values.items():
            if fname in names:
                row = _write_field_by_name(row, fields, fname, value)
        records[blk[1][0]] = row

    blk = _find_block(records, "SEOCLASSTX")
    fields = nametabs.get("SEOCLASSTX")
    if blk and blk[1] and fields and seo_meta.get("DESCRIPT"):
        row = records[blk[1][0]]
        row = _write_field_by_name(row, fields, "DESCRIPT", seo_meta["DESCRIPT"])
        if seo_meta.get("LANGU"):
            row = _write_field_by_name(row, fields, "LANGU", seo_meta["LANGU"])
        records[blk[1][0]] = row

    relations = ([(decl["super"], "2", "0")] if decl["super"] else []) + \
                [(intf, "1", "2") for intf in decl["interfaces"]]
    blk = _find_block(records, "SEOMETAREL")
    fields = nametabs.get("SEOMETAREL")
    if relations and blk and not blk[1] and fields:
        df_blk = _find_block(records, "SEOCLASSDF")
        df_fields = nametabs.get("SEOCLASSDF")
        author = createdon = ""
        if df_blk and df_blk[1] and df_fields:
            payload = records[df_blk[1][0]].payload
            author = _get_field_text(payload, df_fields, "AUTHOR")
            createdon = _get_field_text(payload, df_fields, "CREATEDON")
        rows = [_seo_row(fields, {
                    "CLSNAME": obj_name, "REFCLSNAME": ref, "VERSION": "1",
                    "STATE": "1", "AUTHOR": author, "CREATEDON": createdon,
                    "RELTYPE": reltype, "EXPOSURE": exposure,
                    "EDITORDER": 0 if reltype == "2" else order})
                for order, (ref, reltype, exposure) in enumerate(relations, start=1)]
        h = records[blk[0]]
        payload = bytearray(h.payload)
        payload[38:44] = b"00REPC"       # the template block is a 00DELL
        records[blk[0]] = Record(offset=h.offset, rtype=h.rtype,
                                 payload=bytes(payload), fragments=h.fragments)
        records[blk[0] + 1:blk[0] + 1] = rows

def _ensure_trdir_nametab(records: list) -> None:
    """
    Source blocks (ABAPREAD REPOS) are written through table TRDIR, whose
    layout must have been declared earlier in the file -- else R3trans
    HALTs with "no nametab found for table TRDIR". The ENHO and TYPE
    templates were spliced without one; borrow the PROG template's.
    """
    first = next((i for i, r in enumerate(records) if r.rtype == "H"
                  and r.payload[:16] == b"ABAPREADREPOS   "), None)
    if first is None or any(
            r.rtype == "N" and r.payload[8:38].rstrip() == b"TRDIR"
            for r in records[:first]):
        return
    _, donor = _load_template_records("PROG")
    start = next(i for i, r in enumerate(donor)
                 if r.rtype == "N" and r.payload[8:38].rstrip() == b"TRDIR")
    end = next(i for i in range(start, len(donor)) if donor[i].rtype == "E")
    if donor[start - 1].rtype == "*" and donor[start - 1].payload.startswith(b"gsr:"):
        start -= 1
    records[first:first] = donor[start:end + 1]

def request_text(object_names: list) -> str:
    """The generated request's short text (E07T-AS4TEXT, 60 characters)."""
    first = object_names[0].split()[0] if object_names else ""
    more = f" +{len(object_names) - 1} more" if len(object_names) > 1 else ""
    return f"abapGit: {first}{more}"[:60]


def _set_request_text(records: list, text: str, language: str = "") -> None:
    """
    Write `text` (and, when given, its `language`) into every E07T row. A
    template's request text describes the template (its probe or donor),
    and the generic rename only replaces it when the text happens to
    contain the template object's name.
    """
    blk = _find_block(records, "E07T")
    fields = _parse_nametabs(records).get("E07T")
    if blk is None or not fields:
        raise ValueError("template has no E07T row to describe the request")
    for ridx in blk[1]:
        row = _write_field_by_name(records[ridx], fields, "AS4TEXT", text)
        if language:
            row = _write_field_by_name(row, fields, "LANGU", language[:1])
        records[ridx] = row


def _check_object_list(records: list, objects: list) -> None:
    """
    The request must name exactly the generated objects. A template whose
    object key the rename did not find would otherwise ship ITS object --
    and the import replaces and re-registers that object on the target.
    `objects` holds (type, transport name) pairs in request order.
    """
    found = [(u16(r.payload)[30:34], u16(r.payload)[34:].rstrip())
             for r in records if r.rtype == "C"]
    expected = [(t, n.rstrip()) for t, n in objects]
    if found != expected:
        raise ValueError(
            f"request lists {found}, expected {expected}: a template's object "
            f"key was not replaced; check its 'object' in templates.json")


def _set_request_entry_count(records: list) -> None:
    """
    Write the number of E071 rows into the request's F record,
    `<request>  (<owner>/<count>)`.

    R3trans checks the two against each other whenever the request already
    exists on the target -- on a re-import, and on every import that needs
    more than one R3trans run (dictionary import, then main import) -- and
    HALTs with "exists already with different contents. E071=<rows>/file=
    <count>". Real exports agree: 2 rows -> /2, 1 row -> /1, 54 rows -> /54.
    """
    blk = _find_block(records, "E071")
    if blk is None:
        raise ValueError("no E071 block to count")
    for i, rec in enumerate(records):
        if rec.rtype != "F":
            continue
        text, n = re.subn(r"/\d+\)", f"/{len(blk[1])})",
                          rec.payload.decode("utf-16-le"))
        if n != 1:
            raise ValueError(f"unexpected F record layout: {text!r}")
        records[i] = Record(offset=rec.offset, rtype=rec.rtype,
                            payload=text.encode("utf-16-le"),
                            fragments=rec.fragments)
        return
    raise ValueError("no F record in template")

def _header_nametab_blocks(header: list) -> list:
    """Return the records of all object-level nametab blocks in a template's
    request header: each N record up to its E terminator, with the `gsr:`
    marker record preceding it."""
    out = []
    i = 0
    while i < len(header):
        rec = header[i]
        if rec.rtype != "N":
            i += 1
            continue
        j = i
        while j < len(header) and header[j].rtype != "E":
            j += 1
        table = rec.payload[8:38].decode("latin-1").rstrip()
        if table not in _REQUEST_LEVEL_TABLES:
            if (i > 0 and header[i - 1].rtype == "*"
                    and header[i - 1].payload.startswith(b"gsr:")):
                out.append(header[i - 1])
            out += header[i:j + 1]
        i = j + 1
    return out

def _transport_object_name(obj_type: str, file_name: str, sources) -> str:
    """
    The TADIR name of an object whose name is a compound key. The file name
    cannot be trusted to carry it (fixed-width parts, padding blanks, for
    SICF not even the same value), the XML content can.
    """
    if obj_type == "SICF":
        return sicf_object_name(file_name, sources.sicf_meta)
    if obj_type == "APIS":
        # OBJECT_ID (36) + OBJECT_TYPE (4)
        header = sources.apis_meta.get("header") or {}
        if header.get("OBJECT_ID") and header.get("OBJECT_TYPE"):
            return header["OBJECT_ID"].ljust(36) + header["OBJECT_TYPE"]
    if obj_type == "AQQU":
        # user group (12) + query name
        row = (sources.aqqu_meta.get("AQGQCAT") or [{}])[0]
        if row.get("NUM") and row.get("QNUM"):
            return row["NUM"].ljust(12) + row["QNUM"]
    if obj_type == "AVAS":
        guid = (sources.avas_meta.get("header") or {}).get("GUID")
        if guid:
            return guid
    if obj_type == "SPPF":
        # page format PFORMAT (8) + orientation ORIENT, e.g. 'DINA4   P'
        orient = (getattr(sources, "sppf_meta", None) or {}).get("ORIENT")
        if not orient:
            raise ValueError(f"SPPF {file_name}: .sppf.xml has no ORIENT, so the "
                             f"transport key PFORMAT + ORIENT cannot be built")
        return file_name.ljust(8) + orient
    if obj_type == "SUCU":
        # authorization group BRGRU (30) + authorization object OBJECT
        auth = (getattr(sources, "sucu_meta", None) or {}).get("auth") or [{}]
        objects = {row.get("OBJECT") for row in auth if row.get("OBJECT")}
        if len(objects) != 1:
            raise ValueError(f"SUCU {file_name}: .sucu.xml must name exactly one "
                             f"authorization object, found {sorted(objects)}")
        return file_name.ljust(30) + objects.pop()
    return file_name


# Native transport row-layout constants.
_CHAR_TYPES = frozenset("CNDTLGY")
A_SRCSYSTEM_OFF = 58
A_AUTHOR_OFF = 68
A_AUTHOR_LEN = 12
A_MASTERLANG_OFF = 121
_ENDCLASS_RE = re.compile(r"^\s*ENDCLASS\b", re.IGNORECASE)
_SECTION_RE = re.compile(r"^\s*(PUBLIC|PROTECTED|PRIVATE)\s+SECTION\s*\.",
                         re.IGNORECASE)
_CLASS_LOCAL_STUBS = {
    "CCDEF": ('*"* use this source file for any type of declarations (class\n'
              '*"* definitions, interfaces or type declarations) you need for\n'
              '*"* components in the private section\n'),
    "CCIMP": ('*"* use this source file for the definition and implementation of\n'
              '*"* local helper classes, interface definitions and type\n'
              '*"* declarations\n'),
    "CCMAC": ('*"* use this source file for any macro definitions you need\n'
              '*"* in the implementation part of the class\n'),
}
_DDIC_SYSTEM_COLUMNS = frozenset(
    ("AS4LOCAL", "AS4VERS", "AS4USER", "AS4DATE", "AS4TIME", "ACTFLAG"))
_XSLT_LINE_CHARS = 255
_XSLT_LINE_BYTES = _XSLT_LINE_CHARS * 2
_XSLT_ROW_HEAD = b"\xbc" + struct.pack(">I", _XSLT_LINE_BYTES)
_XSLT_TABLE_HEAD = b"\xbe" + struct.pack(">I", _XSLT_LINE_BYTES)
_CONSTANT_RE = re.compile(
    r"^\s*CONSTANTS\s+([\w~]+)\s+TYPE\s+([\w~/]+)\s+VALUE\s+'([^']*)'\s*$",
    re.IGNORECASE)
_SECTION_EXPOSURE = {"PUBLIC": "2", "PROTECTED": "1", "PRIVATE": "0"}
_SEO_HEADER_DEFAULTS = {
    "CATEGORY": "00", "CLSCCINCL": "", "FIXPT": "", "UNICODE": "",
    "WITH_UNIT_TESTS": "", "DURATION_TYPE": "0", "RISK_LEVEL": "0",
    "MSG_ID": "", "CLSSHAREDMEMORY": "", "CLSDEFATT": "", "CLSDEFMTD": "",
}
_REQUEST_LEVEL_TABLES = frozenset(
    ("E070", "E071", "E070C", "E070A", "E07T", "TADIR", "__INDEX_INFORMATION"))
