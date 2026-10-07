# Financial chat evidence boundary

The observed1.5B Portuguese answer inventedEUR4.00 for0.004 units atEUR100.
`workflow-scope-v2-review.json` preserves the failure. Merely acquiring the right
tools did not make the generated financial prose correct.

`src/finance/answers.py` now renders source-reported portfolio facts using exact
Decimal/string values. It never derives a total from an unqualified symbol/price,
invents FX, or treats a missing value as zero. Source currency and unavailable
as-of fields are explicit. Only selected financial fields are rendered; provider
errors are counted without copying potentially sensitive exception text. Source
valuation status is preserved, not upgraded to reconciled/accounting authority.

Default factual portfolio requests collect scoped evidence and render it directly.
Combined scanner requests retain their independently requested news/market results.
Native-tool mode retains model tool selection, but any portfolio answer is replaced
by the same exact evidence representation after tool collection; a model claim
cannot override it. Final events identify deterministic_financial_evidence.
Twenty displayed positions bound answer size; omitted count and retained full tool
event expose that limitation. Other oversized evidence is represented by valid
structured omission status. This is source evidence, not proof of a trade/fill.

This deliberately establishes reliable factual output, not completed qualitative
portfolio analysis. A validated model-analysis schema, broader language/ambiguity
coverage, complete external accounting and advice quality remain incomplete. Do
not count bypassed inference latency as a model-synthesis benchmark improvement.

Evidence:30 initial affected tests PASS (financial-answers.txt), then582 aggregate
unit/PostgreSQL tests PASS (suite-financial-answers.txt), including native-model
counterexample and Portuguese catalog selection. Tests use synthetic tool sources.


Simulation answers also require complete numeric evidence before claiming completion.
`finance/simulation_answer.py` renders the reported base currency, rejects unavailable/
malformed results instead of substituting zero returns, and keeps persistence failure
visible. Ambiguous company names/pronouns do not become guessed uppercase symbols.
An explicit exchange constraint requires confirmation of the historical-data provider
symbol; the parser cannot silently discard that constraint or guess a suffix. The
SPYL/Xetra request remains an instrument/proposal fixture, never authority to trade.
Unrelated portfolio/news reads continue through the existing scoped boundary while
clarification is requested. This is a supported deterministic parser, not proof of
general natural-language instrument resolution. Explicit provider tickers such as
SPYL.DE remain usable for research; execution still requires broker qualification.

## Descriptive portfolio review (2026-10-07)
A readable English/Portuguese review now precedes exact evidence. It explains
missing valuations/timestamps, source failures, omitted positions and mixed
currencies. Complete displayed holdings with unique source conIds, known internal
account/currency, nonnegative quantities/values and comparable aware timestamps
can show their largest position weight within each separate account/currency group.
Decimal128 arithmetic rounds the displayed percentage to two decimals; values and
denominators remain explicit. Cash, other currencies/accounts and fund look-through
are excluded. Missing, duplicate, nonfinite, extreme, zero-total, inconsistent,
short, cross-time or omitted evidence prevents percentages. A source weight is not
a verified current valuation, risk limit, suitability finding or trading authority.
The review is deterministic; no unchecked model arithmetic or investment forecast
was added. More general model commentary remains independently constrained.
portfolio-review-reproduction.txt5FAIL before, portfolio-review-guards.txt28PASS,
workflow-portfolio-review-cpu-20261007.json9/9 scope/event/content checks pass.
The benchmark now checks answer content (known80%/100EUR denominator, cash and
look-through limitations, preserved0.004/unknown values), not only nonempty events.

Combined portfolio/scanner requests now append validated news assessment instead
of allowing portfolio rendering to bypass it. Exact portfolio facts and the
readable review remain deterministic; source quotations are selected in a separate
tool-free structured inference call. Market evidence remains independent. Final
events distinguish financial evidence with validated news from facts-only output.
Headlines or unavailable sources still produce explicit abstention; recognized
source commands cannot become selected observations. Full tool events retain the
original evidence. The same bounded candidate selection is used by report prompts.
