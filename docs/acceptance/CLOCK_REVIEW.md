# Clock discontinuity investigation

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

## Proposed bounded experiment — requires explicit OS-change approval

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
permission. No such stop has been performed. Preserve the250ms discontinuity
threshold and do not restart the full soak before the host issue is understood.

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
A matching service-restored observation is running; inspect it before retrying.


Restored-service control finished: 90.005 seconds, 8,853 samples, maximum wall/
monotonic divergence 42.8 ms, no event above 50 ms. Matching model benchmark
exit0. Service remains active; latest reported offset +101.798 ms. The control
is better than the stopped-service trial, so these observations do NOT establish
that disabling NTP is a fix. Normal service settings are retained. Starting a
90-second isolated soak preflight before a fresh full window; no guard changed.
Evidence: `evidence/clock-pairs-ntp-restored-20261013.json`.
