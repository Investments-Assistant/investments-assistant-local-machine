# Local chat/scanner acceptance review

Original L06: portfolio and scanner workflows acquire scoped evidence under default
settings; parsing, follow-up, injection and tool-error cases pass. The scope below
is the configured local GGUF runtime and deterministic controls. It does not claim
universal natural-language understanding, arbitrary investment advice, or economic edge.

| Condition | Implementation and direct evidence |
|---|---|
| Portfolio/default scanner acquire authorized sources | `_factual_requests`, default prefetch, dispatch scope guard; `acceptance_workflows_test.py`; actual app workflow benchmark9/9 and combined substantive scanner benchmarks |
| Independent requests and follow-ups | `read_request` reuses nearest user read only; no assistant/tool authority, no action replay, intervening topic boundary; `read_followup_test.py`, actual refresh and scoped-news cases |
| Negation/restrictions and supported language | `read_scope_test.py`, `read_exclusion_answer_test.py`; English/Portuguese source scopes; meaningful retained-restriction explanation without inference; exact source values and Portuguese review |
| Ambiguous instrument/exchange handling | `simulation_clarification_test.py`: clarification instead of guessed company/pronoun/listing; independent safe reads continue; explicit provider symbol still usable; no SPYL/Xetra order implied |
| Useful portfolio interpretation | `portfolio_review_test.py`, exact facts and account/currency/source identity/time guards; exposure denominator and cash/look-through limitations; actual9/9 content checks in workflow-portfolio-review-cpu-20261007.json |
| Useful news/scanner analysis | `scanner_analysis_test.py`, exact eligible source quotations, source links, mandatory evidence gaps and bounded abstention; actual default scanner and scoped-news checks in workflow-scanner-candidates-cpu-20261007.json; native scanner passes same content checks |
| Tool errors/incomplete evidence | `news_analysis_test.py`, `read_followup_test.py`, `simulation_clarification_test.py`: no fabricated totals/zero-success, unavailable sources distinct from empty sources, typed bounded retries, truncated inference rejected |
| Injection/authority | Original tool events retain source text; structured inference is tool-free; commands cannot grant capabilities. AUTHORITY_REVIEW.md covers independent execution policy. Selected quotations must be eligible exact source sentences, preserving qualifications; recognized directives are excluded as a quality measure |
| Native/default comparison | Native scanner38.508s via deterministic recovery versus default10.976s; both keep scopes and source facts. Existing default stays selected. No p95/production workload claim from these small samples |
| Event/persistence compatibility | Tool-call/result/final/done regression cases, native recovery, durable chat/browser retention/isolation; browser-scanner-history-final.txt passes all retained end-to-end flows with model/provider fixtures explicit |

Full current regression result must be checked separately before promoting the gate.
Benchmark failure history is retained, including safe-but-unhelpful abstention and
an earlier nominal report PASS rejected by manual review for selecting a source
command. Final report and scanner tests require meaningful factual selection.
The supported-source extractor is deliberately bounded and conservative; unresolved
entities, forecasts, full accounting, real provider freshness, external execution,
model economic edge and target-host soak remain separately gated. No model analysis
can substitute for an account mandate, trusted price/FX, independent approval or
reconciled fills. Real broker/bank access was not exercised.
