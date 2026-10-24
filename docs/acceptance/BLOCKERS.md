# Remaining gates and prerequisites

## Owner direction — 22 October 2026

This laptop is not the deployment target. Its24h observation, mapped CPU-temperature
measurement and clock repair are **DEFERRED to the actual final host**, not passed;
stop pursuing them here. The pending laptop Portable ZIP download/setup request is
cancelled. Final-host OS/architecture/hardware are unknown; use the
[handoff](FINAL_HOST_HANDOFF.md) for conditional preparation and new acceptance.

The owner explicitly keeps **research and Paper gates OPEN**. L04/L14/L15 are not
deferred or complete. Portable checkout implementation can continue; an offline
durable Paper intent/attempt journal cannot authorize an actual read, order or
reconciliation claim. Live stays OFF and external SDK writes remain closed.
The Goal remains incomplete. Historical failures/proofs are preserved below;
later source/migration changes require affected checks before reusing their PASS.

## Current portable verification — 23 October 2026

The [offline journal](BROKER_SUBMISSION_CONTRACT.md), migration0020 and retained
closed SDK boundaries pass [119 focused checks](evidence/paper-submission-focused-20261022.json)
and [907 unit/431 PostgreSQL cases](evidence/paper-submission-backend-20261022.json).
[Current image/runtime](evidence/paper-submission-image-review-20261023.json) and
[committed-byte mapping](evidence/paper-submission-published-image-reconciliation-20261023.json)
pass. The owner approved the exact16-file patch; [publication](evidence/paper-submission-publication-20261023.json)
as a2b2f42 is complete. CI39875250173 and its configured Sonar gate pass;
[verified CI](evidence/paper-submission-ci-20261023.json) retains actual1342combined cases,24browser/8TLS-WSS checks and84.28%coverage.
No CI/publication blocker remains for that exact bundle. The subsequent six-file
lost-acknowledgment correlation patchb2da is now locally tested, image-checked,
separately approved and [published asd5aa99e](evidence/paper-recovery-publication-20261023.json).
Its [published-image reconciliation](evidence/paper-recovery-published-image-reconciliation-20261023.json)
passes for187context/184copied files; source13aa/tests12db are unchanged. Exact new
[exactCI/Sonar39983987095](evidence/paper-recovery-ci-20261023.json) now passes
all4jobs/920unit/459PG/1383overlappingcombined/24browser/8TLS-WSS, zero failures/
errors/skips and84.40% measuredcoverage. No publication/CI blocker remains. Local
920unit/459distinctPG cases have passing executions, with the original fullPG
clockfailure and one targetedretry retained. Research/Paper inputs remain open.
[Local0020 DB-only durability](evidence/paper-submission-durability-20261023.json)
passes actual ownedPG restart/new journal object/no resend, with all33public tables/
17rows restored and independently matched by SQL counts/hashes. No Python-process
restart, ephemeral vault-key recovery or restored-copy dispatch was exercised.
Actual Paper and target-host acceptance remain pending. These are portable checks,
separate from the deferred final-host24h/temperatures. Actual Paper/research remain
OPEN. Goal service reports PAUSED; no status was changed by these local checks.

## Recorded baseline before this direction

Checkpoint2026-10-20: published HEADe154a0a365ece2a9fd81657034139c43c8e0abe6;
its approved credential/packaging bundles and CI/Sonar remain valid. New local
seven-file cash/halt candidate source4fd1380c passes860unit/392PostgreSQL and
current-image/runtime/recovery/cleanup; exact publication is approved and complete,
current remoteCI39083730719/allfourjobs/configuredSonar PASS for exacte154. Last custom audit90%/raw89.875. Window79f7ab59792c was interrupted by another kernel restart before24hours.
Its stale RUNNING file earns no24h credit. The fresh078d window failed after
39.744seconds on CLOCK_DISCONTINUITY; a read-only probe reproduced a311ms backward
step. No observation is running; no clock setting or performance guard changed.

A verified WSL kernel restart stopped the private app and source observation.
Existing operator PG recovered without recreating data, migrating or replacing
keys. Normal app recovery passed native and ordinary Windows HTTPS checks;
the owner confirms both saved read flags are disabled. One actual authorized UI broker read persisted; positions complete,
cash incomplete/non-atomic, SDK environment unverified, execution authority none.
Relay17497 is closed; no new read/order. The interrupted73-cycle window has no
24h credit. [Checkpoint](CHECKPOINT.md) preserves exact recovery receipts/failures;
[boot evidence](evidence/native-kernel-interruption-20261017.json) establishes the
restart but not its cause. Goal service nowACTIVE; no completion claimed.

| Area | Evidence and remaining condition | Next safe step |
|---|---|---|
| L10/L13 continuous observation — DEFERRED | Historical79f7 stops at2824cycles/80574.770seconds,87restarts/23model runs, without terminal PASS; its bound boot/observer identities are obsolete. Fresh078d failed CLOCK_DISCONTINUITY after39.744seconds and its verifier rejected it. The [clock probe](evidence/clock-soak-failure-20261020-078d596f2f79.json), [233-file archive](evidence/soak-24h-cash-20261020-078d596f2f79-failure-review.json) and [exact fixture cleanup](evidence/soak-24h-cash-20261020-078d596f2f79-cleanup.json) preserve the result. | No further laptop soak or clock repair. Carry unchanged duration/gap/performance/model requirements to a fresh source-bound final-host observation and independent audit; see [handoff](FINAL_HOST_HANDOFF.md). No old helper/cluster resume, blanket cleanup or OS/power change. Deferral grants no24h credit. |
| Historical e154 image/runtime | [New candidate image review](evidence/cash-collector-image-review-20261018-5d8b5cb04c1b.json) verifies source4fd1380c/image92eabede:184context/181copied files, actual readonlyGGUF/nonroot production app, persisted halts, app7.167s/DB1.130s restarts and owned cleanup. Prior unchanged UI/ingress surfaces are reconciled, not rerun. | Local validation complete; preserve provenance. Exact seven-file approval/publication is complete (e154a0a); current remoteCI39083730719/allfourjobs/configuredSonar is verified PASS for exacte154. |
| L13 mapped CPU cooling — DEFERRED | Preserved672-sample ACPI THM0 series covers11h11m51s,67.05–95.05C, passive100/throttle0. Its component remains unmapped, so no CPU cooling acceptance. The earlier HWiNFO review is historical. | Laptop ZIP/download/setup request cancelled22Oct. Select a trusted component-mapped source appropriate to the unknown final host and retain sustained-load evidence there. No sensor tool, driver or OS change is preapproved; see [cooling review](COOLING_REVIEW.md) and [handoff](FINAL_HOST_HANDOFF.md). |
| L04/L15 broker paper lifecycle | User selected same encrypted account and confirmed one read through normal UI. Persisted1snapshot/valid owner/binding/idempotency metadata; positionscomplete/cashincomplete/non-atomic, declaredPaper/SDKunverified/authoritynone. Actual read is partial evidence only. App stopped on kernel restart; PG/app recovered; relaygone/17497closed. | App restored; owner confirms Enabled/Read Authorized unchecked and saved. Do not repeat read. Full reauthentication/history/execution/reconciliation/forward plan remain separate, with orders requiring additional authority. |
| L14 research/economic evidence | Fixed cost-aware fixture replay passes; economic result INSUFFICIENT EVIDENCE. Owner confirms no local file, approves the bounded EODHD Sandbox check and reports the free account/key ready. Helper25offline checks pass; exact nine-request plan is prepared, not started. No actual data, approved real-study universe or sufficient coverage is established. Yahoo permissions remain OFF. Historical unintended baseline lookup has unknown outcome; later tests mock or deny provider imports. | Confirm at least nine free calls remain, then inspect the SAME unstarted, unexpired hash-bound manifest before the [private source check](RESEARCH_SOURCE_PROPOSAL.md). Do not purchase, blindly retry a partial run, enable an app provider, change fixture splits/targets or claim preparation passes L14. |
| Real bank sync/external operations | Synthetic consent, adapter, restore and local alert tests pass; no real institution consent, external destination or off-host target configured. | Keep disconnected; obtain concrete target/privacy scope and separate setup/notification/deployment authorization. No public/LAN exposure or firewall changes. |
| L16 live eligibility | PASS(NO-GO; safely disabled): LIVE_TRADING_ENABLED=false and all external SDK writes denied even under synthetic true flag. | Keep live OFF; no live mandate or trading authorization. |

## Resume safely

The20Oct kernel restart also makes the pending old-boot app-only refresh proposal
stale. [Native metadata](evidence/operator-runtime-metadata-20261020.json) found no
matching private-directory cwd among readable processes; inaccessible processes
prevent an exhaustive absence claim. Existing private data remains present.
No runtime recovery, SQL, secret access or account-setting change was performed.
Any recovery requires a freshly reviewed proposal and its applicable authority;
old app-only approval must not be treated as database restart approval.


Do not resume/restart either completed24h window or rerun its database cleanup.
The historical f945-source observation is terminal PASS_24H_VERIFIED and its owned
fixture database has been removed. Preserve all raw evidence and unrelated
PostgreSQL databases/server; no production cleanup is authorized.

Historical f945 terminal review: evidence/soak-24h-read-final-20261015-terminal-review.json.
Portable raw evidence/manifest: evidence/soak-24h-read-final-20261015-raw.tar.gz and
soak-24h-read-final-20261015-archive.json. Cleanup proof:
evidence/soak-24h-read-final-20261015-database-cleanup.json.
Current credential/CI validation: FLEXIBLE_CREDENTIALS.md; historical image
validation: READ_ADMISSION.md. Historical decisions and
unknown baseline lookup/import-stall outcomes: CHECKPOINT.md.

Smallest next steps, without credentials in chat:

For a step-by-step explanation, start with [Getting the prerequisites ready](PREREQUISITES.md).

1. Paper gate: the displayed simulated TWS session and reported API settings are
   recorded. Approved certificate trust and ordinary Windows HTTPS now pass in
   evidence/paper-local-certificate-application-20261016.json. The user has
   registered and selected their encrypted Paper account. One normal UI read
   persisted partial evidence, then WSL restarted. Existing data/app are recovered
   ([HTTPS proof](evidence/paper-local-app-recovered-20261017.json)). Owner confirms
   that SAME record now has Enabled/Read Authorized unchecked and saved; do not
   repeat the read. [Metadata proof](evidence/paper-ui-read-metadata-20261017.json) records
   cash/environment/history/reconciliation limitations. Existing
   read-only approval does not authorize Paper submissions or a forward plan.
   Inspect private runtime receipts/PIDs before restarting anything; never use
   synthetic fixture cleanup against the new private operator database.
2. Research gate: the owner has no existing price-history file. Review the
   [approved free private source check](RESEARCH_SOURCE_PROPOSAL.md); owner confirms
   account/key ready and the nine-request manifest is prepared. Remaining free
   allowance confirmation is pending, and no data request has occurred.
   A source check is separate from real-study approval; the result remains
   INSUFFICIENT EVIDENCE. No purchase or arbitrary download is authorized.
3. Final-host gates: leave this laptop's cooling/24h/clock work deferred. Once the
   real target is known, follow [FINAL_HOST_HANDOFF.md](FINAL_HOST_HANDOFF.md) for
   inventory, compatible profile, fresh fixtures and independent acceptance.
   The laptop Portable ZIP request is cancelled; do not download or set it up.

Reproducible next step after supplying any prerequisite: resume this Goal and
inspect the latest CHECKPOINT.md/PLAN.md before acting; reuse current credential/CI
proofs within their recorded scope and verify no duplicate job before a new authorized operation. Rerun checks only for
subsequent changes or unresolved failures. Historical f94524h evidence is not a
pass for the new fingerprint.
The optional real-bank/off-host/notification gates remain separately disconnected;
they are not implied by the local fixture passes.

IBKR Paper means a simulated account/session with pretend money; an ordinary
login alone does not establish that environment. Historical prices means a
permitted dataset of past stock/fund prices with its instruments and dates.
Neither credentials nor account numbers belong in chat. If these prerequisites
are unavailable, retain the explicit incomplete gates; never invent evidence.

## 23 October — current portable validation boundary

Six-file lost-acknowledgment recovery code is implemented and locally tested:920unit,
459distinct PostgreSQL cases with a passing execution, including one targeted retry
after the unchanged short clock test failed `CLOCK_DISCONTINUITY`. Original failure
is retained as a localfulltierfailure. New exactCI passes459/459 with no failure/skip.
Actual Paper and research remain OPEN.

Docker prerequisite is resolved: owner started the engine, and new imagebuild+
network-none/nonroot smoke pass with all187context/184copied bytes verified; no
owned temporary container remains. [Image evidence](evidence/paper-recovery-image-review-20261023.json).
The owner approved exact six-fileb2da0209 publication. It is now onorigin/main
asd5aa99e, with indexempty and exactremoteSHA verified; [newCI/Sonar39983987095](evidence/paper-recovery-ci-20261023.json)
passes, including clean459PG cases. No publication/CI permission or task remains
pending for this bundle. The failed fullPG clock
case and its passing targetedretry remain explicit. Native fixture cleanup passed;
no test/build/watch/container operation remains. No24h laptoptest is needed and no
operator/broker flags changed. Research/Paper external prerequisites remain open.
