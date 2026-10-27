# Saving account consent before a broker read

The account editor previously left **Read broker evidence** available while an
asynchronous **Save account** was pending. A read could reach the server with the
previous saved OFF flags and return `IBKR_READ_CONSENT_REQUIRED`. A synthetic
Chromium reproduction held the Save request before commit and observed a read
confirmation and refresh POST escaping. This proves the UI race; it does not
establish the exact cause of the owner's failed session.

The UI now requires acknowledged saved consent before enabling a read. Both
saved flags must be true, the account must not be under edit, and no save or read
may be pending. The handler checks the same conditions before confirmation.
Successful Save updates the account from the server's response; older account
loads cannot replace that acknowledgement. A failed Save keeps the edited
account blocked. Saved historical evidence remains independently available.
Backend authorization, post-read revocation checks and closed SDK write routes
are unchanged.

The HTML also requests the script with the new `broker-consent-20261027a` version
so the deployment proxy's one-hour asset cache does not retain the old handler.

## Validation

- [Focused regression](evidence/broker-consent-save-focused-20261027.json): old
  source fails deterministically; the fix passes at 1440×1000 and 390×844 with all
  HTTP intercepted. OFF, draft, pending, failed-save and direct-handler cases
  cannot confirm or POST a read; successful acknowledgement restores saved flags.
- [Full browser gate](evidence/broker-consent-save-browser-20261027.json): all 24
  flows pass through real routes and a fresh marked PostgreSQL fixture, including
  the regression, ownership, CSRF and revocation checks. No unexpected console
  errors; only the exact intercepted synthetic PUT503 is added to the existing
  expected-error scope. Owned fixture/server cleanup is verified.
- [Image gate](evidence/broker-consent-save-image-20261027.json): 187 public
  context files and all 184 copied image files match. The non-root, read-only,
  network-disabled smoke verifies the Save control and container cleanup.
- Ruff, JavaScript syntax and whitespace checks pass. Python application bytes
  are unchanged, so the independently verified base 961-unit/459-PostgreSQL
  results remain scoped evidence; they were not rerun for this UI change.

Browser plugin was unavailable; installed Playwright Chromium was used without
installing dependencies. Screenshots and their hashes are retained locally as
listed in the evidence. These checks use synthetic identities, model/provider
responses and broker facts. They do not verify an actual Paper read, full broker
history or fees, economic results, or deployment-host acceptance. Exact CI for
this new candidate remains required after its separately approved publication.

## Operator boundary

Keep both saved read switches OFF until a new specific Paper-read window is
approved and its transport is ready. In that approved window, edit the intended
saved account, enable both switches and save. Wait for saved acknowledgement and
the **Read permission saved** status before one explicitly confirmed read. After
the request finishes, save both switches OFF again. This guide grants no read,
retry, order, cancellation or live-trading authority.

The previous one-use helper claim remains consumed. Its clock-guard shutdown and
the failed request's unchanged observations remain separate evidence; this UI fix
does not disable that guard or repair the host clock. Actual SDK writes remain
closed and live trading remains OFF.
