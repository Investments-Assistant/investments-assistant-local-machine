# Component-temperature acceptance — deferred to final host

## Current direction — 22 October 2026

The owner will deploy on a different computer and explicitly deferred this
laptop's CPU-temperature checks,24h observation and clock repair to that actual
final host. The pending laptop Portable ZIP download/setup request is cancelled.
No further laptop sensor download, execution or installation is requested.
L13 final-host cooling remains **DEFERRED, not PASS**; research and Paper gates
remain open and the Goal is incomplete.

The final host's OS, architecture and sensors are unknown. Select an already
available trusted component-mapped CPU package/core source appropriate to that
computer before proposing any new tool or privileged access. Retain raw sensor
labels/units, timestamps/time zone, workload/effective clocks and available thermal
throttling fields through baseline, representative sustained load and recovery.
Report unavailable fields; unmapped ACPI/GPU readings are not CPU cooling proof.
No install, driver/service, fan, power or other OS change is preapproved. The
[final-host handoff](FINAL_HOST_HANDOFF.md) carries the remaining validation.

## Historical laptop review — superseded request, preserve evidence

On2026-10-18 the owner confirmed that no existing CPU-temperature monitoring app
is installed. The earlier ACPI THM0 series remains unmapped; it cannot establish
CPU-package cooling. L13 was blocked at that review. No software or driver had been run or
installed during this review.

The historical laptop candidate was HWiNFO64 Portable. The publisher then listed
version8.54 and a ZIP containing the Windows tools on its
[official download page](https://www.hwinfo.com/download/).
Its [licensing page](https://www.hwinfo.com/licenses/) permits free personal,
non-commercial use; commercial use has different requirements. No paid license,
Pro automation, purchase or commercial-use permission is assumed.

The app supports manual sensor logging; its author describes the
[logging function](https://www.hwinfo.com/forum/threads/how-to-save-temperature-report.9274/)
and identifies [CPU Package as the relevant CPU value](https://www.hwinfo.com/forum/threads/question-for-auto-logging-and-saving-file.8738/).
Actual sensor availability and attribution on this laptop remain unverified.
Hardware access can require a privileged driver: the author's
[driver explanation](https://www.hwinfo.com/forum/threads/rainmeter-no-longer-sees-hwinfo-after-update.3053/)
describes administrator rights and a separate persistent-driver option. This
proposal does not authorize execution, elevation, a persistent driver, autostart,
remote monitoring or any OS, fan, voltage, firewall or power change.

The publisher ZIP returned HTTP403 to the bounded automated download; its
publisher-listed SAC mirror also returned403 through the web reader. The saved
local file contains zero bytes and is not a package. Owner browser download to
Downloads was requested, explicitly without running it; that request is now cancelled.
The proposed next review had been to inspect the actual
ZIP, exact executable version/hash and Windows Authenticode result before asking
for any execution/setup approval. No binary integrity or publisher-signature
claim can yet be made. Failed download receipts remain under
`.qa/cooling-sensor-review-20261018-hwi854`.

The superseded proposal, conditional on a verified file and separate setup
approval, was first to establish a populated
CPU Package/core sensor group attributable to the measured i7-11850H. Retain the
original local log, time zone, sensor labels/units and software version. Capture
temperature, CPU load, effective clocks and available thermal-throttling fields;
report unavailable fan/power fields rather than invent them. The operator chooses
the log path; hardware telemetry is not published or sent to a cloud service.

Its proposed bounded workload was the existing CPU4/GPU0/context4096 profile through
`scripts/benchmark_control_contention.py`: three native generations with real
authenticated ASGI/PostgreSQL halt checks, against a newly marked isolated
disposable database. Reuse its existing250ms halt budget. Prepare and positively
verify that fixture before use; never use the private operator database or the
historical79f7 soak database or any active observation database. Start logging before the workload, retain baseline and
recovery readings, and correlate with actual benchmark timestamps/results. Keep
the original source/model and fixed budgets. This proposed measurement has not
run; it cannot be substituted with a temperature screenshot, historical THM0,
simulator-only result or an invented full-day thermal claim.

Source review and candidate preparation add no completion credit. No laptop
downloaded filename, setup approval or further experiment is pending. Preserve
the failed download receipts and unmapped telemetry; they do not establish
final-host sensor availability or cooling.
