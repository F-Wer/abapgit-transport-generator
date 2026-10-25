# Supported object types

Status of version 0.1.0. "Import-tested" means a generated transport of the
type was imported into one test system (SAP_BASIS 8.16), the import and
activation logs were checked, and the created rows were read back. No other
release is tested yet, and a successful import does not prove that every
optional field of a type is handled. Test your own objects on a
non-production system.

| Type | Status |
| --- | --- |
| ACID | generated; import-tested |
| AMSD | generated; import-tested |
| APIS | generated; import-tested |
| APLO | generated; import-tested |
| AQBG | generated; import-tested |
| AQQU | generated; import-tested |
| AQSG | generated; import-tested |
| ASFC | generated; import-tested |
| AUTH | generated; import-tested |
| AVAR | generated; import-tested |
| AVAS | generated; import-tested |
| CHAR | generated; import-tested |
| CLAS | generated; import-tested |
| CUS0 | generated; import-tested |
| CUS1 | generated; import-tested |
| CUS2 | generated; import-tested |
| DEVC | generated; import-tested |
| DOMA | generated; import-tested |
| DTEL | generated; import-tested |
| ENQU | generated; import-tested |
| FUGR | generated; import-tested |
| INTF | generated; import-tested |
| MSAG | generated; import-tested |
| NROB | generated; import-tested |
| OTGR | generated; import-tested |
| PARA | generated; import-tested |
| PERS | generated; import-tested |
| PRAG | generated; import-tested |
| PROG | generated; import-tested |
| SCVI | generated; import-tested |
| SFPF | generated; import-tested |
| SFPI | generated; import-tested |
| SHLP | generated; import-tested |
| SICF | generated; import-tested |
| SPLO | generated; import-tested |
| SPPF | generated; import-tested |
| SUCU | generated; import-tested |
| SUSC | generated; import-tested |
| SUSO | generated; import-tested |
| TABL | generated; import-tested |
| TOBJ | generated; import-tested |
| TRAN | generated; import-tested |
| TTYP | generated; import-tested |
| TYPE | generated; import-tested |
| VIEW | generated; import-tested |
| XSLT | generated; import-tested |

## Not supported

The generator lists files of these types as unsupported and never ships
them: ENHO (enhancement implementations), PINF (package interfaces), COTA,
SUSH, SRFC, G4BS and CHDO, and every abapGit type not listed above.

## Known limits

- Dynpros and GUI status are not generated (PROG, FUGR).
- Tables: foreign keys, secondary indexes and search-help assignments are
  not shipped.
- Classes: attributes, types, events and method parameters are not
  modelled in the class-builder tables; the source code is authoritative.
- Texts are transported in the master language only.
