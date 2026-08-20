# Expenses and bank sync

The Expenses tab is a user-scoped cashflow dashboard. It groups transactions into
stable categories such as housing, groceries, restaurants, car fuel, car
maintenance, transport, health, personal care, subscriptions, travel, gifts,
donations, pets, work, bank fees, taxes, investments, transfers, and income.

## Current data flow

The dashboard has three layers:

1. `ExpenseTransaction` stores normalised transactions with `(user_id,
   provider, external_id)` deduplication.
2. `POST /api/expenses/import` is the provider adapter boundary. A future bank
   worker can send raw PSD2 transactions here; the server normalises amounts,
   dates, categories, and merchant names before persisting them.
3. `GET /api/expenses/stream` is an authenticated Server-Sent Events channel.
   A connected dashboard reloads its summary as soon as an import completes,
   while also polling every 30 seconds when the user opens the view.

The application does not currently pretend that a bank account is connected.
Until a consented provider adapter is configured, the tab shows an empty state.

## Bank API option

For a Portugal/EEA deployment, GoCardless Bank Account Data (formerly Nordigen)
is the first provider boundary to implement. Its official documentation says
the account-information API covers EEA PSD2 banks and can expose balances and
transactions, with up to 24 months of history where the bank supports it. It
also documents bank-controlled rate limits and commonly up to 90 days of
continuous access before consent renewal.

This is not a guaranteed per-card-swipe real-time stream. The bank controls when
transactions become visible, and providers can enforce rate limits. The robust
design is: consent link -> provider access token -> scheduled incremental
transaction fetch -> idempotent import -> SSE update to the open dashboard.

The provider credentials and refresh tokens must be stored encrypted and scoped
to the user. Do not put a personal bank password in `.env`, the database, or a
browser form.

## Import contract

The current adapter boundary accepts common PSD2 fields:

```json
{
  "provider": "gocardless",
  "account_name": "Main account",
  "transactions": [
    {
      "transactionId": "bank-transaction-id",
      "transactionAmount": {"amount": "-42.50", "currency": "EUR"},
      "bookingDate": "2026-08-20",
      "debtorName": "Example supermarket",
      "remittanceInformationUnstructured": "Weekly shop"
    }
  ]
}
```

Negative amounts are treated as expenses by default; providers can explicitly
send `direction` as `debit`, `credit`, or `transfer`. Replaying the same
provider transaction ID updates the existing row rather than creating a
duplicate.

