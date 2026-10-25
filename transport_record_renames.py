"""Generic transport record and key rename helpers."""

from dataclasses import dataclass, field
from typing import Optional

from sap_transport_records import Record, u16


@dataclass
class RenameRule:
    old_name: str
    new_name: str
    old_request: str
    new_request: str
    old_task: str = ""
    new_task: str = ""
    old_descs: list = field(default_factory=list)
    new_desc: str = ""
    # Function-module renames (FUGR): list of (template_fm, repo_fm).
    # Applied AFTER the object/group rename, everywhere the FM name appears
    # outside the injected sources (TFTIT/FUNCT/TFDIR/ENLFDIR/FUPARAREF/
    # RODIR rows + keys, DOCUT% keys). Constraint: a template FM name must
    # not be a substring of the template GROUP name (the group rename runs
    # first and would corrupt it) -- holds for the bundled template.
    fm_pairs: list = field(default_factory=list)
    # The repo's master language (one character); "" keeps the template's.
    language: str = ""



def _make_description(obj_name: str) -> str:
    """Generate a human-readable description from an object name."""
    return obj_name.replace("_", " ").strip()



def _replace_bytes(payload: bytes, old: str, new: str) -> bytes:
    """Replace all occurrences of old->new in both UTF-16LE and Latin-1 encodings
    (and their case variants, plus space-for-underscore variants used in
    descriptions)."""
    variants = [
        ("utf-16-le", old, new),
        ("latin-1", old, new),
    ]
    for enc, o, n in variants:
        o_enc = o.encode(enc)
        n_enc = n.encode(enc)
        payload = payload.replace(o_enc, n_enc)
        # upper case
        o_up = o.upper().encode(enc)
        if o_up != o_enc:
            payload = payload.replace(o_up, n.upper().encode(enc))
        # lower case
        o_lo = o.lower().encode(enc)
        if o_lo != o_enc:
            payload = payload.replace(o_lo, n.lower().encode(enc))
        # Space-for-underscore variants (common in descriptions like E07T)
        o_space = o.replace("_", " ")
        n_space = n.replace("_", " ")
        o_space_enc = o_space.encode(enc)
        n_space_enc = n_space.encode(enc)
        if o_space_enc != o_enc:
            payload = payload.replace(o_space_enc, n_space_enc)
        # Space-separated, lower case
        o_space_lo = o_space.lower().encode(enc)
        if o_space_lo != o_space_enc and o_space_lo != o_lo:
            payload = payload.replace(o_space_lo, n_space.lower().encode(enc))
        # Space-separated, upper case
        o_space_up = o_space.upper().encode(enc)
        if o_space_up != o_space_enc and o_space_up != o_up:
            payload = payload.replace(o_space_up, n_space.upper().encode(enc))
    return payload


def _apply_rename_to_key(key: str, rule: RenameRule) -> str:
    """Apply a rename rule to a REPOS key string to get the new key.
    '=' padding is re-normalized afterwards so the name field stays exactly
    30 chars -- the include suffix must not shift when the name grows."""
    # Replace old name with new name
    result = key.replace(rule.old_name, rule.new_name)
    result = result.replace(rule.old_name.upper(), rule.new_name.upper())
    result = result.replace(rule.old_name.lower(), rule.new_name.lower())
    # Also replace the non-namespaced variant
    if "/" in rule.old_name:
        old_base = rule.old_name.rsplit("/", 1)[1]
        if "/" in rule.new_name:
            new_base = rule.new_name.rsplit("/", 1)[1]
        else:
            new_base = rule.new_name
        result = result.replace(old_base, new_base)
        result = result.replace(old_base.upper(), new_base.upper())
        result = result.replace(old_base.lower(), new_base.lower())
    # Re-normalize '=' padding: NAME '='*n SUFFIX -> NAME.ljust(30) + SUFFIX
    if "=" in result:
        name, _, suffix = result.partition("=")
        suffix = suffix.lstrip("=")
        if name and suffix:
            result = name.ljust(30, "=") + suffix
    return result



# Character-like ABAP types are stored as UTF-16LE; the rest are binary.
_CHAR_TYPES = frozenset("CNDTLGY")


def _replace_in_row(rec: Record, rule: RenameRule, fields: list) -> Record:
    """
    Rename inside a fixed-width data row **field by field**.

    A plain byte replacement shifts every field after the name when the new
    name is longer, which silently corrupts the row: in SEOCLASSTX the LANGU
    key field went blank and the description absorbed the 'D', so R3trans
    deleted the good row and then failed to insert ours ("duplicate key error
    during insert into table SEOCLASSTX"). Each field must absorb its own
    length change inside its own boundaries.
    """
    payload = bytearray(rec.payload)
    pairs = [(rule.old_name, rule.new_name),
             (rule.old_request, rule.new_request)]
    if rule.old_task:
        pairs.append((rule.old_task, rule.new_task))
    for old_desc in rule.old_descs:
        if old_desc:
            pairs.append((old_desc, rule.new_desc))
    for old_fm, new_fm in rule.fm_pairs:
        if old_fm:
            pairs.append((old_fm, new_fm))

    for _fname, off, flen, ftype in fields:
        if ftype not in _CHAR_TYPES or off + flen > len(payload):
            continue
        try:
            text = payload[off:off + flen].decode("utf-16-le")
        except UnicodeDecodeError:
            continue
        new_text = text
        for old, new in pairs:
            if not old or old not in new_text:
                continue
            new_text = new_text.replace(old, new)
        if new_text == text:
            continue
        encoded = new_text.encode("utf-16-le")
        if len(encoded) > flen:
            # too long for the field: keep what fits (SAP truncates as well)
            encoded = encoded[:flen]
        payload[off:off + flen] = encoded.ljust(flen, b"\x00")[:flen]
        # pad the remainder with UTF-16LE spaces, not NULs
        tail = off + len(encoded)
        while tail + 1 < off + flen:
            payload[tail:tail + 2] = b"\x20\x00"
            tail += 2
    return Record(offset=rec.offset, rtype=rec.rtype,
                  payload=bytes(payload), fragments=rec.fragments)


def _rename_key_preserving_width(key: str, rule: RenameRule) -> Optional[str]:
    """
    Rename the object name / request inside an ATAB or DLIB H-record key while
    keeping the width of the name field: the trailing spaces that pad the name
    up to its DDIC field width absorb the length change.

    R3trans reads these keys as fixed-width field patterns, so a longer name
    must eat its padding. Getting this wrong shifts the `*` into the NEXT
    field, the delete-by-pattern matches nothing ("0 d" in the import log) and
    the following insert dies with a duplicate key error.
    Verified against a real export: CLSNAME is CHAR(30), so the key reads
    "/NAMESPACE/IF_DEMO *" -- name.ljust(30) + "*".
    """
    result = key
    changed = False
    for old, new in ((rule.old_name, rule.new_name),
                     (rule.old_request, rule.new_request)):
        if not old or old not in result:
            continue
        idx = result.index(old)
        end = idx + len(old)
        pad_end = end
        while pad_end < len(result) and result[pad_end] == " ":
            pad_end += 1
        width = pad_end - idx          # name + its padding = field width
        if len(new) > width:
            width = len(new) + 1       # cannot fit: keep one separator space
        result = result[:idx] + new.ljust(width) + result[pad_end:]
        changed = True
    return result if changed else None


def _rename_fm_in_key(key: str, fm_pairs: list) -> Optional[str]:
    """
    Rename the FM name inside an H key pattern, preserving the field shape:

    - padded FM fields keep their width (FUNCT sweep `&<FM><30><*>`,
      DOCUT% `FU<FM><30>%`): the new FM is ljust'ed to the same width so the
      trailing `*`/`%` wildcard never shifts into the next field;
    - unpadded patterns stay unpadded (TFTIT sweep `&<FM>`, RODIR
      `FUNC<FM>`, TFDIR/ENLFDIR/FUPARAREF keys `<FM>`), mirroring how SAP
      itself emits those keys.

    FM pairs are applied longest-name-first and replaced spans are never
    revisited, so a short FM name cannot clobber a longer one's key.
    """
    result = key
    replaced = []
    for old, new in sorted(fm_pairs, key=lambda p: len(p[0]), reverse=True):
        if not old or old not in result:
            continue
        idx = result.index(old)
        if any(idx < r_end and idx + len(old) > r_start
               for r_start, r_end in replaced):
            continue
        end = idx + len(old)
        pad_end = end
        while pad_end < len(result) and result[pad_end] == " ":
            pad_end += 1
        width = pad_end - idx
        if width > len(old):
            result = result[:idx] + new.ljust(width) + result[pad_end:]
            replaced.append((idx, idx + width))
        else:
            result = result[:idx] + new + result[end:]
            replaced.append((idx, idx + len(new)))
    return result if replaced else None


# 'A' record (object directory attributes) -- fixed CHARACTER offsets, no
# nametab. Decoded from a real export:
#   [0:4] PGMID  [4:8] OBJECT  [8:58] OBJ_NAME
#   [58:68] SRCSYSTEM  [68:80] AUTHOR  [81:111] DEVCLASS (package)
A_DEVCLASS_OFF = 81
A_DEVCLASS_LEN = 30


def _rename_a_record(rec: Record, rule: RenameRule,
                     package: str = "", author: str = "") -> Record:
    """
    Rename an 'A' record and optionally set the package and author.

    The object name sits in a fixed-width field, so a plain replacement
    shifts SRCSYSTEM / AUTHOR / DEVCLASS out of position -- that is how the
    imported interface ended up in TADIR with DEVCLASS='<user tail> <template package>'
    and AUTHOR='<SID>       X'. The package must be set explicitly as well:
    otherwise the template's own package ships and the import MOVES the
    object into it.
    """
    text = u16(rec.payload)
    renamed = _rename_key_preserving_width(text, rule)
    if renamed is not None:
        text = renamed
    if package:
        text = (text[:A_DEVCLASS_OFF]
                + package.ljust(A_DEVCLASS_LEN)[:A_DEVCLASS_LEN]
                + text[A_DEVCLASS_OFF + A_DEVCLASS_LEN:])
    if author:
        text = (text[:A_AUTHOR_OFF]
                + author.upper().ljust(A_AUTHOR_LEN)[:A_AUTHOR_LEN]
                + text[A_AUTHOR_OFF + A_AUTHOR_LEN:])
    # Original system: the system the request claims to come from, not the
    # template's -- a native probe of an SAP-delivered object would otherwise
    # register the generated object in TADIR as an SAP original.
    sid = rule.new_request[:3]
    text = text[:A_SRCSYSTEM_OFF] + sid.ljust(10) + text[A_SRCSYSTEM_OFF + 10:]
    if rule.language:
        text = (text[:A_MASTERLANG_OFF] + rule.language[:1]
                + text[A_MASTERLANG_OFF + 1:])

    encoded = text.encode("utf-16-le")
    size = len(rec.payload)
    if len(encoded) > size:
        encoded = encoded[:size]
    else:
        encoded += b"\x20\x00" * ((size - len(encoded)) // 2)
    return Record(offset=rec.offset, rtype=rec.rtype,
                  payload=encoded, fragments=rec.fragments)


def _rename_h_key(orig_h: Record, renamed: Record,
                  rule: RenameRule) -> Record:
    """Rewrite a renamed H record's key region with width-preserving padding
    computed from the ORIGINAL template key.

    Applies the group rename (object name / request, width-preserving) and
    then the FM rename (FUGR: TFTIT/FUNCT/TFDIR/ENLFDIR/FUPARAREF/RODIR/
    DOCUT% keys pack the FM name)."""
    orig_key = orig_h.payload[48:].decode("latin-1").rstrip()
    new_key = _rename_key_preserving_width(orig_key, rule)
    if new_key is None:
        new_key = orig_key
    fm_key = _rename_fm_in_key(new_key, rule.fm_pairs)
    if fm_key is not None:
        new_key = fm_key
    if new_key == orig_key:
        return renamed
    payload = bytearray(renamed.payload)
    area = len(payload) - 48
    encoded = new_key.encode("latin-1")
    if len(encoded) > area:
        raise ValueError(f"key too long for H record: {new_key!r}")
    payload[48:] = encoded.ljust(area, b" ")
    return Record(offset=renamed.offset, rtype=renamed.rtype,
                  payload=bytes(payload), fragments=renamed.fragments)


def _normalize_repos_key(h_rec: Record) -> Record:
    """
    Rewrite an ABAPREAD H record's key region so the object name field is
    exactly 30 chars: growth/shrinkage from a rename is absorbed by the '='
    padding instead of shifting the include suffix.
    """
    payload = bytearray(h_rec.payload)
    key_area = payload[48:]
    # rstrip NULs too: _replace_in_record pads a SHRUNKEN latin-1 payload
    # with UTF-16LE spaces (b"\x20\x00"), leaving NUL bytes behind the key.
    # A non-namespaced rename (19-char template name -> 15-char Z-name)
    # hit exactly that; the renormalization below rebuilds the key from the
    # name/suffix pair, so the trailing garbage must be stripped first.
    key = key_area.decode("latin-1").rstrip(" \x00")
    if "=" in key:
        # '='-padded keys (INTF/CLAS): NAME '='*n SUFFIX -> NAME.ljust(30)
        name, _, suffix = key.partition("=")
        suffix = suffix.lstrip("=")
        if not name or not suffix:
            return h_rec
        new_key = name.ljust(30, "=") + suffix
    else:
        # unpadded keys (PROG main/include names, FUGR SAPL<grp>/L<grp>*):
        # the key IS the include name -- just re-pad the area with spaces.
        new_key = key
    encoded = new_key.encode("latin-1")
    if len(encoded) > len(key_area):
        raise ValueError(f"key too long for H record: {new_key!r}")
    payload[48:48 + len(encoded)] = encoded
    payload[48 + len(encoded):] = b" " * (len(payload) - 48 - len(encoded))
    return Record(offset=h_rec.offset, rtype=h_rec.rtype,
                  payload=bytes(payload), fragments=h_rec.fragments)


def _replace_in_record(rec: Record, rule: RenameRule,
                        preserve_length: bool = True) -> Record:
    """Replace old name/request with new in a record payload.

    If preserve_length is True (default), the payload length is kept exactly
    the same by trimming or padding with UTF-16LE spaces. This is essential
    for fixed-width table data rows (E070, E071, etc.). REPOS source lines
    pass preserve_length=False since they get completely new content.
    """
    original_len = len(rec.payload)
    new_payload = rec.payload

    # Important: replace the REQUEST NUMBER first with a same-length version
    # to avoid cascading length changes. If the new request is longer/shorter,
    # we adjust with padding later.
    new_payload = _replace_bytes(new_payload, rule.old_request, rule.new_request)
    if rule.old_task:
        new_payload = _replace_bytes(new_payload, rule.old_task, rule.new_task)

    # Replace object name
    new_payload = _replace_bytes(new_payload, rule.old_name, rule.new_name)

    # Replace description texts if present
    for old_desc in rule.old_descs:
        if old_desc:
            new_payload = _replace_bytes(new_payload, old_desc, rule.new_desc)

    # Also replace just the base name if namespaced
    if "/" in rule.old_name:
        old_base = rule.old_name.rsplit("/", 1)[1]
        if "/" in rule.new_name:
            new_base = rule.new_name.rsplit("/", 1)[1]
        else:
            new_base = rule.new_name
        if old_base != rule.old_name:
            new_payload = _replace_bytes(new_payload, old_base, new_base)

    # Replace the FM name(s) -- after the group name, so a template FM name
    # that is a substring of the template group name is not corrupted (the
    # group rename consumed it already). Non-recursive str.replace, so a new
    # FM name that itself contains an old name is safe.
    for old_fm, new_fm in rule.fm_pairs:
        if old_fm:
            new_payload = _replace_bytes(new_payload, old_fm, new_fm)

    # Preserve original length for fixed-width records
    if preserve_length and len(new_payload) != original_len:
        if len(new_payload) > original_len:
            excess = len(new_payload) - original_len
            new_payload = new_payload[:original_len]
        else:
            # Pad with UTF-16LE spaces (U+0020 = b'\x20\x00' -- NOT b'\x00\x20',
            # which is U+2000 EN QUAD and breaks the syntax check)
            shortage = original_len - len(new_payload)
            new_payload += b"\x20\x00" * (shortage // 2)
            if shortage % 2:
                new_payload += b"\x20"

    return Record(offset=rec.offset, rtype=rec.rtype,
                  payload=new_payload, fragments=rec.fragments)



make_description = _make_description
replace_bytes = _replace_bytes
apply_rename_to_key = _apply_rename_to_key
replace_in_row = _replace_in_row
rename_key_preserving_width = _rename_key_preserving_width
rename_fm_in_key = _rename_fm_in_key
rename_a_record = _rename_a_record
rename_h_key = _rename_h_key
normalize_repos_key = _normalize_repos_key
replace_in_record = _replace_in_record
