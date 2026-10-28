# Dependency security — 28 October 2026

The dependency candidate updates the packages that match the saved GitHub alerts.
The complete hashed-bootstrap comparison finds 62 matching alert records among
80 open records:7critical,28high,22medium,5low. Multiple records may concern one
advisory; these are not unique CVE counts. Eighteen do not match current versions.
The candidate removes61of62version-range matches; remote alerts were not accepted
or dismissed. [Local validation](evidence/dependency-remediation-local-20261028.json)
is complete; exact-commit CI is required after publication.

| Input | Before | Candidate |
|---|---|---|
| Pillow |12.3.0|13.0.0|
| Brotli (CPython)|1.2.0|1.2.1|
| brotlicffi (other implementations)|1.2.0.1|1.2.1.0|
| Poetry bootstrap filelock|4.1.0|4.2.1|
| Poetry bootstrap virtualenv|21.14.6|21.14.13|

Only three runtime lock entries change. Explicit security floors retain existing
implementation markers. Poetry2.3.4, all other runtime lock packages, Dockerfile,
base-image selection and application source remain unchanged. The bootstrap retains wheel-only
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
