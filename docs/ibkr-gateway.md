# IBKR read-only setup

Start with the [step-by-step prerequisite guide](acceptance/PREREQUISITES.md).
Use a separately verified Paper session and the authenticated application's
Brokerage Accounts form for explicit owner/account selection and encrypted
account-identifier storage. Global `.env` broker values do not authorize reads.

Keep Read-Only API and localhost-only restrictions enabled. A port number alone
does not identify a Paper account. The existing adapter uses `readonly=True`,
checks the selected actual managed account, and keeps all submit/cancel paths
closed. See [capabilities and evidence limits](acceptance/BROKER_CAPABILITIES.md).

Windows TWS and WSL NAT are separate network contexts: `127.0.0.1` inside WSL
does not establish access to Windows localhost. Do not relax firewall/trusted-IP
rules or disable localhost-only protection to make a connection work. A new
connection helper must be reviewed and tested separately before use.

Any private operator-validation database/files must be separate from the
synthetic-only acceptance cluster. Keep keys, account identifiers and private
responses out of Git and public evidence. TLS trust changes, actual Paper
submissions/observation, and production deployment retain their separate approval
requirements; this guide grants none of them. Live trading remains OFF.
