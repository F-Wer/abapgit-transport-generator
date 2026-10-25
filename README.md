# abapGit Transport Generator

Generate SAP transport files — the cofile `K<number>.<SID>` and the data file
`R<number>.<SID>` — from an [abapGit](https://abapgit.org/) repository, so a
CI pipeline can deliver ABAP code through STMS without exporting anything
from a development system.

> **Experimental (0.1.0).** Importing a transport changes the target system.
> Read the [disclaimer](DISCLAIMER.md) and import into a non-production
> system first.

## How it works

For each object type the generator starts from a **template**: a transport
of one minimal object of that type, exported from a system you are
authorized to use. It renames the template's object, request and texts,
replaces its content with your repository's source and XML, and merges
every object into one request. The result is checked structurally before
it is written.

This project ships **no templates**. You capture your own once; see
[docs/templates.md](docs/templates.md).

## Quick start

```bash
python -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements.txt

# validate your template directory
python abapgit_to_transport.py --check-templates --templates /path/to/templates

# generate one transport with all objects of an abapGit repository
python abapgit_to_transport.py /path/to/abapgit-repo \
  --templates /path/to/templates \
  --request DEVK900001 --package ZDEMO_PACKAGE --author DEVELOPER
```

| Option | Meaning |
| --- | --- |
| `--request` | Request number `<SID><letter><6 digits>`; required |
| `--sid` | Defaults to the request's first three characters |
| `--package` | Target package; without it objects move into the template's package |
| `--author` | User written into the generated metadata |
| `--templates` | Template directory (or `ABAPGIT_TRANSPORT_TEMPLATES`) |
| `--object` | Generate a single object instead of all |
| `--list` | List the detected objects and stop |

Invalid values stop with exit code 2 before any file is written.

## GitHub Action

```yaml
- uses: actions/checkout@v4
- uses: actions/checkout@v4          # your private template repository
  with:
    repository: your-org/sap-transport-templates
    path: templates
    token: ${{ secrets.TEMPLATES_TOKEN }}
- uses: F-Wer/abapgit-transport-generator@v0.1.0
  with:
    request: DEVK900001
    package: ZDEMO_PACKAGE
    templates: templates
```

Inputs reach the action's scripts only through environment variables. The
generated files are verified before the action reports success.

## Importing

1. Copy `K…` to `/usr/sap/trans/cofiles/` and `R…` to `/usr/sap/trans/data/`
   in binary mode.
2. STMS → Extras → Other Requests → Add → your request, then import it.
3. If the objects already exist, import with *Overwrite Originals*.

## Supported object types

46 abapGit object types are generated, among them PROG, CLAS, INTF, FUGR,
DDIC types (DOMA, DTEL, TABL, TTYP, VIEW, ENQU, SHLP), MSAG, TRAN, SICF,
XSLT, Adobe forms (SFPF/SFPI), packages (DEVC) and many table-based types.
Import-tested on one test system (SAP_BASIS 8.16) only; no other release is
tested yet. ENHO and package interfaces are not supported. Per-type status:
[docs/support.md](docs/support.md).

Known limits: dynpros and GUI status are not generated; table foreign keys,
secondary indexes and search-help assignments are not shipped; texts are
transported in the master language only.

## Security and data

The tool reads no credentials and talks to no SAP system. Generated files
contain your source code and your templates' metadata: treat them like the
repository they come from. Report vulnerabilities as described in
[SECURITY.md](SECURITY.md).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). This project follows the
[Contributor Covenant](CODE_OF_CONDUCT.md).

## License

GPL-2.0-only — see [LICENSE](LICENSE). Not affiliated with SAP SE or the
abapGit project; see the [disclaimer](DISCLAIMER.md).
