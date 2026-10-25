# Security policy

## Reporting a vulnerability

Please report vulnerabilities privately through GitHub: open the
repository's **Security** tab and choose **Report a vulnerability**. Do not
open a public issue. Include the version, what an attacker controls (for
example the abapGit repository content or action inputs) and the impact.

Do not attach transport files, templates, logs or anything else from a real
SAP system. A minimal invented reproduction is enough.

We aim to acknowledge reports within a week. This is a volunteer project
without guaranteed response times.

## Supported versions

Only the latest release receives fixes while the project is below 1.0.0.

## What the tool trusts

- **Untrusted:** the content of the abapGit repository (XML is parsed with
  defusedxml; values that become file names or transport keys are
  validated) and the inputs of the GitHub Action (passed to scripts only
  through environment variables).
- **Trusted:** the template directory you supply. Templates are exports of
  your own system; keep them confidential.

The tool reads no credentials and opens no network connection. Generated
transports contain your source code and must be handled like it. Importing
a transport changes the target system; see the [disclaimer](DISCLAIMER.md).
