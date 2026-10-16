# Remaining gates and prerequisites

Current checkpoint:2026-10-16 Lisbon date. HEAD227a095bffec978d74dabd653b15804a6efea8b6
is an external acceptance-documentation/evidence commit over approved source4e62b88;
source/tests/dependencies are unchanged. Preserve both that commit and local edits.
The current-source24h soak and guarded owned-database cleanup pass. Overall Goal
is ACTIVE/incomplete during the resumed audit, at90% (raw89.500/100); remaining gates depend on absent
Paper/account authority, permitted research data and mapped component telemetry.
PLAN.md is the acceptance matrix; CHECKPOINT.md preserves decisions/process state.
The final custom progress_monitor audit found no additional safe local code or
verification gap. These external prerequisites have remained absent across
multiple prior Goal turns. The Goal was previously marked blocked after final
audit, then automatically resumed. The current resume starts a fresh blocked
audit; it has not yet met the three-resumed-turn threshold for blocking again.

| Area | Evidence and remaining condition | Next safe step |
|---|---|---|
| L10/L13 current-source observation | RESOLVED: fingerprintf945c38d… passed86,400.165s,3,060samples/93restarts/zero failures. Independent raw review and progress_monitor confirm p9529.102ms<250ms, maximum recorded restart4.046s<15s,24CPUmodel runs/72correct answers. Original runner984335 exited; exact marked fixture database identity/state and removal verified. | Reuse terminal review, raw archive/manifest and database-cleanup evidence in SOAK.md. Do not restart/resume the completed window or repeat cleanup. Mapped cooling remains a separate L13 prerequisite. |
| Current image/runtime | RESOLVED for frozen follow-up: final image19c1f198… complete179-file match, production model/PG/migrations, halt persistence and app7.033s/DB1.104s recovery under15s PASS, exit0 and independently verified owned-resource cleanup. | Reuse completed short checks while source unchanged; this is no deployment, external recovery or24h claim. See CONTAINERS.md/READ_ADMISSION.md. |
| L13 mapped CPU cooling | Preserved672-sample ACPI THM0 series covers11h11m51s,67.05–95.05C, passive100/throttle0. Sensor does not map to CPU/GPU/chassis; no CPU-package cooling acceptance. | Use an available read-only component-specific source, or obtain separate approval for sensor setup. No OS/power/service changes inferred. |
| L04/L15 broker paper lifecycle | Simulator/SDK-shaped persistence, callbacks and recovery are tested. Read-only paper connectivity is authorized conditionally, but user has only an IBKR login and cannot verify a selected Paper session/account. No actual broker connection/order. External reauthentication and reconciliation unverified. | Provide plain-language setup help. Independently verify a simulated Paper session/account before connecting. Keep credentials/account IDs in secure local configuration, never chat; keep writes denied. Paper orders need separate explicit approval. |
| L14 research/economic evidence | Fixed cost-aware fixture replay passes; economic result INSUFFICIENT EVIDENCE. No named permitted price-history source, instrument universe, coverage or local file. Yahoo historical and market permissions independently default OFF. One unintended unmocked baseline lookup attempt has unknown connection/data outcome; corrected later tests mock or deny provider imports. | Identify an already-permitted dataset/source, instruments, dates and local path/usage limits before evaluating. Do not fetch arbitrary data or change predeclared split/targets. The user need not buy/install anything merely to acknowledge this absent prerequisite. |
| Current-source remote CI | RESOLVED:approved23-file patch is published as4e62b88. CI38717676258 all four jobsSUCCESS, combinedSonargatePASS;802unit/374PG/1180combined tests pass,83.93%combined linecoverage,24-flowbrowser/8ingresschecks pass. | Reuse terminal watch90342exit0 and retainedJUnit/coverage/job evidence while source unchanged. No pending publication permission for this bundle; do not rerun completed CI without a relevant change or concern. |
| Real bank sync/external operations | Synthetic consent, adapter, restore and local alert tests pass; no real institution consent, external destination or off-host target configured. | Keep disconnected; obtain concrete target/privacy scope and separate setup/notification/deployment authorization. No public/LAN exposure or firewall changes. |
| L16 live eligibility | PASS(NO-GO; safely disabled): LIVE_TRADING_ENABLED=false and all external SDK writes denied even under synthetic true flag. | Keep live OFF; no live mandate or trading authorization. |

## Resume safely

Do not resume/restart either completed24h window or rerun its database cleanup.
The latest current-source observation is terminal PASS_24H_VERIFIED and its owned
fixture database has been removed. Preserve all raw evidence and unrelated
PostgreSQL databases/server; no production cleanup is authorized.

Current terminal review: evidence/soak-24h-read-final-20261015-terminal-review.json.
Portable raw evidence/manifest: evidence/soak-24h-read-final-20261015-raw.tar.gz and
soak-24h-read-final-20261015-archive.json. Cleanup proof:
evidence/soak-24h-read-final-20261015-database-cleanup.json.
Current code/image validation: READ_ADMISSION.md. Historical decisions and
unknown baseline lookup/import-stall outcomes: CHECKPOINT.md.

Smallest next steps, without credentials in chat:

For a step-by-step explanation, start with [Getting the prerequisites ready](PREREQUISITES.md).

1. Paper gate: establish an IBKR simulated Paper session and securely verify the
   selected account. Existing approval covers read-only connection after that
   verification; external Paper submission/observation still needs separate
   agreement. The closed write boundary must remain closed until authorized.
2. Research gate: identify an already-permitted historical-price dataset, its
   instruments, dates, local path and usage conditions. Until then the result is
   INSUFFICIENT EVIDENCE; no arbitrary provider download or purchase is authorized.
3. Cooling gate: identify an existing trusted CPU-component temperature source,
   or separately authorize a concrete sensor-tool setup. No install, service,
   firewall or power change is inferred from the original checkout scope.

Reproducible next step after supplying any prerequisite: resume this Goal and
inspect the latest CHECKPOINT.md/PLAN.md before acting; use existing evidence,
not a fresh24h run, while application sources and dependencies remain unchanged.
The optional real-bank/off-host/notification gates remain separately disconnected;
they are not implied by the local fixture passes.

IBKR Paper means a simulated account/session with pretend money; an ordinary
login alone does not establish that environment. Historical prices means an
already-permitted file of past stock/fund prices with its instruments and dates.
Neither credentials nor account numbers belong in chat. If these prerequisites
are unavailable, retain the explicit incomplete gates; never invent evidence.
