"""REPOS source encoding, parsing, mapping, and injection primitives.

This module owns the fixed-width source-block behavior shared by PROG, CLAS,
INTF, and FUGR transport generation.  The compatibility facade re-exports
the original private helper names.
"""

from __future__ import annotations

import re
from pathlib import Path

from sap_transport_records import Record
from transport_record_renames import RenameRule


def extract_ldb(xml_path) -> str:
    """Read the logical database name from an abapGit .prog.xml ("" if none)."""
    if xml_path is None or not Path(xml_path).exists():
        return ""
    text = Path(xml_path).read_text(encoding="utf-8", errors="replace")
    m = re.search(r"<LDBNAME>([^<]*)</LDBNAME>", text, re.IGNORECASE)
    return (m.group(1) if m else "").strip().upper()


def set_meta_ldb(meta_rec: Record, ldb: str) -> Record:
    """
    Write the logical database name into a 628-byte REPOS meta row
    (bytes 218-228, 5 UTF-16LE chars -- verified against a real export:
    template "D$S" vs the real report's "PNPCE"). The compiler resolves
    NODES/GET statements against this field, so leaving the template's
    value breaks reports using a logical database.
    """
    if not ldb or len(meta_rec.payload) != 628:
        return meta_rec
    payload = bytearray(meta_rec.payload)
    payload[218:228] = ldb.ljust(5).encode("utf-16-le")
    return Record(offset=meta_rec.offset, rtype=meta_rec.rtype,
                  payload=bytes(payload), fragments=meta_rec.fragments)




# -- Source encoding for REPOS blocks ----------------------------------------

def encode_source_lines(source: str) -> list[bytes]:
    """
    Convert ABAP source text to a list of fixed-width REPOS source rows.

    Each row is UTF-16LE encoded. All rows in the returned list have the same
    byte-length, determined by the longest line in `source` (rounded up to an
    even number for valid UCS-2). Shorter lines are space-padded.
    """
    raw_lines = source.split("\n")
    # Strip trailing CR from each line
    lines = [l.rstrip("\r") for l in raw_lines]

    if not lines:
        return []

    # Determine max byte width from the longest UTF-16LE-encoded line
    max_width = 0
    for line in lines:
        encoded = line.encode("utf-16-le")
        max_width = max(max_width, len(encoded))

    # Round up to even (valid UTF-16LE)
    if max_width % 2:
        max_width += 2  # ensure even -- should already be even for UTF-16LE

    # Pad all lines to max_width
    rows = []
    for line in lines:
        encoded = line.encode("utf-16-le")
        if len(encoded) < max_width:
            # Pad with UTF-16LE spaces: U+0020 = b'\x20\x00' -- NOT b'\x00\x20'
            # (that is U+2000 EN QUAD; RSYN reports it as a bogus statement).
            pad_needed = max_width - len(encoded)
            encoded += b"\x20\x00" * (pad_needed // 2)
        rows.append(encoded)
    return rows


# -- REPOS block key helpers -------------------------------------------------

def build_repos_key(obj_type: str, obj_name: str, include_suffix: str) -> str:
    """
    Build the REPOS key from object name and include suffix.
    Matches how SAP formats REPOS keys for each object type.
    """
    if obj_type in ("CLAS", "INTF", "ENHO"):
        padded = obj_name.ljust(30, "=")
        return padded + include_suffix
    elif obj_type == "TYPE":
        # A type group has exactly two REPOS keys (verified against the
        # real template export): the declarative body under the SAME
        # ljust(30,'=')+suffix padding CLAS/INTF/ENHO use (suffix 'TT'),
        # and the auto-generated '%_C<name>' boilerplate include (NOT
        # padded -- an unpadded program-name-shaped key, like PROG's own
        # main include).
        if include_suffix == "TT":
            return obj_name.ljust(30, "=") + "TT"
        return f"%_C{obj_name}"
    elif obj_type == "FUGR":
        # The namespace prefix stays in front: /NS/GRP -> /NS/SAPLGRP,
        # /NS/LGRPTOP.
        namespace, base = "", obj_name
        if obj_name.startswith("/") and "/" in obj_name[1:]:
            cut = obj_name.index("/", 1) + 1
            namespace, base = obj_name[:cut], obj_name[cut:]
        if include_suffix in ("", "MAIN"):
            return f"{namespace}SAPL{base}"
        else:
            return f"{namespace}L{base}{include_suffix}"
    else:
        # PROG: use include name directly
        if include_suffix == "":
            return obj_name
        else:
            return f"{obj_name}_{include_suffix}"


def make_repos_block_records(obj_name: str, include_key: str,
                               source: str, template_h: Record,
                               template_meta: Record) -> list[Record]:
    """
    Create REPOS block records: [H, meta, source_lines..., COMMIT, E].

    Copies the H and meta records from the template, with the key replaced.
    Source lines are encoded from the actual source content.
    """
    # Copy H record, replacing the key at offset 48
    h_payload = bytearray(template_h.payload)
    key_area = h_payload[48:]
    new_key_bytes = include_key.encode("latin-1")
    new_key_bytes = new_key_bytes.ljust(len(key_area), b" ")
    new_key_bytes = new_key_bytes[:len(key_area)]
    h_payload[48:] = new_key_bytes
    h_rec = Record(offset=0, rtype="H", payload=bytes(h_payload), fragments=1)

    # Copy metadata row (628B) -- renames applied later
    meta_rec = Record(offset=0, rtype=" ", payload=template_meta.payload,
                      fragments=template_meta.fragments)

    # Encode source lines
    source_rows = encode_source_lines(source)
    source_recs = [Record(offset=0, rtype=" ", payload=row, fragments=1)
                   for row in source_rows]

    # COMMIT marker + End marker
    commit_rec = Record(offset=0, rtype="*", payload=b"COMMIT", fragments=1)
    end_rec = Record(offset=0, rtype="E", payload=b"", fragments=1)

    return [h_rec, meta_rec] + source_recs + [commit_rec, end_rec]


# -- Class (CLAS) source splitting -----------------------------------------
#
# A .clas.abap file holds two top-level blocks:
#   CLASS <name> DEFINITION ... ENDCLASS.        -> the CU include
#   CLASS <name> IMPLEMENTATION ... ENDCLASS.    -> CI (whole) or CM### (per
#                                                   method, mirroring the
#                                                   template's CM001 block)
#
# The template's own CU include is the DEFINITION block *without* ENDCLASS
# (the class pool emits it), but we ship the block verbatim WITH its
# ENDCLASS: the include contents stay complete statements either way, and
# keeping the block intact is what an abapGit source round-trip proves.

_CLASS_BLOCK_RE = re.compile(
    r"^\s*CLASS\s+([\w/~]+)\s+(DEFINITION|IMPLEMENTATION)\b",
    re.IGNORECASE)
_ENDCLASS_RE = re.compile(r"^\s*ENDCLASS\b", re.IGNORECASE)
# \b (not \s*\.) so trailing pseudo-comments like ##ADT_SUPPRESS_GENERATION
# after the method name do not break the match.
_METHOD_RE = re.compile(r"^ {0,2}METHOD\s+([\w~/]+)\b", re.IGNORECASE)
_ENDMETHOD_RE = re.compile(r"^ {0,2}ENDMETHOD\b", re.IGNORECASE)


def extract_class_blocks(source: str):
    """
    Split a .clas.abap into its top-level DEFINITION and IMPLEMENTATION
    blocks. Returns (definition, implementation) -- each the block text
    INCLUDING the CLASS header and ENDCLASS (None if not found).

    A depth counter over CLASS...DEFINITION/IMPLEMENTATION vs ENDCLASS keeps
    nested local classes inside the blocks from confusing the split.
    """
    text = source.replace("\r\n", "\n").replace("\r", "\n")
    blocks = {"DEFINITION": [], "IMPLEMENTATION": []}
    depth = 0
    cur = None
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith("*"):
            # comments and blank lines cannot open or close a block
            if cur is not None:
                blocks[cur].append(line)
            continue
        hdr = _CLASS_BLOCK_RE.match(line)
        if hdr:
            if depth == 0:
                cur = hdr.group(2).upper()
            depth += 1
            if cur is not None:
                blocks[cur].append(line)
            continue
        if _ENDCLASS_RE.match(line) and depth > 0:
            # the ENDCLASS belongs to the block it closes -- nested and
            # top-level alike
            if cur is not None:
                blocks[cur].append(line)
            depth -= 1
            if depth == 0:
                cur = None
            continue
        if cur is not None:
            blocks[cur].append(line)
    def_block = ("\n".join(blocks["DEFINITION"]) or None)
    impl_block = ("\n".join(blocks["IMPLEMENTATION"]) or None)
    return def_block, impl_block


def split_implementation_methods(impl_lines: list) -> "list | None":
    """
    Split an implementation block's lines into METHOD...ENDMETHOD blocks at
    column 0-2 (the class's own methods; deeper-indented METHODs belong to
    local classes and stay inside the enclosing method's body).

    Returns a list of (method_name, [lines]) or None when the split is not
    robust: an unbalanced METHOD, or a non-comment statement outside any
    method (content a CM###-based layout would lose). The caller then ships
    the whole implementation in CI instead.
    """
    methods = []
    cur_name = None
    body = []
    class_depth = 0
    stray = []
    for line in impl_lines[1:]:        # [0] is the CLASS...IMPLEMENTATION header
        stripped = line.strip()
        if not stripped or stripped.startswith("*"):
            if cur_name is not None:
                body.append(line)
            continue
        if _CLASS_BLOCK_RE.match(line):
            class_depth += 1
            if cur_name is not None:
                body.append(line)
            continue
        if _ENDCLASS_RE.match(line):
            if class_depth > 0:
                class_depth -= 1
                if cur_name is not None:
                    body.append(line)
            continue
        m = _METHOD_RE.match(line)
        if m and class_depth == 0 and cur_name is None:
            cur_name = m.group(1)
            body = [line]
            continue
        if cur_name is not None:
            body.append(line)
            if _ENDMETHOD_RE.match(line):
                methods.append((cur_name, body))
                cur_name = None
                body = []
            continue
        stray.append(line)             # statement outside a method
    if cur_name is not None or stray:
        return None
    return methods


def base36(n: int) -> str:
    """SAP numbers CM includes 0-9A-Z after the ninth method: CM001..CM009,
    CM00A..CM00Z, CM010... (verified in a real 53-object export)."""
    digits = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    out = ""
    while n:
        n, r = divmod(n, 36)
        out = digits[r] + out
    return out or "0"


def split_class_source(source: str):
    """
    Split a .clas.abap into include contents.

    Returns (definition, implementation, methods):
      definition / implementation: the two top-level block texts (None if
        the file does not parse as DEFINITION/IMPLEMENTATION at all)
      methods: list of (name, lines) for the implementation's METHOD blocks,
        or None when the split is not robust (whole implementation -> CI)
    """
    definition, implementation = extract_class_blocks(source)
    if definition is None and implementation is None:
        print("  WARNING: .clas.abap has no CLASS ... DEFINITION / "
              "IMPLEMENTATION blocks -- shipping whole source in CI")
        return None, None, None
    methods = None
    if implementation is not None:
        methods = split_implementation_methods(implementation.split("\n"))
    return definition, implementation, methods


# -- Source -> REPOS include mapping ----------------------------------------

def map_source_to_includes(obj_type: str, obj_name: str,
                             sources: dict[str, str],
                             mode: str = "cm"
                             ) -> "tuple[list, dict]":
    """
    Map abapGit source files to REPOS include keys.
    Returns (list of (include_key, include_suffix, source_text), cm_methods)
    where cm_methods maps the CM### include key (upper) to its method name.

    For CLAS, the main .clas.abap is split by _map_class_sources: the
    DEFINITION block -> CU, each METHOD -> a CM### include (mode="cm",
    mirroring the template's CM001 block) or the whole IMPLEMENTATION -> CI
    (mode="ci"), and the CP include is regenerated as class-pool boilerplate.
    """
    if obj_type == "CLAS":
        return _map_class_sources(obj_name, sources, mode)

    mapping = []
    cm_methods = {}

    for src_name, src_text in sources.items():
        if obj_type == "PROG":
            if src_name.upper() == obj_name.upper():
                mapping.append((obj_name, "", src_text))
            else:
                # Extract suffix from include name
                upper_obj = obj_name.upper()
                upper_src = src_name.upper()
                if upper_src.startswith(upper_obj + "_"):
                    suffix = upper_src[len(upper_obj) + 1:]
                else:
                    suffix = upper_src.rsplit("_", 1)[-1]
                include_key = _build_repos_key(obj_type, obj_name, suffix)
                mapping.append((include_key, suffix, src_text))

        elif obj_type == "INTF":
            if "============" in src_name:
                suffix = src_name.rsplit("=", 1)[-1]
                include_key = src_name
            else:
                suffix = "IU"
                include_key = _build_repos_key("INTF", obj_name, "IU")
            mapping.append((include_key, suffix, src_text))

        elif obj_type == "FUGR":
            # The include key was already resolved by collect_sources from
            # the file name (real abapGit FUGR convention: `sapl<grp>.abap`
            # -> SAPL<grp>, `l<grp><suffix>.abap` -> L<grp><suffix>,
            # `<fmname>.abap` -> L<grp>U<n> from the .fugr.xml FUNCTIONS
            # order). Derive the suffix from the key itself.
            include_key = src_name
            upper_obj = obj_name.upper().replace("/", "")
            upper_key = include_key.upper()
            if upper_key.startswith("SAPL"):
                suffix = ""
            elif upper_key.startswith("L" + upper_obj):
                suffix = include_key[len("L" + upper_obj):]
            else:
                suffix = include_key
            mapping.append((include_key, suffix, src_text))

        elif obj_type == "ENHO":
            # collect_sources already resolved the full REPOS key ("NAME
            # =========E" for the synthesized master include, "NAME
            # =========EM001"/EM002/... for each new method's real body) --
            # same "key already resolved by the file name/index" pattern
            # as FUGR above. The suffix (everything after the '='-padded
            # name) is only used informationally downstream (CLAS's own
            # CM### special case is the only thing that reads it).
            padded_name = obj_name.ljust(30, "=")
            suffix = (src_name[len(padded_name):] if src_name.upper()
                      .startswith(padded_name.upper()) else src_name)
            mapping.append((src_name, suffix, src_text))

        elif obj_type == "TYPE":
            # collect_sources already resolved both full REPOS keys (the
            # synthesized '%_C<name>' boilerplate and the real
            # '<name>=========================TT' body, empty string when
            # the type group declares nothing) -- same "key already
            # resolved by the caller" pattern as FUGR/ENHO above.
            include_key = src_name
            suffix = "C" if src_name.upper().startswith("%_C") else "TT"
            mapping.append((include_key, suffix, src_text))

    return mapping, cm_methods


def map_class_sources(obj_name: str, sources: dict,
                       mode: str = "cm") -> "tuple[list, dict]":
    """
    Build the REPOS include mapping for one CLAS object.

    The DEFINITION is split into CU/CO/CI (public/protected/private section).
    mode="cm": one CM### include per implementation METHOD (the template's
    CM001 layout), pulled into CP with `include methods.`
    mode="ci" (historic name; used when the method split is not robust): the
    whole IMPLEMENTATION block is written straight into CP.

    Local includes (locals_def/locals_imp/macros/testclasses) map to
    CCDEF/CCIMP/CCMAC/CCAU; untouched ones ship the class builder's stubs so
    every include CP names exists. Returns (mapping, cm_methods).
    """
    main_src = sources.get(obj_name)
    locals_ = {}
    for src_name, src_text in sources.items():
        if src_name == obj_name:
            continue
        # include keys are <class name '='-padded to 30><suffix>; the padding
        # is anything from 0 to 29 characters, so cut by position
        suffix = src_name[30:]
        locals_[suffix.upper()] = (src_name, suffix, src_text)

    entries = []
    cm_methods = {}
    impl_inline = None
    definition = implementation = methods = None
    if main_src is not None:
        definition, implementation, methods = _split_class_source(main_src)
    if definition is None:
        raise ValueError(f"CLAS {obj_name}: no CLASS ... DEFINITION block "
                         f"found in the .clas.abap source")
    for suffix, text in zip(("CU", "CO", "CI"),
                            _split_definition_sections(definition)):
        entries.append((_build_repos_key("CLAS", obj_name, suffix), suffix, text))
    if mode == "cm" and methods:
        for i, (mname, body) in enumerate(methods, start=1):
            suffix = "CM" + _base36(i).rjust(3, "0")
            key = _build_repos_key("CLAS", obj_name, suffix)
            entries.append((key, suffix, "\n".join(body)))
            cm_methods[key.upper()] = mname.upper()
    elif implementation is not None and (methods is None or mode != "cm"):
        impl_inline = implementation
    for suffix, stub in _CLASS_LOCAL_STUBS.items():
        if suffix not in locals_:
            locals_[suffix] = (_build_repos_key("CLAS", obj_name, suffix),
                               suffix, stub)
    entries += list(locals_.values())
    entries.append((_build_repos_key("CLAS", obj_name, "CT"), "CT",
                    '*"* dummy include to reduce generation dependencies between\n'
                    f'*"* class {obj_name} and it\'s users.\n'
                    '*"* touched if any type reference has been changed'))

    cp_key = _build_repos_key("CLAS", obj_name, "CP")
    entries.append((cp_key, "CP",
                    _class_pool_boilerplate(obj_name,
                                            has_ccau="CCAU" in locals_,
                                            implementation=impl_inline)))
    return entries, cm_methods


# -- Core generation --------------------------------------------------------

def interface_pool_boilerplate(obj_name: str) -> str:
    """The IP include boilerplate SAP generates for an interface pool.
    The include statement must reference the IU include with the '='
    padding normalized to the object's actual name length."""
    padded = obj_name.ljust(30, "=")
    return (f"interface-pool.\n"
            f'*"* class pool for interface {obj_name}\n'
            f"\n"
            f"  include {padded}iu.")


def class_pool_boilerplate(obj_name: str, has_ccau: bool = False,
                            implementation: "str | None" = None) -> str:
    """
    The CP include (class pool) for a generated class -- the class builder's
    own layout, line for line from the CLAS template's CP: the three section
    includes closed by `endclass.`, the local includes, then the method
    implementations via `include methods.` (the CM### includes).

    `implementation` replaces the `include methods.` block with the literal
    IMPLEMENTATION text when the source could not be split into methods.
    '=' padding is normalized to the object's real name length.
    """
    padded = obj_name.ljust(30, "=")
    lines = ["class-pool .",
             f'*"* class pool for class {obj_name}',
             "",
             '*"* local type definitions',
             f"include {padded}ccdef.",
             "",
             f'*"* class {obj_name} definition',
             '*"* public declarations',
             f"  include {padded}cu.",
             '*"* protected declarations',
             f"  include {padded}co.",
             '*"* private declarations',
             f"  include {padded}ci.",
             f'endclass. "{obj_name} definition',
             "",
             '*"* macro definitions',
             f"include {padded}ccmac.",
             '*"* local class implementation',
             f"include {padded}ccimp.",
             ""]
    if has_ccau:
        lines += ['*"* test class',
                  f"include {padded}ccau.",
                  ""]
    if implementation is not None:
        lines += implementation.split("\n")
    else:
        lines += [f"class {obj_name} implementation.",
                  "*\"* method's implementations",
                  "  include methods.",
                  f'endclass. "{obj_name} implementation']
    return "\n".join(lines)


def make_cm_h_record(h_template: Record, rule: RenameRule,
                      suffix: str, method_name: str) -> Record:
    """
    Build an ABAPREAD H record for a CM### method include.

    The key packs four fixed-width subfields (verified byte for byte
    against the template's CM001 block and the real 53-object export):
      [0:30]   include name, '='-padded
      [30:60]  include suffix (e.g. CM001), space-padded
      [60:120] filler (spaces)
      [120:150] class name, space-padded
      [150:240] method name, space-padded (interface methods keep the
               'IFACE~METHOD' prefix here -- verified in the real export)
    """
    payload = bytearray(h_template.payload)
    name = rule.new_name
    if len(name) > 30:
        raise ValueError(
            f"class name too long for a CM### include key "
            f"({len(name)} > 30 chars): {name}")
    key = (name.ljust(30, "=") + suffix.ljust(30) + " " * 60
           + name.ljust(30) + method_name.ljust(90))
    area = len(payload) - 48
    if len(key) > area:
        raise ValueError(f"CM### key too long for H record: {key!r}")
    payload[48:] = key.encode("latin-1").ljust(area, b" ")
    return Record(offset=0, rtype="H", payload=bytes(payload), fragments=1)


def make_cm_block_records(obj_name: str, include_key: str,
                           method_name: str, source: str,
                           template_h: Record, template_meta: Record,
                           rule: RenameRule) -> list:
    """
    Create the records of a CM### method-include block:
    [H (00MMRG, packed key), meta, source rows..., COMMIT, E].

    Mirrors the template's CM001 block: same action (merge), same key
    packing, METHOD...ENDMETHOD content.
    """
    suffix = include_key[len(obj_name.ljust(30, "=")):]
    h_rec = make_cm_h_record(template_h, rule, suffix, method_name)
    meta_rec = Record(offset=0, rtype=" ",
                      payload=template_meta.payload,
                      fragments=template_meta.fragments)
    commit_rec = Record(offset=0, rtype="*", payload=b"COMMIT", fragments=1)
    end_rec = Record(offset=0, rtype="E", payload=b"", fragments=1)
    return ([h_rec, meta_rec]
            + [Record(offset=0, rtype=" ", payload=row, fragments=1)
               for row in encode_source_lines(source)]
            + [commit_rec, end_rec])


def emit_repos_rows(out: list, records, i: int, h_rec: Record,
                     meta_rec, rows: list) -> int:
    """Append an ABAPREAD block (H + meta + the given pre-encoded source-
    line rows) to `out`, skipping the template's old rows up to and
    including COMMIT + E. Returns the new position in `records`.

    Factored out of emit_source_block so a caller with a genuinely EMPTY
    source (TYPE's TT include when the type group declares nothing -- see
    the real template export) can pass `rows=[]` directly and ship ZERO
    source-line records, instead of encode_source_lines("") synthesizing
    one spurious blank line."""
    out.append(h_rec)
    i += 1
    if meta_rec is not None:
        out.append(meta_rec)
        i += 1
    for row in rows:
        out.append(Record(offset=0, rtype=" ", payload=row, fragments=1))
    while i < len(records):
        if records[i].rtype == "*" and records[i].payload == b"COMMIT":
            out.append(records[i])
            i += 1
            break
        i += 1
    if i < len(records) and records[i].rtype == "E":
        out.append(records[i])
        i += 1
    return i


def emit_source_block(out: list, records, i: int, h_rec: Record,
                       meta_rec, source: str) -> int:
    """Append an ABAPREAD block (H + meta + encoded source rows) to `out`,
    skipping the template's old rows up to and including COMMIT + E.
    Returns the new position in `records`."""
    return emit_repos_rows(out, records, i, h_rec, meta_rec,
                            encode_source_lines(source))
