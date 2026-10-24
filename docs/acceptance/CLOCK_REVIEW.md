# Clock discontinuity investigation

## Current direction — 22 October 2026

The owner will deploy on a different computer. Stop this laptop's clock-repair,
24h observation and CPU-temperature work; those checks are **DEFERRED to the actual
final host**, not passed. No laptop NTP/service experiment, guard relaxation or new
soak is pending. The historical cause below remains unproven; it does not diagnose
the unknown final computer. Keep the250ms continuity guard and carry read-only
clock checks into the [final-host handoff](FINAL_HOST_HANDOFF.md). Any target OS
change still requires concrete review and applicable approval. Research and Paper
gates remain open; this scheduling decision does not complete the Goal.

## Historical20Oct result

The newly reviewed078d596f2f79 observation launched once, then failed
CLOCK_DISCONTINUITY after39.744seconds. Its finite verifier ran the immutable
terminal auditor once; the auditor correctly rejected the FAILED window. No
continuous24-hour acceptance or live run remains.

A separate read-only45.007-second probe retained4369 paired readings. Root
independently recomputed one backward wall step of311.304ms relative to monotonic
elapsed time, versus about10microseconds paired-read uncertainty. During that
pair, wall delta was-301.070ms while monotonic/raw/boottime deltas were each about
+10ms. This reproduces a host-clock discontinuity; it does not establish its cause.
[Exact raw provenance and review](evidence/clock-soak-failure-20261020-078d596f2f79.json)
retain the sample, script, service metadata and hashes.

systemd-timesyncd reports active/running. No clock or service setting was changed,
no model load was started for this probe and the soak was not retried. The earlier
13Oct temporary experiment was restored and did not establish disabling NTP as
a fix. Keep the250ms guard. A new observation requires a stable host clock;
any proposed OS intervention still needs its own concrete review/approval.

## Historical13Oct investigation

The fresh awake soak failed CLOCK_DISCONTINUITY after about10 seconds. No
24-hour run is active. The separate90-second paired-clock observation captured
six positive wall-clock adjustments, each0.67–0.91 seconds, against about10ms
monotonic elapsed time. Maximum paired-read time was94 microseconds, far below
the observed jumps. Events clustered near23/53/83 seconds, roughly30s apart.
Evidence: [paired readings](evidence/clock-pairs-load-20261013.json).
The local existing-model benchmark completed with exit0 during this diagnostic
window; do not infer that every jump overlapped inference.

Read-only diagnostics show systemd-timesyncd active, reported NTP offset+910.292ms,
clocksource tsc, and Hyper-V timesync_implicit=Y. Both time synchronization paths
exist; their interaction is a hypothesis, not a verified cause. The earlier
backward steps and confirmed sleep interruption remain distinct evidence.

## Historical proposed bounded experiment — not a new request

1. Confirm systemd-timesyncd is initially active and record status.
2. Install an unconditional cleanup handler that starts it again.
3. Temporarily stop only systemd-timesyncd inside this WSL distribution.
4. Run a90-second paired-clock observation with the same existing local-model
   benchmark; keep Hyper-V and Windows time configuration unchanged.
5. Restore systemd-timesyncd and verify it is active, even if the probe fails.
6. Compare both directions of clock adjustment. Do not infer a permanent fix
   from a single short observation or automatically change persistent settings.

No clock value is manually set; no configuration file, power setting, trading
setting or Windows service is changed. The temporary service stop affects this
WSL distribution, so it exceeds the original checkout-scoped implementation
permission. At the time of this proposal no such stop had been performed; the
separately approved experiment and restoration are recorded below. Preserve
the250ms discontinuity threshold. The22Oct direction supersedes any further
laptop repair or soak proposal.

Kernel background (does not diagnose this machine):
https://docs.kernel.org/virt/hyperv/clocks.html
https://docs.kernel.org/timers/timekeeping.html


## Approved temporary clock-service experiment (2026-10-13)

The user explicitly approved the 90-second stop/test/restore experiment.
Executed `.qa/temporary_clock_test.py` through `wsl.exe -d Ubuntu -u root`;
passwordless sudo was unavailable. An independent 100-second restoration
watchdog protected against loss of the controller; it was terminated only after
successful restoration. No persistent service configuration changed.

Service state: active → inactive → active. Stop/restore elapsed 90.266 seconds;
probe and local model benchmark both exited 0. During 90.004 seconds and 8,865
paired samples, two forward divergences were 102.6 and 121.9 ms. Prior service-on
observation had six divergences of 674.5–913.6 ms. This short comparison suggests
a synchronization interaction but does not establish cause or long-term stability.
The 250 ms guard remains unchanged; no 24-hour soak is running.

Evidence: `evidence/clock-service-test-20261013.json`,
`evidence/clock-pairs-ntp-stopped-20261013.json`.
A matching service-restored observation was then started; its finished result
follows. No historical command or watcher is a current retry instruction.


Restored-service control finished: 90.005 seconds, 8,853 samples, maximum wall/
monotonic divergence 42.8 ms, no event above 50 ms. Matching model benchmark
exit0. Service remains active; latest reported offset +101.798 ms. The control
is better than the stopped-service trial, so these observations do NOT establish
that disabling NTP is a fix. Normal service settings were retained. A90-second
isolated soak preflight was then proposed before a fresh full window; this is
historical context, not a pending22Oct action. No guard changed.
Evidence: `evidence/clock-pairs-ntp-restored-20261013.json`.
