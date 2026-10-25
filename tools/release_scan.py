#!/usr/bin/env python3
"""Reject internal identifiers and binaries from a public release candidate.

    python tools/release_scan.py --banned FILE [--templates DIR] PATH...
    python tools/release_scan.py --banned FILE --manifest LIST

Every file under PATH (or listed in LIST, one path per line relative to the
working directory, `#` comments, `!path` excludes a file or directory) is
checked:

- its path and its text, case-insensitively, against every pattern in
  FILE (one Python regular expression per line, `#` comments) and every
  object name, request and description in DIR's templates.json;
- binary files (a NUL byte, or not valid UTF-8) are always rejected: a scan
  cannot prove a binary free of identifiers.

This file contains no identifiers itself: the banned list is supplied from
outside the public tree (a private file or a CI secret). Exit code 1 lists
every finding as `path:line: pattern`; 0 means none.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_SKIP_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", "node_modules"}
_MIN_TOKEN = 4


def load_patterns(banned_file: Path, template_dir: "Path | None") -> list[re.Pattern]:
    """Compile the banned list plus the template manifest's identifiers."""
    if not banned_file.is_file():
        raise SystemExit(f"ERROR: banned-pattern file {banned_file} not found")
    sources = []
    for line in banned_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            sources.append(line)
    manifest = template_dir / "templates.json" if template_dir else None
    if manifest and manifest.is_file():
        for entry in json.loads(manifest.read_text(encoding="utf-8")).values():
            # A compound object name's first part is the identity; the rest
            # names an object type or parent (e.g. "ENHS"), which stays
            # usable. Descriptions match only as whole phrases.
            names = [v for v in entry.get("names", {}).values() if isinstance(v, str)]
            for text in (str(entry.get("object", "")).split()[:1],
                         [entry.get("request", "")], names):
                sources += [re.escape(str(token)) for token in text
                            if len(str(token)) >= _MIN_TOKEN]
            for text in (entry.get("description", ""), *entry.get("descriptions", [])):
                if len(str(text).strip()) >= _MIN_TOKEN:
                    sources.append(re.escape(str(text).strip()))
    if not sources:
        raise SystemExit("ERROR: no banned patterns supplied")
    return [re.compile(source, re.IGNORECASE) for source in dict.fromkeys(sources)]


def candidate_files(paths: list[Path]) -> list[Path]:
    files = []
    for path in paths:
        if path.is_dir():
            files += [p for p in sorted(path.rglob("*"))
                      if p.is_file() and not _SKIP_DIRS & set(p.parts)]
        else:
            files.append(path)  # a missing path is reported by scan()
    return files


def scan(files: list[Path], patterns: list[re.Pattern]) -> list[str]:
    findings = []
    for path in files:
        name = path.as_posix()
        if not path.is_file():
            findings.append(f"{name}: listed but missing")
            continue
        findings += [f"{name}: file name matches {p.pattern}"
                     for p in patterns if p.search(name)]
        raw = path.read_bytes()
        try:
            if b"\x00" in raw[:8192]:
                raise UnicodeDecodeError("utf-8", raw, 0, 1, "NUL byte")
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            findings.append(f"{name}: binary file not allowed in a public release")
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            findings += [f"{name}:{number}: {p.pattern}"
                         for p in patterns if p.search(line)]
    return findings


def read_manifest(manifest: Path) -> tuple[list[Path], list[Path]]:
    """Included and excluded (`!path`) paths of a manifest."""
    paths, excluded = [], []
    for line in manifest.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line.startswith("!"):
            excluded.append(Path(line[1:].strip()))
        elif line:
            paths.append(Path(line))
    return paths, excluded


def without(files: list[Path], excluded: list[Path]) -> list[Path]:
    """Drop every file that is, or lies below, an excluded path."""
    return [f for f in files
            if not any(f == e or e in f.parents for e in excluded)]


def main(argv: "list[str] | None" = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("paths", nargs="*", type=Path)
    ap.add_argument("--banned", type=Path, required=True,
                    help="file of banned regular expressions (kept private)")
    ap.add_argument("--templates", type=Path, default=None,
                    help="template directory whose identifiers are banned too")
    ap.add_argument("--manifest", type=Path, default=None,
                    help="file listing the public candidate paths")
    args = ap.parse_args(argv)

    included, excluded = read_manifest(args.manifest) if args.manifest else ([], [])
    paths = list(args.paths) + included
    if not paths:
        ap.error("give PATH arguments or --manifest")

    files = without(candidate_files(paths), excluded)
    findings = scan(files, load_patterns(args.banned, args.templates))
    for finding in findings:
        print(finding)
    print(f"{len(findings)} finding(s)", file=sys.stderr)
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
