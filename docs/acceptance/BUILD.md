# Build inputs and remaining validation

## 28 October certificate remediation candidate

The current candidate pins Python3.12.16-slim-bookworm to multi-platform digest
`sha256:62ed8e07e544e8555c5d93748d5275015136b7f5c52b5e8679b4de339c3779d3`.
The registry identifies Linux amd64 and arm64 images. Python's
[3.12.16 release](https://www.python.org/downloads/release/python-31216/)
adds rejection of the compromised eMudhra intermediate keys. The dated Debian
repositories move to20261028T000000Z and ca-certificates is fixed at
20250419~deb12u2, preserving archive signature verification. Runtime/bootstrap
certifi is2026.10.23 and the hash-locked bootstrap adds pip26.2.2, following
[Python's incident guidance](https://discuss.python.org/t/information-for-python-users-regarding-emudhra-emsign-ca-certificate-security-incident/109576).

Poetry lock consistency and a47-package amd64 wheel-only bootstrap dry-run pass;
other149 runtime package records remain byte-identical. A new clean image build
and actual container certificate-store checks are still required. ARM64 execution
and new ARM64 bootstrap resolution are not established by the amd64 checks.
Existing host environments, private app and OS trust stores remain unmodified.
See [dependency scope and residual risk](DEPENDENCY_SECURITY.md). The dated proofs
below describe their original inputs and must not be treated as this new build.

## Historical build verification

The original Python base, PostgreSQL and Nginx multi-platform manifests were pinned
by SHA256. The registry response bytes were hashed and matched to the registry
digest; Linux amd64 and arm64 entries were verified. Evidence:
`evidence/container-image-manifests-20261009.json`. Only small manifest documents
were fetched; no image layers, models, production data or credentials were sent.

Poetry2.3.4 now matches the existing CI toolchain and installs the existing
`poetry.lock`. `.dockerignore` allows only Dockerfile inputs, excluding the local
environment, models, reports, Git history, caches and disposable PostgreSQL data.
Runtime models remain read-only mounts; they are not image build inputs.

The earlier pinned amd64 image built successfully on Docker Desktop's Linux engine.
`evidence/container-build-20261010-ad17fb8e.*` records the first successful build;
`evidence/container-startup-build.txt/.exit` records the updated image after
deferring unused market-data imports. See CONTAINERS.md for actual native-library,
startup and restart results. This is not a bit-identical compilation or ARM64
execution claim. The isolated Ubuntu Nginx check does not validate the Alpine
container or Docker Desktop source-address handling.

Update digests deliberately when reviewing security updates. Retrieve each
official registry manifest, verify its SHA256 and required platforms, update
the reference and evidence together, and run the manual local-machine release
validation workflow plus isolated startup/ingress/restart checks. Do not deploy
to an existing instance without authorization. Restore previous references to
roll back an unaccepted build candidate; do not downgrade an existing database.

Docker documents why mutable tags need digest pins and why updates still require
review: https://docs.docker.com/build/building/best-practices/#pin-base-image-versions

## Hash-locked Poetry bootstrap (2026-10-10)

The original `requirements-poetry.txt` pinned46 resolved packages and67 compatible wheel
hashes for CPython3.12 Linux amd64/arm64 with glibc at most2.36. Docker installs
with `--require-hashes --only-binary=:all:`; missing or changed distributions fail
closed. The context allowlist includes this lock file. Application `poetry.lock`
and the active application virtualenv were not modified.

A new `.qa/poetry-bootstrap-20261010` virtualenv installed the complete lock,
passed `pip check`, reported Poetry2.3.4, and passed `poetry check --lock` against
the existing application lock. Legacy pyproject deprecation warnings remain
visible. ARM64 wheels were separately downloaded with matching hashes; this is
compatibility/resolution evidence, not ARM64 execution or a Docker build. See
`evidence/poetry-bootstrap-verified.txt/.exit`,
`evidence/poetry-bootstrap-arm64.txt/.exit` and
`evidence/poetry-bootstrap-review.json`.

Recheck in a NEW disposable environment:

```sh
python3 -m venv .qa/poetry-bootstrap-new
.qa/poetry-bootstrap-new/bin/python -m pip install \
  --require-hashes --only-binary=:all: -r requirements-poetry.txt
.qa/poetry-bootstrap-new/bin/python -m pip check
.qa/poetry-bootstrap-new/bin/poetry check --lock
```

For a reviewed update, first resolve the explicit Poetry version with
`pip install --dry-run --ignore-installed --only-binary=:all: --report <new.json>
poetry==<version>`. Pin every reported package and collect SHA256 hashes from
that exact version's PyPI release metadata for compatible CPython3.12 wheels.
Check both supported architectures and repeat the isolated installation before
replacing the lock. Do not regenerate dependencies as part of an ordinary build.
Reference: https://pip.pypa.io/en/stable/topics/secure-installs/

## Dated Debian repositories (2026-10-10)

The original `config/build/debian.sources` fixed bookworm, bookworm-updates and bookworm-security
to the20261009T000000Z archive; the current candidate deliberately advances it as
described above. The Docker recipe replaces only the container's
repository files; no host apt configuration was changed. Signature verification
remains required through Debian's archive keyring. `Check-Valid-Until: no` applies
only to these dated archives, as documented by Debian; it permits intentionally
archived metadata after expiry and does not trust unsigned or modified indexes.
Updates now require deliberately refreshing the snapshot and base digest, then
repeating build/security validation. Do not describe this as automatic patching.

Three InRelease bodies were downloaded and hashed. An initial raw gpgv check
returned2 because Ubuntu's older extracted keyring lacks an additional signer;
known bookworm signatures were valid. Actual apt authenticated all repositories
and fetched their indexes successfully in an isolated `.qa/debian-snapshot-apt`
state/cache/config, with no insecure flags or system hooks. A simulated install
resolved all15 Docker build package roots and transitive dependencies, installing
nothing. Evidence: `debian-snapshot-probe-20261010.json`, `debian-snapshot-apt.txt`
and `.exit`, `debian-snapshot-resolution.txt` and `.exit`, and
`debian-snapshot-review.json` in the evidence directory.

The isolated apt check validates amd64 repository authentication and dependency
resolution from an empty status file. The subsequent Docker build also installs
these dependencies inside the pinned Python image. ARM64 execution remains
unverified; application startup/restart has its own evidence in CONTAINERS.md.
References: https://snapshot.debian.org/ and
https://manpages.debian.org/bookworm/apt/apt-secure.8.en.html

## CI test-report import repair

The unit, integration and combined workflows generate pytest JUnit XML. They
now pass those files through `sonar.python.xunit.reportPath`, rather than the
generic `sonar.testExecutionReportPaths` importer, which requires a different
XML schema. Producer filenames, YAML and shell syntax were checked in
`evidence/ci-xunit-routing-review.json`; a retained actual pytest report has
`testsuites`/`testcase` elements. This configuration verification is not a
successful remote Sonar scan by itself. Subsequent
[exact c037c86 CI](https://github.com/Investments-Assistant/investments-assistant-local-machine/actions/runs/40607898664)
and its configured primary Sonar gate pass. Authorization is available; the new
certificate candidate still needs its own exact-commit checks after publication.
Primary reference:
https://docs.sonarsource.com/sonarqube-cloud/analyzing-source-code/test-coverage/test-execution-parameters
