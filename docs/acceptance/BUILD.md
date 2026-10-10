# Build inputs and remaining validation

The Python base, PostgreSQL and Nginx official multi-platform manifests are pinned
by SHA256. The registry response bytes were hashed and matched to the registry
digest; Linux amd64 and arm64 entries were verified. Evidence:
`evidence/container-image-manifests-20261009.json`. Only small manifest documents
were fetched; no image layers, models, production data or credentials were sent.

Poetry2.3.4 now matches the existing CI toolchain and installs the existing
`poetry.lock`. `.dockerignore` allows only Dockerfile inputs, excluding the local
environment, models, reports, Git history, caches and disposable PostgreSQL data.
Runtime models remain read-only mounts; they are not image build inputs.

This fixes declared image, apt repository and Poetry bootstrap inputs, but is
not a bit-identical native compilation or successfully built image claim.
The image has not been built or booted here because Docker's Linux daemon is
unavailable. The isolated Ubuntu Nginx check does not validate this Alpine image.
Container acceptance remains pending; registry metadata is not runtime evidence.

Update digests deliberately when reviewing security updates. Retrieve each
official registry manifest, verify its SHA256 and required platforms, update
the reference and evidence together, and run the manual local-machine release
validation workflow plus isolated startup/ingress/restart checks. Do not deploy
to an existing instance without authorization. Restore previous references to
roll back an unaccepted build candidate; do not downgrade an existing database.

Docker documents why mutable tags need digest pins and why updates still require
review: https://docs.docker.com/build/building/best-practices/#pin-base-image-versions

## Hash-locked Poetry bootstrap (2026-10-10)

`requirements-poetry.txt` pins all46 resolved packages and67 compatible wheel
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

`config/build/debian.sources` fixes bookworm, bookworm-updates and bookworm-security
to the20261009T000000Z archive. The Docker recipe replaces only the container's
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

This validates amd64 repository authentication and dependency resolution from an
empty isolated status file. It is not resolution inside the pinned Python image,
an ARM64 build, or application startup. Those checks still require Docker.
References: https://snapshot.debian.org/ and
https://manpages.debian.org/bookworm/apt/apt-secure.8.en.html
