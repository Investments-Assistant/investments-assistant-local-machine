# Isolated container validation

The actual amd64 image build passed: `container-build-20261010-ad17fb8e.json`,
`.txt` and `.exit` in the evidence directory. Image:
`investment-assistant:container-build-20261010-ad17fb8e`.
Its source hashes and exported image digest are recorded. This is a local build;
the remote workflow has not run against the uncommitted checkout.

A Windows Docker client network-none smoke ran as UID1000, produced a real PDF,
loaded llama.cpp, and checked that `.env`, `.qa` and model files were absent from
the image. GPU offload is unsupported. Library inspection and `ldd` verify the
ggml BLAS backend links OpenBLAS; a cold system-info call alone omitted this
backend and was insufficient to judge linkage. No Dockerfile change followed
that observation. Evidence: `container-native-smoke-windows.txt/.exit` and
`container-openblas-linkage.txt/.exit`.

The first native WSL runtime command failed before container startup because WSL
integration disappeared. The direct Windows client remained available; no image
rebuild was needed. Preserve that failed command as environment evidence, not an
application test failure.

## Production startup and restart runner

`scripts/verify_container_runtime.py` creates uniquely named, labelled internal
network, volume and PostgreSQL/application containers. It publishes no host ports
and mounts no production storage. It positively verifies the new test database
name and random disposable marker before explicit migrations. It copies an
existing local model into the owned application container, starts the production
entrypoint, checks real database/model readiness, and restarts the application
and database separately. The existing15-second restart budget is enforced.
Only identifiers returned by its own creates are removed during cleanup.

```sh
.venv/bin/python scripts/verify_container_runtime.py \
  --docker '/mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe' \
  --image investment-assistant:container-build-20261010-ad17fb8e \
  --postgres postgres:16-alpine@sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea \
  --model models/qwen2.5-1.5b-instruct-q4_k_m.gguf \
  --output docs/acceptance/evidence/container-runtime-new.json
```

Use a new output path. Inspect a previous run's live process/terminal result and
owned resource names before retrying. This tier does not establish Nginx/LAN
ingress, broker/provider connectivity, model answer quality, OS sleep or24hours
of stability. Readiness and marker persistence are not evidence of trading-state
reconciliation. Actual acceptance results remain in the named JSON/exit records.

The initial runtime attempt failed because a Unix-socket readiness check raced
PostgreSQL's temporary initialization server shutdown. Its resources were cleaned.
The runner now waits for the final TCP listener; the reproduction remains in
`container-runtime-20261010.json/.txt/.exit`. Do not classify an active retry as
PASS before its checks and cleanup finish.
