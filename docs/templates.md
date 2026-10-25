# Transport templates

The generator never invents a transport from nothing. For each object type
it starts from a **template**: a real transport of one minimal object of
that type, exported from a system you are authorized to use. It renames the
template's object, request and texts, replaces its content with your
repository's, and merges everything into one request.

Templates are exports of a real system, so **this project ships none**. You
capture your own and keep them out of version control (or in a private
repository you control).

## Template directory

A template directory holds the cofile/data-file pairs and a
`templates.json` manifest:

```
my-templates/
  templates.json
  prog/K900001.DEV
  prog/R900001.DEV
  tabl/K900002.DEV
  tabl/R900002.DEV
```

```json
{
  "PROG": {
    "cofile": "prog/K900001.DEV",
    "data": "prog/R900001.DEV",
    "object": "ZDEMO_TEMPLATE_PROG",
    "request": "DEVK900001",
    "description": "Template report"
  },
  "TABL": {
    "cofile": "tabl/K900002.DEV",
    "data": "tabl/R900002.DEV",
    "object": "ZDEMO_TEMPLATE_TABL",
    "request": "DEVK900002"
  }
}
```

| Field | Meaning |
| --- | --- |
| key | Object type (`PROG`, `TABL`, …). A namespaced interface uses the extra key `INTF_NS`. |
| `cofile`, `data` | The exported `K…` and `R…` files, relative to the manifest. They may not point outside the directory. |
| `object` | The template object's name exactly as it appears in the transport. |
| `request` | The request the template was exported with. |
| `description`, `descriptions` | Optional texts of the template object; the generator replaces them with the generated object's description. |

You only need templates for the types your repositories contain. Generating
a type without a template stops with an error naming the missing key.

### ICF services

An ICF service (`SICF`) hangs below a parent node, and the transport must
name that node's GUID, which belongs to the target system. Put the parents
you use into an optional `icf_nodes.json` next to `templates.json`:

```json
{
  "/sap/bc": "<ICFNODGUID of /sap/bc>",
  "/sap/bc/rest": "<ICFNODGUID of /sap/bc/rest>"
}
```

Read each GUID (25 characters) from table `ICFSERVICE`, column `ICFNODGUID`,
of the target system. The key is the parent URL that abapGit writes into
the service's `<URL>`. A service whose parent is missing stops with an error
naming the URL; `--check-templates` validates the file's format.

## Choosing the directory

In order of precedence:

1. `--templates DIR` on the command line (action input `templates`);
2. the `ABAPGIT_TRANSPORT_TEMPLATES` environment variable;
3. the default directory next to the generator, if your installation has one.

## Capturing a template

1. On a development system you are authorized to use, create the smallest
   possible object of the type in a dedicated package. Give it a neutral
   name and description, and use no confidential content: the template's
   rows are rewritten, but they are still the basis of every generated file.
2. Put only that object on a new workbench request and release it.
3. Download the request's cofile (`/usr/sap/trans/cofiles/K…`) and data
   file (`/usr/sap/trans/data/R…`) in binary mode.
4. Add the files and an entry to `templates.json`.
5. Validate the directory:

   ```bash
   python abapgit_to_transport.py --check-templates --templates my-templates
   ```

   The check reads every manifest entry and reports, with exit code 2 and
   one `ERROR:` line per problem, when:

   - a file is missing or lies outside the directory;
   - a data file is not a readable transport container, or belongs to
     another request than the manifest says;
   - the export does not contain exactly one object, of the entry's type,
     named exactly as the manifest's `object` (otherwise every generated
     transport would deliver the template's object);
   - the export lacks a content table the generator rewrites for that
     type (see [Requirements per type](#requirements-per-type)).

6. Generate a transport with the new template and **import it into a
   non-production system** before trusting it. A structurally valid file
   does not prove that SAP accepts it.

## Requirements per type

`--check-templates` enforces the content tables each type needs (the
generator rewrites them; the full list is `TEMPLATE_TABLES` in
`transport_templates.py`). Beyond that, choose template objects like this:

| Type | Template object | Why |
| --- | --- | --- |
| PROG, CLAS, FUGR, TYPE | a minimal object with source code | the source blocks are replaced by the repository's |
| INTF / INTF_NS | one interface without and one with a `/NAMESPACE/` prefix | the two key layouts differ |
| FUGR | a group with one function module; list it as `names.function` | the verifier then checks that its name does not survive |
| TABL | a transparent table with technical settings | technical settings are generated or dropped from this shape |
| TRAN | a report transaction | parameter transactions are generated from it |
| SHLP | an elementary search help | collective helps are generated from it |
| XSLT | a transformation with a long enough source | the repository's source must fit the template's space |
| SICF | a service below a standard node, plus `icf_nodes.json` | see [ICF services](#icf-services) |
| SPPF | any page format | the key is PFORMAT + orientation from the XML |
| SUCU | an authorization group with one object | the key is group + object |
| ENHO | none | not supported |

Text tables should carry the language you generate in; the generator
writes the repository's master language.

## Limits

- The generator's per-type handling was developed against specific
  template shapes. A template that differs (for example a table without
  technical settings, or a service node below an unusual parent) can
  produce a transport that does not import. The per-type requirements are
  still being documented; until then, validate every new template by an
  import.
- Template row layouts (nametabs) are release-specific. Capture templates
  on the release you import into, or at least test the target release.
- Treat template files as confidential exports of your system. Do not
  publish them unless you are entitled to.
