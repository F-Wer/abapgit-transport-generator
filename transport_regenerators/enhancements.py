"""ENHO and BAdI enhancement-template regeneration helpers."""

import struct
from collections.abc import Callable

from sap_transport_records import Record
from transport_templates import TEMPLATES, template_name


_helpers: dict[str, Callable] = {}


def configure_enhancement_helpers(**helpers: Callable) -> None:
    """Configure shared facade helpers used by ENHO regeneration."""
    _helpers.update(helpers)


def _helper(name: str) -> Callable:
    try:
        return _helpers[name]
    except KeyError as exc:
        raise RuntimeError(f"ENHO helper {name!r} has not been configured") from exc


def _build_repos_key(*args, **kwargs):
    return _helper("build_repos_key")(*args, **kwargs)


def _find_block(*args, **kwargs):
    return _helper("find_block")(*args, **kwargs)


# What the ENHO templates contain (the "search" side of every rewrite)
# is listed under "names" in templates.json, next to the template files.


def _make_enho_master_include_source(obj_name: str, enho_meta: dict) -> str:
    """
    Synthesize the class enhancement's master REPOS include (key suffix
    "E"). abapGit's .enho.xml never serializes this text directly -- only
    the structured METH_HEADER/METH_PARAM data it's derived from; SAP's own
    enhancement framework generates it when a change is saved in the
    Class Builder. Reproduces the exact shape found in the real template
    object: 8 "ENHANCEMENT n . / ENDENHANCEMENT." wrapper blocks -- 5 empty
    historical placeholders, block 6 holding the new method's
    class-methods declaration, block 7 empty, block 8 holding the INCLUDE
    statement for the method body. Only the single-new-method,
    IMPORTING-only-parameters case is exercised against real content (see
    ENHO_CLUSTER_FORMAT_PROGRESS.md) -- other PARPASSTYP values (EXPORTING/
    CHANGING/RETURNING) fall back to "importing" with a warning rather than
    guessing unverified syntax.
    """
    lines = []
    for n in range(1, 6):
        lines.append(f"ENHANCEMENT {n} .")
        lines.append("ENDENHANCEMENT.")
    lines.append("ENHANCEMENT 6 .")
    lines.append("")
    methods = enho_meta.get("methods") or []
    if methods:
        method = methods[0]
        lines.append(f"  class-methods {method['name']}")
        params = method.get("params") or []
        if params:
            for p in params:
                if p.get("parpasstyp") not in ("", "1"):
                    print(f"  WARNING: ENHO parameter {p.get('sconame')!r} "
                          f"has PARPASSTYP={p.get('parpasstyp')!r} (not the "
                          f"only verified value, '1'=importing) -- treating "
                          f"as importing anyway, syntax not confirmed for "
                          f"other passing types")
            lines.append("    importing")
            for i, p in enumerate(params):
                terminator = " ." if i == len(params) - 1 else ""
                lines.append(f"      !{p['sconame']} type {p['type']}{terminator}")
        else:
            # No parameters: the declaration line itself ends the statement.
            lines[-1] = lines[-1] + " ."
    lines.append("ENDENHANCEMENT.")
    lines.append("ENHANCEMENT 7 .")
    lines.append("ENDENHANCEMENT.")
    lines.append("ENHANCEMENT 8 .")
    lines.append(f"INCLUDE {_build_repos_key('ENHO', obj_name, 'EM001')}.")
    lines.append("ENDENHANCEMENT.")
    return "\n".join(lines) + "\n"


def _read_bc_field(payload: bytes, marker_pos: int) -> "tuple[int, int]":
    """Given the byte offset of a 'BC' field-tag byte, return
    (value_start_offset, declared_length_in_bytes)."""
    assert payload[marker_pos] == 0xBC, (
        f"not a BC field marker at {marker_pos}: {payload[marker_pos]:#x}")
    length = struct.unpack_from(">I", payload, marker_pos + 1)[0]
    return marker_pos + 5, length


def _locate_enho_bc_markers(payload: bytes, known_values: list,
                            max_back: int = 5000) -> "set[int]":
    """
    Find every 'BC'-marked field in ENHHEADER-DATA's payload whose decoded
    value CONTAINS one of `known_values` as a substring -- i.e. every field
    this generator might need to rewrite, discovered the same way the
    reverse-engineering round found them, rather than hardcoded byte
    offsets.

    Two shapes, both real (confirmed against CLASENH's and BADI_IMPL's own
    ENHHEADER-DATA -- see ENHO_CLUSTER_FORMAT_PROGRESS.md and
    DOMA_VIEW_TYPE_ENHO_BADI_PROGRESS.md):
    - the marker sits exactly 5 bytes before the value (tag + 4-byte
      length) -- true for every CLASENH field and BADI_IMPL's smaller
      fields (the header composite, the per-filter-name entries, the
      short text, the standalone SPOT_NAME reference).
    - the value is buried further inside a LARGER composite field whose
      OWN marker is further back -- true for BADI_IMPL's per-filter-VALUE
      composites (each ~1-1.6K chars, packing filter name + type +
      compare + value together). Found by scanning backward (bounded by
      `max_back`) for the nearest preceding 0xBC byte whose declared
      [start, start+length) span actually contains the match -- not just
      the nearest 0xBC byte, since binary framing can contain incidental
      0xBC bytes that aren't real markers.

    Safe against false positives in both cases: a candidate marker is only
    accepted if decoding its declared length places the real string
    genuinely inside its span.
    """
    positions = set()
    for value in known_values:
        if not value:
            continue
        needle = value.encode("utf-16-le")
        start = 0
        while True:
            p = payload.find(needle, start)
            if p == -1:
                break
            start = p + 1
            if p >= 5 and payload[p - 5] == 0xBC:
                positions.add(p - 5)
                continue
            for m in range(p, max(0, p - max_back), -1):
                if payload[m] != 0xBC:
                    continue
                length = struct.unpack_from(">I", payload, m + 1)[0]
                vstart = m + 5
                if vstart <= p < vstart + length and length < 20000:
                    positions.add(m)
                    break
    return positions


def _rewrite_bc_field_text(payload: bytearray, marker_pos: int,
                           replacements: list, label: str = "") -> bool:
    """
    In-place rename within one BC-marked fixed-width field of ENHHEADER-
    DATA's RAW payload. For each (old, new) pair present in the field's own
    decoded text, replaces old->new, absorbing any length change into
    whichever padding character (' ' or '=') immediately follows the
    matched substring WITHIN THIS SAME FIELD -- the RAW-blob analog of
    _rename_key_preserving_width's "absorb into the name's own trailing
    padding, never touch anything past it" discipline already used for
    ATAB/DLIB H-record keys and REPOS '='-padded include keys elsewhere in
    this project. This is what makes it safe to reuse on fields with
    different tail conventions (plain space padding, an apparent NUL
    terminator, a trailing '=='-style REPOS-key suffix, a numeric sequence
    suffix like "001") without needing to know which shape applies -- the
    algorithm never writes past the padding run it measured, so whatever
    comes after that run (terminator, suffix, more content) is untouched.

    Handles a value appearing MORE THAN ONCE within the same field (e.g.
    the method-header composite's METHKEY repeated twice) by looping.

    Raises ValueError if a replacement doesn't fit even after absorbing all
    available same-kind padding -- a real implementation limit (new value
    too long for this real template's field width), not something to
    silently truncate and risk corrupting neighbouring content.

    Returns True if anything changed.
    """
    value_start, length = _read_bc_field(bytes(payload), marker_pos)
    raw = bytes(payload[value_start:value_start + length])
    text = raw.decode("utf-16-le", errors="replace")
    original = text
    for old, new in replacements:
        if not old or old == new:
            continue
        search_from = 0
        while True:
            idx = text.find(old, search_from)
            if idx == -1:
                break
            end = idx + len(old)
            pad_char = text[end] if end < len(text) else " "
            pad_char = pad_char if pad_char in (" ", "=") else " "
            pad_end = end
            while pad_end < len(text) and text[pad_end] == pad_char:
                pad_end += 1
            avail_width = pad_end - idx
            if len(new) > avail_width:
                raise ValueError(
                    f"ENHO field {label!r} at payload offset {marker_pos}: "
                    f"{new!r} ({len(new)} chars) does not fit in the "
                    f"{avail_width}-char space available after {old!r} "
                    f"(field width {length // 2} chars total)")
            replacement_text = new.ljust(avail_width, pad_char)
            text = text[:idx] + replacement_text + text[pad_end:]
            search_from = idx + len(replacement_text)
    if text == original:
        return False
    encoded = text.encode("utf-16-le")
    assert len(encoded) == length, (
        f"internal error: rewritten ENHO field {label!r} changed length "
        f"({len(encoded)} vs declared {length})")
    payload[value_start:value_start + length] = encoded
    return True


def _regenerate_enho_data_blob(records: list, obj_name: str, rule: "RenameRule",
                               enho_meta: dict) -> list:
    """
    Rewrite ENHHEADER-DATA's RAW long-value field in place using the field
    map from ENHO_CLUSTER_FORMAT_PROGRESS.md. ENHOBJCONTRACT-CONTRACTDATA
    (the object's other big RAW field) is left completely untouched -- it
    was verified to contain none of the object's own identifying content.
    """
    blk = _find_block(records, "ENHHEADER")
    if blk is None:
        return records
    h_idx, _row_idxs, e_idx = blk
    r_idxs = [i for i in range(h_idx + 1, e_idx) if records[i].rtype == "R"]
    if not r_idxs:
        return records
    if len(r_idxs) > 1:
        print(f"  WARNING: {obj_name}: ENHHEADER has {len(r_idxs)} RAW rows, "
              f"expected 1 -- only the first is rewritten")
    r_idx = r_idxs[0]
    payload = bytearray(records[r_idx].payload)

    if TEMPLATES["ENHO"]["object"].encode("utf-16-le") not in bytes(payload):
        print(f"  WARNING: {obj_name}: ENHHEADER RAW payload does not "
              f"contain the expected template object name "
              f"{TEMPLATES["ENHO"]["object"]!r} -- template may have changed; "
              f"binary metadata NOT rewritten (shipping stale content)")
        return records

    new_class = enho_meta.get("class") or template_name("ENHO", "class")
    methods = enho_meta.get("methods") or []
    method = methods[0] if methods else None
    if len(methods) > 1:
        print(f"  WARNING: {obj_name}: .enho.xml declares {len(methods)} "
              f"new methods -- ENHHEADER's binary metadata only reflects "
              f"the first ({methods[0]['name']!r}); the others' source "
              f"still gets injected via the generic new-REPOS-block "
              f"fallback, but the framework's own method registry will "
              f"only know about the first one (documented limitation)")
    new_method = (method["name"] if method and method.get("name")
                 else template_name("ENHO", "method"))
    new_method_descr = (method.get("descript", "") if method
                        else template_name("ENHO", "method_descr")) or template_name("ENHO", "method_descr")
    params = (method.get("params") or []) if method else []
    param = params[0] if params else None
    if len(params) > 1:
        print(f"  WARNING: {obj_name}: method {new_method!r} declares "
              f"{len(params)} parameters -- ENHHEADER's binary metadata "
              f"only reflects the first ({params[0]['sconame']!r}); the "
              f"master include's synthesized declaration lists all of "
              f"them, but this is a documented limitation")
    new_param_name = (param["sconame"] if param and param.get("sconame")
                      else template_name("ENHO", "param_name"))
    new_param_descr = (param.get("descript", "") if param
                       else template_name("ENHO", "param_descr")) or template_name("ENHO", "param_descr")
    new_param_type = (param.get("type", "") if param
                      else template_name("ENHO", "param_type")) or template_name("ENHO", "param_type")

    all_replacements = [
        (TEMPLATES["ENHO"]["object"], rule.new_name),
        (template_name("ENHO", "class"), new_class),
        (template_name("ENHO", "method"), new_method),
        (template_name("ENHO", "method_descr"), new_method_descr),
        (template_name("ENHO", "param_name"), new_param_name),
        (template_name("ENHO", "param_descr"), new_param_descr),
        (template_name("ENHO", "param_type"), new_param_type),
    ]
    known_old_values = [pair[0] for pair in all_replacements]
    marker_positions = _locate_enho_bc_markers(bytes(payload), known_old_values)

    changed = 0
    for marker_pos in sorted(marker_positions):
        try:
            if _rewrite_bc_field_text(payload, marker_pos, all_replacements,
                                      label=f"ENHHEADER@{marker_pos}"):
                changed += 1
        except ValueError as exc:
            print(f"  WARNING: {obj_name}: {exc} -- field left at template "
                  f"value")
    print(f"  ENHO ENHHEADER-DATA: rewrote {changed}/{len(marker_positions)} "
          f"fixed-width fields (class={new_class!r} method={new_method!r}"
          + (f" param={new_param_name!r}" if param or params == [] else "")
          + ")")

    records[r_idx] = Record(offset=records[r_idx].offset, rtype="R",
                            payload=bytes(payload),
                            fragments=records[r_idx].fragments)
    return records


def _apply_enho_badi_positional_replacements(payload: bytearray, obj_name: str,
                                              template_old_values: list,
                                              new_values: list,
                                              field_label: str) -> int:
    """
    Rewrite BC-marked fields for a per-slot template value list (filter
    names or filter char values) where the SAME old value can legitimately
    repeat across multiple flat filter slots (index 0..3, in
    root1.filter1/root1.filter2/root2.filter1/root2.filter2 order) while
    needing a DIFFERENT new value per slot -- a genuine OR-of-ANDs filter
    condition confirmed against the real BADI_IMPL template object, not a
    test artifact. A single shared old->new replacement list can't tell
    these slots apart (the first matching pair wins regardless of which
    slot's field is being processed), so each old value's occurrences are
    resolved positionally instead: every BC field containing that old
    value is located, grouped by field byte-width (each width is one
    structural "view" of the filter data -- the small per-filter-ID entry,
    the FILTER_VALUES composite, the FILTERS composite -- all of which lay
    slots out in the same ascending order as the template itself), and
    within each width-group the N matches (sorted by byte position) are
    zipped 1:1, in order, against the N template slots that share that old
    value.

    Returns the number of fields actually changed.
    """
    changed = 0
    distinct_olds = sorted({v for v in template_old_values if v})
    for old in distinct_olds:
        slot_idxs = [i for i, v in enumerate(template_old_values) if v == old]
        wanted = [new_values[i] for i in slot_idxs]
        if all(w is None or w == old for w in wanted):
            continue
        positions = sorted(_locate_enho_bc_markers(bytes(payload), [old]))
        by_length: dict = {}
        for pos in positions:
            _vs, length = _read_bc_field(bytes(payload), pos)
            by_length.setdefault(length, []).append(pos)
        for length, group_positions in by_length.items():
            group_positions.sort()
            if len(group_positions) != len(slot_idxs):
                print(f"  WARNING: {obj_name}: {field_label} old value "
                      f"{old!r}: found {len(group_positions)} field(s) of "
                      f"width {length} but template has {len(slot_idxs)} "
                      f"slot(s) using it -- skipping this group, shipping "
                      f"template value(s) unchanged")
                continue
            for pos, slot_i, new in zip(group_positions, slot_idxs, wanted):
                if new is None or new == old:
                    continue
                try:
                    if _rewrite_bc_field_text(
                            payload, pos, [(old, new)],
                            label=f"{field_label}[slot{slot_i}]@{pos}"):
                        changed += 1
                except ValueError as exc:
                    print(f"  WARNING: {obj_name}: {exc} -- field left at "
                          f"template value")
    return changed


def _regenerate_enho_badi_data_blob(records: list, obj_name: str,
                                    rule: "RenameRule",
                                    enho_meta: dict) -> list:
    """
    Rewrite ENHHEADER-DATA's RAW long-value field in place for a
    TOOL=BADI_IMPL enhancement (a BAdI implementation), the sibling of
    _regenerate_enho_data_blob (which only covers TOOL=CLASENH). Field map
    confirmed against the real BADI_IMPL template object
    (the BADI_IMPL template) -- see
    DOMA_VIEW_TYPE_ENHO_BADI_PROGRESS.md.

    Same `BC`-marker grammar as CLASENH (see ENHO_CLUSTER_FORMAT_PROGRESS.md),
    but BADI_IMPL's filter data lives in composite fields whose OWN marker
    can sit much further back than the usual 5 bytes before the matched
    substring (the header/method fields' shape) -- _locate_enho_bc_markers'
    bounded backward-scan handles this generically, added specifically for
    this type.

    Filter data (FILTER_ROOT/FILTER_VALUES) is only rewritten when the
    repo's own filter count/shape EXACTLY matches the template's real shape
    (2 filter roots, 2 filters each = 4 named-filter slots, 4 filter-value
    entries) -- a genuinely different filter count (including zero, which
    the OTHER real BADI_IMPL sample in the same delivery,
    another real implementation, actually has) is a real, disclosed
    limitation: the template's own stale filter data ships unchanged
    rather than attempting to add/remove slots inside the packed binary
    field (removing content from the middle of this format would need
    shifting every subsequent byte and adjusting length headers throughout
    -- out of scope for this round, the same class of limitation as TABL's
    DD05M/DD08V or ENHO/CLASENH's multiple-methods gap).

    Filter names and filter char-values are genuinely duplicated across
    slots in the real template (both filter roots filter on the same
    WORKFLOW_ID name/value, just different STEP_IDs -- a real OR-of-ANDs
    condition, not a test artifact), so they are deliberately NOT folded
    into the shared `all_replacements` list below (a single old->new pair
    can't represent "same old text, different new text depending on
    slot"). They're rewritten separately via
    _apply_enho_badi_positional_replacements, which resolves each
    occurrence to its flat slot by field position rather than by old-value
    match. Filter numeric-values stay in the shared list because the
    template's own numeric values are unique per slot (no collision to
    resolve).
    """
    blk = _find_block(records, "ENHHEADER")
    if blk is None:
        return records
    h_idx, _row_idxs, e_idx = blk
    r_idxs = [i for i in range(h_idx + 1, e_idx) if records[i].rtype == "R"]
    if not r_idxs:
        return records
    if len(r_idxs) > 1:
        print(f"  WARNING: {obj_name}: ENHHEADER has {len(r_idxs)} RAW rows, "
              f"expected 1 -- only the first is rewritten")
    r_idx = r_idxs[0]
    payload = bytearray(records[r_idx].payload)

    if TEMPLATES["ENHO_BADI"]["object"].encode("utf-16-le") not in bytes(payload):
        print(f"  WARNING: {obj_name}: ENHHEADER RAW payload does not "
              f"contain the expected BADI_IMPL template's own IMPL_NAME "
              f"{TEMPLATES["ENHO_BADI"]["object"]!r} -- template may have "
              f"changed; binary metadata NOT rewritten (shipping stale "
              f"content)")
        return records

    badi = enho_meta.get("badi") or {}
    new_spot_name = badi.get("spot_name") or template_name("ENHO_BADI", "spot_name")
    new_badi_name = badi.get("badi_name") or template_name("ENHO_BADI", "badi_name")
    new_impl_class = badi.get("impl_class") or template_name("ENHO_BADI", "impl_class")
    new_shorttext = (badi.get("impl_shorttext")
                     or template_name("ENHO_BADI", "impl_shorttext"))

    all_replacements = [
        (template_name("ENHO_BADI", "spot_name"), new_spot_name),
        (template_name("ENHO_BADI", "badi_name"), new_badi_name),
        (TEMPLATES["ENHO_BADI"]["object"], rule.new_name),
        (template_name("ENHO_BADI", "impl_class"), new_impl_class),
        (template_name("ENHO_BADI", "impl_shorttext"), new_shorttext),
    ]

    # Filter names: flatten the repo's own FILTER_ROOT into the same
    # [root1.filter1, root1.filter2, root2.filter1, root2.filter2] order
    # the template uses, and only map them 1:1 if the shape matches
    # exactly (2 roots x 2 filters). Kept OUT of all_replacements -- see
    # docstring -- and applied positionally below instead.
    repo_filter_names = []
    for root_entry in (badi.get("filter_root") or []):
        for f in root_entry.get("filters") or []:
            repo_filter_names.append(f.get("name", ""))
    new_names_by_slot = [None, None, None, None]
    if repo_filter_names and len(repo_filter_names) == len(
            template_name("ENHO_BADI", "filter_names")):
        for i, new in enumerate(repo_filter_names):
            if new:
                new_names_by_slot[i] = new
    elif repo_filter_names:
        print(f"  WARNING: {obj_name}: .enho.xml declares "
              f"{len(repo_filter_names)} filter(s), template has "
              f"{len(template_name("ENHO_BADI", "filter_names"))} -- filter names/"
              f"values NOT rewritten (shipping the template's own stale "
              f"filter data), only a matching count can be mapped 1:1")
    elif not repo_filter_names and any(
            template_name("ENHO_BADI", "filter_names")):
        print(f"  WARNING: {obj_name}: .enho.xml declares no filters, but "
              f"the template's own BADI_IMPL object has {len(template_name("ENHO_BADI", "filter_names"))} "
              f"-- the template's stale filter data ships unchanged (removing "
              f"it would require shifting the whole packed binary field, "
              f"out of scope this round)")

    repo_filter_values = list(badi.get("filter_values") or [])
    new_char_by_slot = [None, None, None, None]
    if repo_filter_values and len(repo_filter_values) == len(
            template_name("ENHO_BADI", "filter_char_values")):
        for i, v in enumerate(repo_filter_values):
            old_char = template_name("ENHO_BADI", "filter_char_values")[i]
            old_num = template_name("ENHO_BADI", "filter_numeric_values")[i]
            if old_char is not None and v.get("char_value1"):
                new_char_by_slot[i] = v["char_value1"]
            if old_num is not None and v.get("numeric_value1"):
                # NUMC-style right-justify, zero-pad to the SAME width as
                # the template's own value -- same length in, same length
                # out, so no field-width growth/shrink handling is needed.
                # Kept in the shared list: the template's numeric values
                # are unique per slot, so there's no collision to resolve.
                new_num = v["numeric_value1"].rjust(len(old_num), "0")
                if len(new_num) > len(old_num):
                    print(f"  WARNING: {obj_name}: filter value "
                          f"{v['numeric_value1']!r} is wider than the "
                          f"template's {len(old_num)}-digit field -- "
                          f"truncated")
                    new_num = new_num[-len(old_num):]
                all_replacements.append((old_num, new_num))
    elif repo_filter_values and repo_filter_names:
        print(f"  WARNING: {obj_name}: .enho.xml declares "
              f"{len(repo_filter_values)} filter value(s), template has "
              f"{len(template_name("ENHO_BADI", "filter_char_values"))} -- filter "
              f"values NOT rewritten (shipping the template's own stale "
              f"values)")

    known_old_values = [pair[0] for pair in all_replacements]
    marker_positions = _locate_enho_bc_markers(bytes(payload), known_old_values)

    changed = 0
    for marker_pos in sorted(marker_positions):
        try:
            if _rewrite_bc_field_text(payload, marker_pos, all_replacements,
                                      label=f"ENHHEADER@{marker_pos}"):
                changed += 1
        except ValueError as exc:
            print(f"  WARNING: {obj_name}: {exc} -- field left at template "
                  f"value")

    changed += _apply_enho_badi_positional_replacements(
        payload, obj_name, template_name("ENHO_BADI", "filter_names"),
        new_names_by_slot, "filter name")
    changed += _apply_enho_badi_positional_replacements(
        payload, obj_name, template_name("ENHO_BADI", "filter_char_values"),
        new_char_by_slot, "filter char value")

    print(f"  ENHO (BADI_IMPL) ENHHEADER-DATA: rewrote {changed} fixed-"
          f"width fields (spot={new_spot_name!r} badi={new_badi_name!r})")

    records[r_idx] = Record(offset=records[r_idx].offset, rtype="R",
                            payload=bytes(payload),
                            fragments=records[r_idx].fragments)
    return records


# -- Domain (DOMA) metadata --------------------------------------------------
#
# A domain has no ABAP source at all -- abapGit serializes it entirely as XML
# (<DD01V> header + an optional <DD07V_TAB> fixed-value list, the
# abap-file-formats DOMA schema; confirmed against real .doma.xml files from
# several public/local abapGit-managed repos -- see _parse_doma_xml's
# docstring for the exact sources). On the transport side a DOMA touches
# four tables: DD01L (header: base type/length/flags) and DD01T (one row
# per language: the domain's own description) -- the same two-table shape
# DTEL's DD04L/DD04T already established, confirmed directly against a real
# export (a real R3TR DOMA, see
# docs/doma-support.md) -- plus DD07L (one row per fixed value or range) and
# DD07T (one row per fixed value, parallel to DD07L by VALPOS, carrying the
# per-language text) when the domain has fixed values at all (VALEXI=X).
# DD07L/DD07T are an arbitrary-count pair, the same "regenerate wholesale
# from the XML's own count" shape MSAG's T100/T100U and TABL's DD03L already
# established -- unlike those, DOMA has TWO parallel variable-count tables
# (DD07L and DD07T), not one variable + one fixed, so both get their own
# donor-clone-per-entry loop below.
#
# DD01T and DD07T's H-record key packs DOMNAME(30, padded)+DDLANGUAGE(1)+'*'
# -- verified directly against the real export's bytes, the identical shape
# DTEL's DD04T (and TABL's DD02T) already established, so the existing
# _fix_dtel_ddlanguage_key (already documented as fully generic despite the
# name) is reused here rather than reimplemented. DD01L and DD07L's H-keys
# carry no language byte at all (just DOMNAME+'*'), confirmed the same way --
# the generic _rename_h_key already handles those correctly with no
# DOMA-specific fix needed.


# DD01L fields this generator ALWAYS writes from the repo's <DD01V> header,
# blanked when a field is absent -- see _regenerate_doma_rows for why (a
# real bug caught during development: a stale template VALEXI='X' left in
# place for a domain with no fixed values shipped a DDIC-inconsistent
# object). Admin/bookkeeping fields not in this list (AS4USER, AS4DATE,
# AS4TIME, AUTHCLASS, DOMMASTER, RESERVEDOM, DOMGLOBAL, APPENDNAME, APPEXIST,
# PROXYTYPE, OUTPUTSTYLE, AMPMFORMAT, AS4LOCAL, AS4VERS) are left at the
# template's own value, the same convention TABL's DD02L uses for its own
# unlisted header fields -- those have no XML equivalent at all, so there is
# nothing to go stale against.


# -- Search help (SHLP) metadata ---------------------------------------------
#
# A search help has no ABAP source at all -- like DOMA/TABL/VIEW, the whole
# object is DDIC metadata, serialized by abapGit as <name>.shlp.xml (schema
# confirmed against abapGit's own serializer, LCL_OBJECT_SHLP -- fetched from
# github.com/abapGit/abapGit's src/objects/zcl_abapgit_object_shlp.clas.abap
# -- plus five real .shlp.xml files: four elementary search helps pulled via
# `gh search code DD30V` (oisee/zllm's zllm_00sh_prompt_name.shlp.xml,
# DevEpos/abap-db-browser's zdbbr_dbtab_sh.shlp.xml, MDJoerg/MQBA's
# zmqba_shlp_param_name.shlp.xml, and this project's own local
# a real project's .shlp.xml -- the last one a
# genuine SELMTYPE=T table-based elementary help, the same shape as this
# generator's own reference object) and one genuine COLLECTIVE search help
# (abapkochbuch/Sources's zbook_ticket_coll.shlp.xml, 6 sub-search-helps).
#
# On the transport side a SHLP object touches (at minimum) five tables:
#
# - DD30L -- the header row: SHLPNAME, ISSIMPLE (elementary vs. collective),
#   SELMETHOD/SELMTYPE (the selection method -- a table, view, function
#   module, etc.), SELMEXIT, DIALOGTYPE, AUTOSUGGEST, FUZZY_SEARCH,
#   FUZZY_SIMILARITY (a PACKED DECIMAL field -- see below), ...
# - DD30T -- one row per language: the search help's own description.
# - DD31S -- the selection-method list: one row per sub-search-help
#   (SUBSHLP). An ELEMENTARY search help has exactly one row, its OWN name
#   as SUBSHLP (it IS its own only selection method); a COLLECTIVE search
#   help has one row per member sub-search-help.
# - DD32S -- the parameter list: one row per exported/imported field
#   (FIELDNAME/ROLLNAME/SHLPINPUT/SHLPOUTPUT/...).
# - DD33S -- the parameter-to-subhelp mapping: one row per (FIELDNAME,
#   SUBSHLP) pair, connecting each DD32S parameter to the DD31S sub-help(s)
#   that supply/consume it.
#
# abapGit's DD30V/DD31V_TABLE/DD32P_TABLE/DD33V_TABLE map onto these five
# tables (DD30V doubles as DD30L+DD30T -- DDLANGUAGE/DDTEXT travel directly
# in DD30V, the same "header carries the master-language text too" shape
# DOMA's DD01V and TABL's DD02V already established) with ONE
# genuinely-verified wrinkle:
#
# abapGit NEVER serializes <DD31V_TABLE>/<DD33V_TABLE> for an ELEMENTARY
# search help -- confirmed directly: the real .shlp.xml sample
# sample (SELMTYPE=T, the identical shape to this generator's own reference
# object) has NEITHER element at all, only <DD30V> and <DD32P_TABLE>. Read
# the abapGit source above: DDIF_SHLP_GET populates lt_dd31v/lt_dd33v from
# the DDIC, unconditionally, for every search help -- so this is not a
# serializer omission but a genuine fact about what SAP's own function
# module returns for an elementary help (nothing to reconnect a search help
# to itself). Yet this generator's own reference object's REAL transport
# section DOES carry one self-referencing DD31S row (SUBSHLP = its own name)
# and one DD33S row per parameter (mapping FIELDNAME -> SUBFIELD of the same
# name, SUBSHLP = its own name) -- genuine R3trans export content the DDIC
# activation step (DDIF_SHLP_PUT via CORR_INSERT) apparently regenerates
# from ISSIMPLE alone, since abapGit's own deserializer (DDIF_SHLP_PUT) is
# handed EMPTY lt_dd31v/lt_dd33v tables for this exact object shape and
# still produces a working search help when reimported by abapGit itself.
# This generator SYNTHESIZES those two rows for the elementary case (no
# <DD31V_TABLE>/<DD33V_TABLE> in the repo's XML) rather than shipping zero
# rows, matching the real reference object's own ground truth; the
# collective case (both elements present) regenerates DD31S/DD33S directly
# from the XML's own row lists instead, arbitrary count, the same
# "regenerate wholesale from the XML's own count" pattern MSAG's T100/TABL's
# DD03L/DOMA's DD07L all already established. See docs/shlp-support.md.
#
# FUZZY_SIMILARITY is a PACKED DECIMAL field (DD30L nametab: type 'P',
# 2 bytes) -- the first packed field this project has had to write. Decoded
# directly against the real reference object's own bytes: raw `00 8c` =
# nibbles 0,0,8,C (C = positive sign) = digits "008" with 1 implied decimal
# place = 0.8, which is exactly the value every real .shlp.xml sample above
# carries (SAP's own DD30L default). Verified DEC(3,1) this way, not
# guessed -- see _write_shlp_fuzzy_similarity.





make_enho_master_include_source = _make_enho_master_include_source
read_bc_field = _read_bc_field
locate_enho_bc_markers = _locate_enho_bc_markers
rewrite_bc_field_text = _rewrite_bc_field_text
regenerate_enho_data_blob = _regenerate_enho_data_blob
apply_enho_badi_positional_replacements = _apply_enho_badi_positional_replacements
regenerate_enho_badi_data_blob = _regenerate_enho_badi_data_blob
