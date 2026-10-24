# Flexible local login credentials

Both the ID and password remain required, as explicitly confirmed by the user.
There is no application minimum beyond nonempty, maximum character count, or
composition rule. Portuguese accents, symbols and spaces are accepted. Stored
credentials preserve their exact Unicode text, case and surrounding whitespace;
ordinary browser, transport and storage capacities still apply. The optional
display name remains a separate bounded presentation field.

Registration, login, CLI provisioning and configured bootstrap identity follow
the same policy. CLI-generated AUTH_USERNAME_BASE64 transports literal UTF-8
through dotenv and Compose without interpolation; existing AUTH_USERNAME remains
supported. Passwords retain salted scrypt hashes and bounded worker admission.

Migration 0019 widens username storage and uses a fixed 32-byte SHA256 lookup key
with exact-text comparison. A database trigger maintains the key for raw SQL and
updates. Core PostgreSQL functions require no extension; see the
[PostgreSQL16 binary functions](https://www.postgresql.org/docs/16/functions-binarystring.html).
A synthetic dump/restore also preserves an 8,593-character ID and its key/hash;
the restored database trigger remains effective. The frozen reviewed schema is unchanged. Rollback requires a reviewed backup;
long IDs must never be truncated to fit an old schema.

New signed cookies contain the stable user ID rather than the username. Their
size is independent of ID length. Canonical legacy cookies remain valid; aliases
with padding or ignored characters are rejected so they cannot evade logout
revocation. Login rechecks the active user, exact ID and unchanged password hash
under a row lock after password verification.

[Validation and retained failures](evidence/flexible-credentials-review-20261016.json):
825 unit tests; 390 distinct PostgreSQL cases reconciled from the selected full
run and affected reruns; four real signup/logout/login cases plus 24 existing
desktop/mobile browser flows. Examples include a 4,711-character Portuguese ID,
a 4,704-character password, one-character and whitespace passwords, pipe/quotes,
surrounding spaces, duplicate rejection and concurrent credential-change denial.
Browser testing uses synthetic data and deterministic model/provider fixtures.

The private operator app was backed up and upgraded without replacing data/keys.
The user created their own account and confirmed it opened. A later WSL kernel
restart stopped app/PG; guarded PG-only recovery preserved that account and its
one authorized read result. [App recovery](evidence/paper-local-app-recovered-20261017.json) now passes native and ordinary Windows HTTPS. No broker orders were
submitted; live remains OFF. Credential validation itself is unchanged.

The exact26-file source patch was separately approved/published as26a8d01 and
the exact two-file packaging repair as a4fccde. [Current CI](evidence/build-input-ci-20261017.json)
passes all4jobs/configured Sonar gate for a4fccde. Detailed identical-runtime
[prior artifact counts](evidence/flexible-credentials-ci-20261017.json) remain
825unit,392PostgreSQL,24browser,8TLS/WSS; combined1221tests/83.88% lines
(overlapping tiers). [Image build/runtime/ingress](evidence/flexible-credentials-image-review-20261017.json)
pass; [every build-context byte](evidence/postpublication-context-review-20261017.json)
reconciles to committed inputs without rewriting historical provenance.
The first current-source window was interrupted by a kernel restart. A fresh
boot-bound53a8ee46e318 window was stopped for a reproduced runner halt-check
gap. The fix passes24affected tests; a fresh smoke and24h remain pending,
without new acceptance credit before terminal verification. Full Paper lifecycle, permitted research and mapped cooling remain
separate incomplete Goal gates.
