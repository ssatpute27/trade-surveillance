# Trade Surveillance verification — October 20, 2026

The analyst workflow runs from the app or ChatGPT through the shared review service into the same versioned case database. ChatGPT prepares decisions; the human confirmation card submits them. Escalation creates an immutable PDF and manager delivery record. Evidence submission creates a follow-up revision while preserving the original record.

## Verified

| Boundary | Evidence |
|---|---|
| Automated suite | 115 tests passed. Coverage includes intake, retrieval, quantitative validation, notifications, escalation, manager workflow, source scope, and ChatGPT confirmation. |
| Actual card UI → MCP → database | An isolated browser host using the official MCP Apps AppBridge and a real stdio ClientSession rendered and submitted all three analyst actions. |
| Request more evidence | One human review, one new queued revision, one submitted document; original revision preserved. |
| Mark reviewed | Human review saved and case status became reviewed. |
| Escalate | PDF ready, one manager case, one delivery record pending. SMTP and workers disabled for this test. |
| Native ChatGPT rendering | Fresh Request more evidence card visibly rendered for CASE-0088C625 revision 12, including note and enabled Confirm decision button. Native chart viewer also rendered saved AAPL and AMZN charts. No live decision confirmed. |
| Read-only connector | Live assessment retrieval succeeded through the installed Trade Surveillance plugin, about 1.4 seconds for the measured call. This is one observation, not a latency guarantee. |
| Live API | Workspace, operations, policies, notifications, evaluation, investigation, history and report export returned HTTP 200 with valid JSON. |
| Live runtime database | SQLite quick_check returned ok. Latest cases: 101 ready for review, four held for manual review. |
| Source assets | 24 saved analysis artifacts passed content hash verification; AMZN audio endpoint matched its stored playback file. All eight policies indexed and PDF endpoints served PDF content. |
| Email configuration | Gmail SMTP authentication succeeded over verified TLS. No test email sent to a real inbox. Unit tests exercise accepted delivery, deduplication, blocked authentication and ambiguous delivery handling. |
| Human decision guards | Bad tokens, expiry, stale revisions, concurrent duplicate clicks, manager closure requirements and source lineage tested. Confirmation tool is app-only; its token is absent from model-visible output. |
| Analyst navigation | Live analyst review loaded 105 cases including manual holds; Standard review filter returned 14 cases. |
| Interview artifacts | 15-slide editable PPTX passed package/layout/font validation and first-party import. All slide renders and ten DOCX page renders visually reviewed. Copies in Downloads match source hashes. |

## Additional reliability checks

The dashboard review API now requires the exact run ID that the analyst inspected. An isolated HTTP regression test proves a stale revision receives 409 and creates no review; missing run IDs receive 422. Dashboard submissions lock while saving and preserve notes on connection failures. Escalation confirmation retries return the current PDF/delivery state. New cards include the same-case app link and explicit missing-token/expiry recovery messages. The final card version was rendered in native ChatGPT with its fallback link.

The read-only `scripts/demo_preflight.py` check passed against the running app, workers, policy index, database, saved analysis and private ChatGPT tunnel.

## Fixes during verification

- Added the documented ChatGPT compatibility template metadata alongside the standard MCP Apps resource URI; refreshed the installed plugin and restarted its private tunnel runtime.
- Strengthened plugin instructions to call the preparation tool for every new decision request and avoid claiming a card exists based only on conversation history.
- Returned an explicit structured confirmation result so the card displays the committed status (queued, reviewed or escalated).
- Replaced initial zero counters and provisional investigation statuses with loading placeholders until live workspace data arrives.
- Bundled exact permitted cited sources with the case assessment to reduce extra source round trips. Reading a case does not rerun the investigator.

## Fresh OpenAI investigation verification

Two fresh AMZN investigations ran in a separate runtime database, with SMTP and all delivery workers disabled. The first was correctly held for manual attention: a repair added a missing gap but rewrote a supported communication observation as an unsupported intent claim. The repair instructions were changed to preserve supported observations and modify only rejected statements or missing gaps. New runs use controls version `2026-10-agent-v8`; existing case records retain their original versions. The rerun completed 13 investigation tools, including policy search and hosted quantitative analysis, repaired a rejected first draft, and passed citation and independent support checks on its second attempt. It reached `ready_for_review` with a qualified concerning/escalate recommendation. Results are preserved in `tmp/live-agent-verification/result.json` and `result-after-repair.json`. This is one successful rerun, not a new population accuracy benchmark. No live case assessment was replaced.

The actual dashboard UI was also exercised against an isolated database on port 8769. Approving the NVDA negotiated-cross case moved it into Completed cases. The revised request included its inspected run ID. The test server was stopped afterward.

## Limits and remaining review

- The user's original failing conversation was not identified. A fresh native ChatGPT evidence-request card is verified; the precise cause in the earlier conversation is unconfirmed. Existing cards expire after 15 minutes; prepare a fresh card against the latest run.
- No live analyst decisions, manager escalations or real emails were created by these tests. Delivery acceptance does not establish inbox receipt.
- Workflow correctness does not establish model accuracy. The existing offline evaluation has 51/92 agreement with original scenario labels and 41 disagreements requiring adjudication. Exact-quote checks establish quote matching, not sound interpretation. Four cases correctly remain held for human attention.
- This is an interview demonstration with fictional private activity and authored policies. Production identity, role authorization, source entitlements, deployment resilience and compliance approval remain proposed work.
- The deck's customer ROI inputs are intentionally unfinished for the presenter to supply. No customer savings were invented.
- Localhost and the private tunnel require this computer and its services to remain running.

## Reproduce

Run `.venv/bin/python -m pytest -q` from the repository root. The disposable browser verification host and database are preserved under `tmp/ui-verification`; its server was stopped after testing. It never starts investigation or email workers. The live app is http://127.0.0.1:8767/population.html. Use `scripts/chatgpt_connection.py status` to inspect the private ChatGPT connection without exposing credentials.

Official metadata reference: https://developers.openai.com/plugins/reference

## Repeated viewer failure reported in Chrome — evening follow-up

The user reported host-level “Couldn’t display Trade Surveillance” failures even for fresh escalation proposals. Preparation succeeded and the resource request reached the server, but no live decision, packet or escalation email was created. A shared conversation omitted the widget diagnostics; the exact cause in that Chrome session remains unconfirmed.

The v4 viewer replaces the 605 KB bundled startup with a roughly 6 KB dependency-free standard MCP Apps bridge based on the official OpenAI quickstart. It validates the parent message source, uses bounded initialization and tool-call timeouts, and supports the documented legacy host bridge if standard initialization is rejected. Confirmation timeouts never automatically retry or switch transport. Three transport regression tests pass, along with 115 backend tests. The official AppBridge isolated browser harness rendered and confirmed an evidence follow-up and escalation through real stdio MCP; PDF generation completed with delivery disabled. Tool responses now explicitly state that the server cannot verify viewer visibility. Private confirmation tokens and app-only confirmation remain enforced. Native user-session resolution must be verified; another prepared proposal alone is not evidence that the reported failure is fixed.


## Rehearsal preparation and navigation update

The suite passes 119 tests, including an isolated reversible reset, a staged case remaining idle until explicitly released, duplicate delivery deduplication, preservation of prior evidence/reports, and exact-proposal validation for the native ChatGPT write tool. The native write path is implemented and deployed; its approval presentation in the user's Chrome account has not been reverified. The earlier embedded viewer remains unverified in that account.

The original live workflow, including the AMZN escalation and its sent delivery record, is preserved in `data/demo_backups/20261021T003206127731Z/agent.sqlite3`. The rehearsal runtime has 98 ready drafts, 4 manual holds and 3 staged investigations (AMZN closing activity, AAPL quote cancellations, NVDA documented order). There are no current analyst decisions, manager cases, escalation packets or outgoing email entries. Earlier reports, source evidence and artifacts remain available; this is a new rehearsal state, not deletion of the original audit. Starting a staged case through Live agent activity releases that exact revision into the existing live worker queue.

Sidebar labels now consistently use 14px/400 weight; the former last-child selector incorrectly treated count-free navigation labels as count badges. Case status filters separate awaiting review, escalated, approved, evidence, closed and investigation states. Default order is latest persisted case activity.


## Identity and trading-data realism review

All 24 trader identities and 40 account display names now use realistic fictional names. The source database was backed up under `data/identity_backups/20261021T003643Z`. Saved investigator evidence and immutable audit rows retain their original bytes; public historical records apply consistent identity aliases without modifying IDs, quantities, timestamps or hashes. New investigations use the updated source identities.

The read-only `scripts/check_data_realism.py` checks passed all 19 assertions on the current 40,000 orders, 150,000 executions and 30 securities, covering referential integrity, overfills, effective limit prices, acceptance/terminal timestamps, exchange sessions, historical daily high/low ranges, intraday volume reconciliation, broker minute-volume caps, funded positions and matched trade legs. Results are in `output/data_realism_check.json`. The complete Python suite passed 120 tests after these changes. These checks establish internal consistency, not independently calibrated production realism. Historical daily market context is sourced; private trading activity, identities, minute paths, communication content and alert thresholds remain authored/generated interview data.


## Written order conversations

370 parent orders linked to surveillance cases now each have a three-message authored desk chat, totaling 1,110 messages. All threads have named fictional participants, order IDs, chronological timestamps before order entry, account-scoped source records and explicit fictional provenance. Existing source records were retained, with a separate source backup under `data/chat_backups`. Each new thread has a matching content-hashed OpenAI embedding. The app Chat tab and ChatGPT communications reader show these records without silently revising saved assessments. The source reader excludes chats linked exclusively to other orders even on the same account. Additional account-context messages are grouped separately.

The Python suite passes 122 tests, including coverage of all 370 orders, thread scope and timestamps, and read-only retrieval without changing investigation snapshots. No investigation, analyst disposition or email was triggered by this addition.


## Concerning written communications

Four additional, explicitly fictional three-message conversations were added for closing-price activity (CASE-AF1D9C5F), spoofing/layering (CASE-0088C625), wash/self-trading (CASE-542714B9), and coordinated trading (CASE-1905FED2). They state concerning intent and attempted concealment in plain language. Existing routine threads, ambiguous calls, source evidence, reports and human decisions remain preserved. The new source texts are indexed with content-hashed embeddings and available to both app and ChatGPT. Scope tests verify these threads remain tied to the exact case orders and do not appear in the benign NVDA case; all three order-chat tests passed. Current assessments predate the addition and are labeled accordingly.


## Original audio before investigation

Original permitted recordings are now visible on Assessment and Sources before the current revision runs. Audio access uses the existing scoped, hash-verified range-capable endpoint; rendering the player invokes no transcription or agent calls. Transcript state is checked against the selected revision's snapshots, so earlier transcripts do not mark a staged revision as processed. Available-audio badges also appear on staged cases in the queue. ChatGPT's case overview includes original recording URLs and transcript status.

125 tests pass, including an original-audio GET/range request before any investigation exists, no run/snapshot/audit side effects, and revision-specific transcript status. The three staged AMZN/NVDA/AAPL cases returned HTTP 206 audio/mpeg responses with pending transcripts after deployment.


## ChatGPT recording player

A new read-only `play_case_recording` MCP tool returns a case-scoped original recording player. It checks cutoff, account scope, recording ID, file size and audio SHA-256 before returning bytes in widget-only metadata. Model-visible results contain metadata and a local recording URL fallback; they contain no base64 audio. The tool starts no model call, transcription, investigation, email or analyst decision.

The full suite passes 126 tests. The compiled player was exercised through a real stdio MCP session and the official MCP Apps AppBridge in the isolated browser host: the AMZN audio loaded with duration 9 seconds, readyState 4, no media error, and playback advanced with paused=false. End-to-end rendering in the user's Chrome ChatGPT plugin remains unverified because that browser connection was unavailable in this session. The previous decision-viewer rendering failure is not claimed resolved by this feature.


## Actual ChatGPT audio compatibility result

The previously unavailable Chrome session became accessible. The plugin tool list was refreshed and the player was tested in the user's actual ChatGPT conversation (`6ad816f0-018c-83ea-9eb6-d07cc1b126a3`). The player card rendered, but media loading failed for both data-URL and Blob sources. A final native MCP AudioContent delivery returned without rendering a playable audio control. No investigation, transcription, decision or email was initiated. The precise browser/platform media restriction was not established.

The experimental player and native-audio tool have been removed from the default MCP server; source and tests are retained under `tmp/chatgpt-audio-experiment` for future work. Original recordings remain playable in the analyst application, and case recording URLs/transcripts remain accessible through the existing ChatGPT case tools. Inline playback in ChatGPT is not claimed supported by this deployment.
# ChatGPT HTTPS recording playback verified

The earlier embedded-data playback failure was narrowed down in the actual Chrome ChatGPT conversation: both WAV and MP3 data URLs returned `MEDIA_ELEMENT_ERROR: Media load rejected by URL safety check`; an HTTPS audio control loaded successfully. This supersedes the earlier broad conclusion that embedded audio was unavailable.

Original recording playback now uses a dedicated, allowlisted HTTPS media origin and the read-only `play_case_recording` MCP tool. Only the six fictional demonstration recordings are hosted, at unlisted random paths; these are not authenticated or expiring URLs. The application, case database, policies, credentials and email configuration remain local. The tool checks case scope, cutoff, recording identity and original SHA-256; hosted URLs are passed in model-hidden metadata. Playback does not invoke investigation, transcription, analyst decisions or email.

In the existing Chrome ChatGPT conversation, CASE-AF1D9C5F rendered a nine-second player. Pressing its native Play control changed the control to Pause and displayed “Playing original recording”; the captured timeline advanced to 0:02 / 0:09. Screenshot: `output/demo/chatgpt-https-recording-player.png`. All six hosted files returned HTTP 200 and matched their original SHA-256; each case reported inline playback available. The full suite passed: 130 tests, including five new playback scope, URL/hash and read-only checks. Actual ChatGPT playback was exercised on the AMZN recording; the remaining five share the player and were verified at the HTTPS/file-integrity layer.



## Agents SDK execution migration

The current investigation workflow now executes through the OpenAI Agents SDK `Agent` and `Runner`. SDK function tools are enabled from per-run server state; direct callback validation also rejects premature or repeated tools. Required evidence, depth, citation, support, time and tool-budget checks remain enforced. A native SDK investigator selects tools, a structured report-writer agent drafts or repairs the report, and a separate structured reviewer assesses support. Agents cannot record analyst decisions or send escalation emails. Model responses are stored for native platform trace inspection. Supplementary Embeddings and hosted File Search/Code Interpreter API calls are nested under their investigation tool spans.

Live verification: CASE-AF1D9C5F revision 7, run `75b94f9a-6b4d-4c3a-a721-08e75d0e0bde`, completed in 59.04 seconds and reached `ready_for_review` with an escalation recommendation and zero analyst decisions. Fourteen tool invocations completed. The first report failed the existing missing-evidence citation check; one repair passed validation and independent support review. The existing review-ready notification was sent by the normal outbox worker. Earlier reports and the two existing escalations were preserved.

Verified in the signed-in platform account, Personal organization / Default project: https://platform.openai.com/logs/trace?trace_id=trace_65207458e6dc47f0922381803cf2acc8&api=traces . Native SDK task, turn, investigator, report-writer and support-reviewer spans appear. `search_communications` includes a real `OpenAI embeddings.create` span: `text-embedding-3-small`, 23 tokens, 754 ms. `policy_search` includes a model request whose output contains a completed `file_search_call` and retrieved `POL-marking_close.pdf` and `POL-size_outlier.pdf` excerpts. In this recorded trace it is labeled Generation; future calls have an additional explicit OpenAI File Search parent label. The transcription tool transparently reused the existing transcript cache.

The app's Investigation tab links to the trace for the selected revision and identifies native SDK execution only when its recorded start event carries that engine. Evidence screenshots: `output/demo/sdk-embeddings-trace.png`, `output/demo/sdk-file-search-trace.png`. Full machine-readable live summary: `output/traces/sdk_migration_verification.json`.

Migration validation completed: 142 tests passed. New SDK tests exercise the real Runner with a scripted Model, required-tool bypass rejection, tool budgets, unsupported-citation repair exhaustion, deadline enforcement and absence of analyst-decision tools. Tracing tests use an in-memory processor and confirm explicit hosted File Search span nesting. No unit test calls live model or email services.

Fresh visible-API verification: CASE-AF1D9C5F revision 8, run 782dc3e9-4e39-4c6d-979e-2c28fcae18e3, reached ready_for_review in 63.26 seconds with zero analyst decisions. Platform trace trace_47da0562961d4e8bbf50250721a2e422 visibly includes the explicit OpenAI File Search span (3568 ms) under policy_search, plus OpenAI Code Interpreter. The current case Investigation tab links to this revision-specific trace. Screenshot: output/demo/explicit-file-search-trace.png.
