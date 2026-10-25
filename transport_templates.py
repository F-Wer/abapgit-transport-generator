"""Template registry for abapGit-to-transport generation.

Templates are real transport exports, so they are never part of the code.
They live in a template directory supplied by the user, described by its
``templates.json`` manifest::

    {
      "PROG": {"cofile": "K900001.DEV", "data": "R900001.DEV",
               "object": "ZDEMO_REPORT", "request": "DEVK900001",
               "description": "Demo report"},
      ...
    }

``cofile`` and ``data`` are paths relative to the manifest. ``object``,
``request`` and the optional ``description``/``descriptions`` are the
exported object's name, its request and its texts, which the generator
renames. The optional ``names`` holds further values the template contains
that a type's regenerator replaces (strings, or lists of strings/null). The directory is chosen, in order, by ``configure_templates()``
(the CLI's ``--templates``), the ``ABAPGIT_TRANSPORT_TEMPLATES``
environment variable, or ``probes/`` next to this module.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator, Mapping
from pathlib import Path

MANIFEST_NAME = "templates.json"
ENV_VAR = "ABAPGIT_TRANSPORT_TEMPLATES"
_DEFAULT_DIR = Path(__file__).parent / "probes"
_REQUIRED = ("cofile", "data", "object", "request")


class TemplateError(ValueError):
    """The template directory or its manifest cannot be used."""


def template_name(key: str, field: str):
    """A value from template `key`'s ``names``; TemplateError if absent."""
    names = TEMPLATES[key]["names"]
    if field not in names:
        raise TemplateError(f"template {key!r} lacks names.{field} in its "
                            f"{MANIFEST_NAME}")
    return names[field]


def template_dir() -> Path:
    """The directory the registry reads, without loading it."""
    return TEMPLATES.directory


def configure_templates(directory: "str | Path | None") -> None:
    """Use `directory` for every later template lookup (None: default)."""
    TEMPLATES.use(Path(directory) if directory else None)


def load_manifest(directory: Path) -> dict:
    """Read and validate `directory`'s manifest; raise TemplateError."""
    manifest = directory / MANIFEST_NAME
    if not manifest.is_file():
        raise TemplateError(
            f"no template manifest {manifest}. Supply a template directory "
            f"with --templates DIR or {ENV_VAR}; see docs/templates.md")
    try:
        raw = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TemplateError(f"{manifest}: unreadable manifest: {exc}") from exc
    if not isinstance(raw, dict):
        raise TemplateError(f"{manifest}: top level must be an object")

    root = directory.resolve()
    entries = {}
    for key, item in raw.items():
        where = f"{manifest}: template {key!r}"
        if not isinstance(item, dict):
            raise TemplateError(f"{where} must be an object")
        missing = [name for name in _REQUIRED if not item.get(name)]
        if missing:
            raise TemplateError(f"{where} lacks {', '.join(missing)}")
        descriptions = item.get("descriptions", [])
        if not (isinstance(descriptions, list)
                and all(isinstance(d, str) for d in descriptions)):
            raise TemplateError(f"{where}: descriptions must be a list of strings")
        names = item.get("names", {})
        if not (isinstance(names, dict) and all(
                isinstance(v, str) or (isinstance(v, list) and all(
                    x is None or isinstance(x, str) for x in v))
                for v in names.values())):
            raise TemplateError(f"{where}: names must map to strings or lists of strings")
        entry = {
            "object": str(item["object"]),
            "request": str(item["request"]),
            "description": str(item.get("description", "")),
            "descriptions": list(descriptions),
            "names": dict(names),
        }
        for name in ("cofile", "data"):
            path = (root / str(item[name])).resolve()
            if not path.is_relative_to(root):
                raise TemplateError(f"{where}: {name} leaves the template directory")
            if not path.is_file():
                raise TemplateError(f"{where}: {name} file {path} not found")
            entry[name] = path
        entries[key] = entry
    return entries


class _TemplateRegistry(Mapping):
    """Mapping of template key -> entry, loaded on first use."""

    def __init__(self) -> None:
        self._override: "Path | None" = None
        self._entries: "dict | None" = None

    @property
    def directory(self) -> Path:
        if self._override is not None:
            return self._override
        env = os.environ.get(ENV_VAR)
        return Path(env) if env else _DEFAULT_DIR

    def use(self, directory: "Path | None") -> None:
        self._override = directory
        self._entries = None

    def _load(self) -> dict:
        if self._entries is None:
            self._entries = load_manifest(self.directory)
        return self._entries

    def __getitem__(self, key: str) -> dict:
        return self._load()[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._load())

    def __len__(self) -> int:
        return len(self._load())


TEMPLATES = _TemplateRegistry()


ICF_NODES_NAME = "icf_nodes.json"
_ICF_GUID_CHARS = frozenset("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ")


def icf_nodes(directory: "Path | None" = None) -> dict:
    """ICF node URL -> node GUID, from the optional icf_nodes.json.

    A generated ICF service needs its parent node's GUID (ICFNODGUID),
    which belongs to the target system, so the user supplies it next to
    the templates: {"/sap/bc": "<25-character GUID>", ...}. Missing file:
    no nodes. Raise TemplateError for a malformed file.
    """
    path = (directory or template_dir()) / ICF_NODES_NAME
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TemplateError(f"{path}: unreadable: {exc}") from exc
    if not isinstance(raw, dict):
        raise TemplateError(f"{path}: top level must be an object")
    nodes = {}
    for url, guid in raw.items():
        guid = str(guid).upper()
        if len(guid) != 25 or not set(guid) <= _ICF_GUID_CHARS:
            raise TemplateError(f"{path}: node {url!r} needs a 25-character GUID")
        nodes[str(url).strip().rstrip("/").lower()] = guid
    return nodes


def check_templates(directory: "Path | None" = None) -> list[str]:
    """Problems with a template directory; an empty list means usable.

    Beyond the manifest checks, every data file must be a readable
    transport container whose request record names the manifest request.
    """
    from sap_transport_records import iter_records, u16
    from sap_transport_writer import decompress_container, parse_container

    directory = directory or template_dir()
    try:
        entries = load_manifest(directory)
    except TemplateError as exc:
        return [str(exc)]
    problems = []
    try:
        icf_nodes(directory)
    except TemplateError as exc:
        problems.append(str(exc))
    for key, entry in entries.items():
        try:
            records = iter_records(decompress_container(
                parse_container(entry["data"].read_bytes())))
        except (OSError, ValueError) as exc:
            problems.append(f"{key}: data file {entry['data'].name}: {exc}")
            continue
        requests = [u16(r.payload).split()[0] for r in records
                    if r.rtype == "F" and u16(r.payload).split()]
        if entry["request"] not in requests:
            problems.append(f"{key}: data file belongs to {requests or 'no request'}, "
                            f"manifest says {entry['request']}")
        # The generator renames the manifest's object; if the export holds a
        # different one, every transport would deliver the template's object.
        objects = [(u16(r.payload)[30:34], u16(r.payload)[34:].rstrip())
                   for r in records if r.rtype == "C"]
        expected = (key.split("_")[0], entry["object"].rstrip())
        if objects != [expected]:
            problems.append(f"{key}: data file transports {objects}, manifest "
                            f"expects one {expected[0]} {expected[1]!r}")
        present = set()
        for i, record in enumerate(records):
            if record.rtype == "H":
                handler = record.payload[:8].decode("latin-1").strip()
                table = record.payload[8:38].decode("latin-1").strip()
                present.add("REPOS" if handler == "ABAPREAD" and table == "REPOS" else table)
        missing = [t for t in TEMPLATE_TABLES.get(key, ()) if t not in present]
        if missing:
            problems.append(f"{key}: template lacks {', '.join(missing)}; capture an "
                            f"object whose export contains them (see docs/templates.md)")
    return problems


# Content tables a template of each type must carry (as blocks; REPOS =
# ABAP source blocks). Each regenerator rewrites these; a template
# without them makes the generator silently ship less. Derived from the
# templates the generator was developed and import-tested against,
# leaving out tables any export carries incidentally (change logs,
# enhancement bookkeeping, documentation, the logical-object definition).
TEMPLATE_TABLES = {
    "ACID": ('AAB_ID_PROP', 'AAB_ID_PROPT'),
    "AMSD": ('AMDP_SCHEMA_DEF', 'AMDP_SCHEMA_DEFT'),
    "APIS": ('ARS_W_API', 'ARS_W_API_SCCSSR', 'ARS_W_API_STATE'),
    "APLO": ('BALOBJ', 'BALOBJT', 'BALSUB', 'BALSUBT'),
    "AQBG": ('AQGDBBG', 'AQGTB'),
    "AQQU": ('AQGDB', 'AQGQCAT', 'AQGTQ'),
    "AQSG": ('AQGDB', 'AQGDBBS', 'AQGSBWMAP', 'AQGSBWPROP', 'AQGSCAT', 'AQGTS'),
    "ASFC": ('AIND_STR1', 'AIND_STR1T', 'AIND_STR3', 'AIND_STR4', 'AIND_STR6', 'AIND_STR7'),
    "AUTH": ('AUTHX',),
    "AVAR": ('AAB_VAR_ID', 'AAB_VAR_PROP', 'AAB_VAR_PROPT'),
    "AVAS": ('CLS_ASSIGNMENT', 'CLS_LINKED_OBJ'),
    "CHAR": ('CLS_ATTRIBUTE', 'CLS_ATTRIBUTET', 'CLS_ATTR_VALUE', 'CLS_ATTR_VALUET'),
    "CLAS": ('METH', 'REPOS', 'SEOCLASS', 'SEOCLASSDF', 'SEOCLASSEX', 'SEOCLASSTX', 'SEOCOMPO', 'SEOCOMPODF', 'SEOCOMPOEX', 'SEOCOMPOTX', 'SEOFRIENDS', 'SEOIMPLREL', 'SEOMAPATT', 'SEOMAPCLS', 'SEOMETAREL', 'SEOREDEF', 'SEOSUBCO', 'SEOSUBCODF', 'SEOSUBCOEX', 'SEOSUBCOTX', 'SEOTYPEPLS'),
    "CUS0": ('CUS_IMGACH', 'CUS_IMGACT'),
    "CUS1": ('CUS_ACTH', 'CUS_ACTOBJ', 'CUS_ACTOBT', 'CUS_ACTT'),
    "CUS2": ('CUS_ATRCOU', 'CUS_ATRH', 'CUS_ATRT'),
    "DEVC": ('TDEVC', 'TDEVCT'),
    "DOMA": ('DD01L', 'DD01T', 'DD07L', 'DD07T'),
    "DTEL": ('DD04L', 'DD04T'),
    "ENQU": ('DD25L', 'DD25T', 'DD26S', 'DD27S'),
    "FUGR": ('ENLFDIR', 'FUGR', 'FUNCT', 'FUPARAREF', 'REPOS', 'RODIR', 'TFDIR', 'TFTIT', 'TLIBG', 'TLIBT'),
    "INTF": ('REPOS', 'SEOCLASS', 'SEOCLASSDF', 'SEOCLASSEX', 'SEOCLASSTX', 'SEOCOMPO', 'SEOCOMPODF', 'SEOCOMPOEX', 'SEOCOMPOTX', 'SEOFRIENDS', 'SEOIMPLREL', 'SEOMAPATT', 'SEOMAPCLS', 'SEOMETAREL', 'SEOREDEF', 'SEOSUBCO', 'SEOSUBCODF', 'SEOSUBCOEX', 'SEOSUBCOTX', 'SEOTYPEPLS'),
    "INTF_NS": ('REPOS', 'SEOCLASS', 'SEOCLASSDF', 'SEOCLASSEX', 'SEOCLASSTX', 'SEOCOMPO', 'SEOCOMPODF', 'SEOCOMPOEX', 'SEOCOMPOTX', 'SEOFRIENDS', 'SEOIMPLREL', 'SEOMAPATT', 'SEOMAPCLS', 'SEOMETAREL', 'SEOREDEF', 'SEOSUBCO', 'SEOSUBCODF', 'SEOSUBCOEX', 'SEOSUBCOTX', 'SEOTYPEPLS'),
    "MSAG": ('T100', 'T100A', 'T100O', 'T100T', 'T100U', 'T100X'),
    "NROB": ('TNROS', 'TNROST'),
    "OTGR": ('CLS_TYGR_ELEMENT', 'CLS_TYGR_PARENT', 'CLS_TYPE_GROUP', 'CLS_TYPE_GROUPT'),
    "PARA": ('TPARA', 'TPARAT'),
    "PERS": ('SPERS_REG', 'SPERS_REGT'),
    "PINF": ('IFOBJLONG', 'IFOBJSHORT', 'INTF', 'INTFTEXT'),
    "PRAG": ('TRPRAGMA', 'TRPRAGMAT'),
    "PROG": ('REPOS',),
    "SCVI": ('SHDGUIXT', 'SHDGXTCODE', 'SHDSVCI', 'SHDSVFVCI', 'SHDSVTXCI'),
    "SFPF": ('FPCONTEXT', 'FPCONTEXTT', 'FPLAYOUT', 'FPLAYOUTT'),
    "SFPI": ('FPINTERFACE', 'FPINTERFACET'),
    "SHLP": ('DD30L', 'DD30T', 'DD31S', 'DD32S', 'DD33S'),
    "SICF": ('ICFDOCU', 'ICFHANDLER', 'ICFSERVICE'),
    "SPLO": ('TSP0P', 'TSP1D', 'TSP1T'),
    "SPPF": ('TSP08',),
    "SUCU": ('TBRG_AUTH', 'TBRG_AUTHT'),
    "SUSC": ('TOBC', 'TOBCT'),
    "SUSO": ('TACTZ', 'TOBJ', 'TOBJT', 'TOBJVOR', 'TOBJVORDAT', 'TOBJVORFLG'),
    "TABL": ('DD02L', 'DD02T', 'DD03L', 'DD09L'),
    "TOBJ": ('OBJH', 'OBJS', 'OBJT', 'TDDAT', 'TVDIR'),
    "TRAN": ('TSTC', 'TSTCC', 'TSTCP', 'TSTCT'),
    "TTYP": ('DD40L', 'DD40T'),
    "TYPE": ('DDTYPET', 'REPOS'),
    "VIEW": ('DD25L', 'DD25T', 'DD26S', 'DD27S', 'DD29L'),
    "XSLT": ('O2XSLTDESC', 'O2XSLTTEXT'),
}


# Import-step counters a cofile header carries, per object type, read off
# real single-object exports: (dictionary objects, objects to generate,
# objects with after-import processing). tp decides from the SUMS which
# import steps to run -- a DDIC object exported with a 0 dictionary counter
# is skipped by every step ("not imported in this step") and never reaches
# the system. Types not listed need the main import only: (0, 0, 0).
_DDIC = (1, 1, 0)
_GENERATED = (0, 1, 0)
_AFTER_IMPORT = (0, 0, 1)
STEP_COUNTERS = {
    **dict.fromkeys(("DOMA", "DTEL", "TABL", "TTYP", "VIEW", "ENQU", "SHLP",
                     "APIS"), _DDIC),
    **dict.fromkeys(("PROG", "CLAS", "INTF", "FUGR"), _GENERATED),
    **dict.fromkeys(("ENHO", "SICF", "XSLT", "SFPF", "ACID", "AQSG", "AVAS",
                     "CHAR", "DEVC"), _AFTER_IMPORT),
}
