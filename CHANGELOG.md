# Changelog

All notable changes are listed here. The project follows
[Semantic Versioning](https://semver.org/); before 1.0.0 any release may
change behavior.

## 0.1.0 — experimental prerelease

First public version.

- Generate one transport (cofile and data file) for all objects of an
  abapGit repository, or for a single object, for 46 object types.
- Templates are user-supplied: a template directory with `templates.json`,
  chosen by `--templates` or `ABAPGIT_TRANSPORT_TEMPLATES`, and validated by
  `--check-templates` (files, request, object, required tables).
- Request, SID, package and author are validated before any file is
  written; the SID defaults to the request's first three characters.
- Generation stops unless the request lists exactly the generated objects.
- Every generated data file passes a structural verifier (container,
  checksums, record round trip, request shape, template leftovers).
- Composite GitHub Action with environment-only input handling.
- Repository XML is parsed with defusedxml.
- Dependencies are locked with hashes.
