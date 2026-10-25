"""Cofile generation helpers for SAP transport files."""

import re


def generate_cofile(tmpl_cofile: bytes, obj_types: list) -> bytes:
    """
    Regenerate the cofile from the template for the given objects.

    The header line carries ten counters behind owner/type/target. Verified
    against real exports (one per object type, plus a 53-object one reading
    `1 15 42 0 0 4 0 0 0 53`): the 2nd counts dictionary objects, the 3rd
    objects to generate, the 6th objects with after-import processing and
    the 10th all objects. tp picks the import steps from them, so they must
    describe the objects actually in the data file, not the template's.
    Everything else (the #/n/ flags line, the tp command lines) is the same
    for any object list.
    """
    lines = tmpl_cofile.decode("latin-1").split("\n")
    parts = re.split(r"(\s+)", lines[0]) if lines else []
    # Non-space tokens sit at even indexes: owner(0) type(2) target(4), then
    # the ten counters at 6..24.
    if len(parts) < 25 or not all(parts[i].isdigit() for i in range(6, 26, 2)):
        raise ValueError(f"unexpected cofile header layout: "
                         f"{lines[0] if lines else ''!r}")

    def set_counter(idx: int, value: int) -> None:
        token = str(value)
        if len(token) > 4:
            raise ValueError(f"counter {value} too large for cofile header")
        delta = len(token) - len(parts[idx])
        parts[idx] = token
        # keep the fixed-width field right-aligned
        if delta > 0:
            parts[idx - 1] = parts[idx - 1][:-delta]
        elif delta < 0:
            parts[idx - 1] += " " * -delta

    steps = [STEP_COUNTERS.get(t, (0, 0, 0)) for t in obj_types]
    set_counter(8, sum(s[0] for s in steps))
    set_counter(10, sum(s[1] for s in steps))
    set_counter(16, sum(s[2] for s in steps))
    set_counter(24, len(obj_types))
    lines[0] = "".join(parts)
    return "\n".join(lines).encode("latin-1")
