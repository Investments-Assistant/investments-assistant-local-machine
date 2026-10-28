# Dependency security — 28 October 2026

## Certificate-chain remediation candidate

After publication of the research timing fix, a fresh repository alert read found
two critical records for [GHSA-6q48-6c7w-9gw2](https://github.com/advisories/GHSA-6q48-6c7w-9gw2):
runtime certifi2026.2.25 and bootstrap certifi2026.7.22. The candidate pins both to
[2026.10.23](https://pypi.org/project/certifi/2026.10.23/). Their wheel hashes were
checked against independent official release metadata before QA extraction.
All149 other runtime lock records remain byte-identical.

The [Python incident guidance](https://discuss.python.org/t/information-for-python-users-regarding-emudhra-emsign-ca-certificate-security-incident/109576)
also requires addressing pip's vendored certificates. The hashed bootstrap adds
pip26.2.2. The container stays on Python3.12/Bookworm, with the official immutable
Python3.12.16 manifest and signed28October Debian snapshots. It pins
ca-certificates20250419~deb12u2, the Bookworm fix in
[DLA4845-1](https://lists.debian.org/debian-lts-announce/2026/10/msg00039.html).
No host Python, trust store, OS setting or existing application environment is
changed by these checkout and isolated-QA operations.

Targeted Poetry resolution and lock checks pass. The final strict wheel-only
bootstrap dry-run resolves47 packages without installation. Offline QA checks
find the compromised G3 subject/fingerprint in the old bundle and absent from the
new certifi and pip bundles, with hostname checking and CERT_REQUIRED preserved.
The new container build, actual system trust store and exact candidate CI remain
pending; the previous image or CI must not be relabelled as this validation.
No security finding was accepted or dismissed remotely.

## Earlier decoder and bootstrap fixes — published c037c86

The earlier dependency patch updated packages matching the saved GitHub alerts.
The complete hashed-bootstrap comparison finds 62 matching alert records among
80 open records:7critical,28high,22medium,5low. Multiple records may concern one
advisory; these are not unique CVE counts. Eighteen do not match current versions.
That patch removes61of62version-range matches; remote alerts were not accepted
or dismissed. [Local validation](evidence/dependency-remediation-local-20261028.json)
and [exact-commit CI40607898664](https://github.com/Investments-Assistant/investments-assistant-local-machine/actions/runs/40607898664)
pass for c037c86. This is earlier source-specific evidence, not the certificate
candidate's build or CI result.

| Input | Before | Published c037c86 |
|---|---|---|
| Pillow |12.3.0|13.0.0|
| Brotli (CPython)|1.2.0|1.2.1|
| brotlicffi (other implementations)|1.2.0.1|1.2.1.0|
| Poetry bootstrap filelock|4.1.0|4.2.1|
| Poetry bootstrap virtualenv|21.14.6|21.14.13|

At that commit only three runtime lock entries changed. Explicit security floors
retained existing implementation markers. Poetry2.3.4, other runtime lock packages,
Dockerfile, base-image selection and application source were unchanged by that
earlier patch. The bootstrap retains wheel-only
installation and upstream hashes. [Pillow13release notes](https://pillow.readthedocs.io/en/stable/releasenotes/13.0.0.html),
[Brotli1.2.1](https://github.com/google/brotli/releases/tag/v1.2.1),
[brotlicffi1.2.1.0](https://pypi.org/project/brotlicffi/1.2.1.0/),
[filelock4.2.1metadata](https://pypi.org/pypi/filelock/4.2.1/json) and
[virtualenv21.14.13metadata](https://pypi.org/pypi/virtualenv/21.14.13/json)
confirm available fixes. Virtualenv21.14.9 would leave a newer published advisory;
21.14.13 also incorporates subsequent security patches without a minor-version jump.

Lock consistency, hash-pinned bootstrap resolution and26existing focused unit
cases pass. Real generated PNG and WOFF2 resources roundtrip and render through
WeasyPrint70into a one-page PDF with image/font metadata, both in a QA overlay and
in the new non-root/read-only/network-disabled image. All187context inputs and
184copied files are source-bound. Existing project/operator environments were not
updated. The sandbox unit timeout and initial empty-stdin renderer failure remain
in the evidence; native execution and corrected renderer passed without weakening
assertions or rebuilding. No PyPy, ARM64 runtime, real-model, deployment, broker,
research or final-host acceptance is claimed. No laptop soak or thermal test ran.

DiskCache5.6.3 remains a medium residual with no patched release at this audit.
Its [advisory](https://github.com/advisories/GHSA-w8v5-vhqr-4h9v) requires modifying
a cache directory before serialized objects are read. The application does not
activate persistent Llama caching; the pinned upstream constructor defaults to
`cache = None`. This is a scoped mitigation, not a patched or accepted vulnerability.
Keep caching disabled; do not read pre-existing or untrusted disk caches. Any
future cache feature needs a separate safe serialization and ownership design.
Live trading and external broker writes remain disabled.
