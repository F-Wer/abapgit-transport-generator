# Disclaimer

## No affiliation with SAP

This project is an independent open-source project. It is **not affiliated
with, sponsored by, endorsed by or supported by SAP SE** or any of its
affiliates. SAP, ABAP, SAP NetWeaver, SAP S/4HANA and other SAP products and
services mentioned here are trademarks or registered trademarks of SAP SE in
Germany and other countries. They are used only to describe what this tool
works with.

The project is likewise independent of the abapGit project; abapGit is
mentioned only because this tool reads its file format.

## Use at your own risk

This tool generates SAP transport files from an abapGit repository. Importing
a transport changes the target system: it can create, overwrite or delete
repository objects, dictionary definitions and table contents, and an import
cannot always be undone.

The software is **experimental** and provided **"as is", without warranty of
any kind**, express or implied, including but not limited to the warranties of
merchantability, fitness for a particular purpose and non-infringement. See
sections 11 and 12 of the [GNU General Public License, version 2](LICENSE).

**To the extent permitted by applicable law, the authors and contributors are
not liable for any damage** arising from the use of this software or of
transports it generates, including damage to SAP systems, data loss or
corruption, downtime, failed or partial imports, lost profits, or claims by
third parties.

## Your responsibility

Before importing any generated transport, you are responsible for:

- using only systems you are authorized to change, under the license terms
  that apply to them;
- importing into a non-production system first and checking the import log,
  activation and behavior;
- having a current backup and a tested way to restore it;
- reviewing what the transport contains;
- following your organization's change, transport and approval processes.

Transport templates are exports from your own systems. You are responsible for
having the right to use them, and for keeping them confidential where
required. This project does not ship any templates.
