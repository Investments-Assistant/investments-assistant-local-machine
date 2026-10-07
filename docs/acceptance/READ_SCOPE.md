# Explicit user read exclusions

The local GGUF client applies `read_scope.py` before deterministic factual reads,
while constructing the native tool catalog, and independently immediately before
dispatch. Native tool calls must also belong to the server-selected catalog;
hallucinating a tool name does not expand it. The degraded local client uses the
same guard. Existing authenticated ownership, execution approvals and mandates
remain separate, mandatory boundaries.

The reproduced request "Do not access my portfolio. Show stored news only." now
selects stored news without portfolio/account/history access. Portfolio exclusions
also block report generation and proposals that could collect account data.
News/market/report/simulation exclusions narrow their corresponding tools.
Original user messages provide these restrictions; tool and assistant evidence
cannot clear them. Follow-ups in the supplied conversation history retain them.
Supported explicit user phrases such as "You may access my portfolio" clear that
scope exclusion but do not grant any account capability or trading authorization.

This is a conservative supported-phrase parser, not general natural-language
understanding. Ambiguous negative clauses exclude their named scopes. English
and selected Portuguese negation/scope phrases are tested; full multilingual
coverage is incomplete. Restrictions are based on available conversation history,
not a durable account preference independent of history retention/truncation.
Other runtime clients and direct user HTTP/MCP tool requests do not derive intent
from this local-client helper; their existing authentication/capability checks
remain in force. No gate is promoted to full NLP correctness based on these tests.

Evidence: `workflow-negation-reproduction.json` records the original offline
failure; `read-scope-fixed.txt` records24 targeted passing tests before the native
stream regression was added. The native-stream test deliberately emits a forbidden
portfolio call despite its absence from the catalog and asserts no dispatch occurs.
No test connects to a broker or loads an external model.

Final scope validation:576 unit/PostgreSQL tests PASS in
`evidence/suite-read-scope-recovered.txt`, including the native stream guard.
The intervening failure log records a stopped disposable database and an invalid
64-token test setting; restored fixture and128-token setting are verified.

The adjacent native evidence path now preserves the full tool-result event and
uses valid omission JSON only for oversized model context.26 affected workflow,
scope and evidence tests PASS (`evidence/native-evidence-budget.txt`). This avoids
character-truncated JSON without pretending the model saw omitted evidence.


Explicit read refreshes now reuse the nearest user request: "Refresh that",
"Check again", "Atualiza isso" (and documented parser variants) collect fresh
source evidence instead of treating the previous answer as current. Assistant/tool
text never selects that scope; an intervening user topic stops inheritance, and
prior buy/sell/approval/mode/mandate actions cannot be repeated. This resolver is
used only for factual read routing/catalogs, never report/simulation/order requests.
Original-history exclusions still apply independently at dispatch. These limited
refresh phrases do not claim general pronoun or multilingual understanding.
Combined portfolio/news requests classify news independently; holdings, positions,
carteira and posições no longer suppress it.40focusedtests and11stream/edge tests
pass (read-followup-fixed.txt and read-followup-stream.txt); realmodel run pending.

The known excluded-scope follow-up now explains the original user restriction
before model inference, including native and degraded modes. It suggests an explicit
read-preference phrase without granting trading or account authority. Independent
permitted reads still run. Assistant/tool text cannot clear the restriction.
read-exclusion-answer-fixed.txt37PASS and native guard followup17PASS validate this;
workflow-exclusion-answer-cpu-20261006.json8/8 real-app cases pass a new answer-content
check, not just scope/events. The response is deterministic, not model synthesis.
