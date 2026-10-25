# Contributing

Thank you for helping. Please read the [disclaimer](DISCLAIMER.md) first:
contributions must never put anyone's SAP system at risk.

## Development setup

```bash
python -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements-dev.txt
.venv/bin/python -m pytest --cov
```

Tests marked `templates` need a template directory and are skipped without
one. Run them with your own templates:

```bash
ABAPGIT_TRANSPORT_TEMPLATES=/path/to/templates .venv/bin/python -m pytest
```

## Rules for changes

- **No real system data.** Never commit transport files, templates, import
  logs, system IDs, user or host names, customer or SAP object names taken
  from a real system. Tests and examples use invented names (`DEV`,
  `ZDEMO_…`, `/ACME/`). CI rejects binary files and known identifiers.
- **Keep output deterministic.** Same input, same bytes. If a change alters
  generated transports on purpose, say why in the pull request.
- **Test first.** Add a test that fails without your change. Generator
  changes need a characterization test; a structurally valid file is not
  proof that SAP accepts it, so describe any import test you ran (release,
  object types, result) without naming the system.
- **Dependencies** are pinned with hashes. Edit `requirements.in` or
  `requirements-dev.in`, then run
  `pip-compile --generate-hashes --strip-extras --output-file requirements.txt requirements.in`
  (and the same for the dev file).

## License of contributions

The project is licensed under GPL-2.0-only. By submitting a contribution you
agree that it is licensed under the same terms.
