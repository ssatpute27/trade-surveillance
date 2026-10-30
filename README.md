# AI Trade Surveillance Investigation

For the architecture, data flow, agent internals, integrations and operations, see the [App build guide](docs/BUILD_GUIDE.md). The separate [Demo guide](docs/DEMO_GUIDE.md) covers presentation and walkthrough notes.

A working local analyst application backed by a live OpenAI investigation agent. Existing surveillance rules produce alerts; the agent investigates grouped cases automatically, prepares a cited draft, and notifies the analyst. Analysts alone escalate, request more evidence, or mark a case reviewed.

The source population contains 40,000 parent orders, 150,000 executions, 141 rule alerts and 105 grouped cases across eight alert types. Real stock symbols and sourced daily market data provide public context. Private orders, communications, participants, intraday paths, order books, and bank policies are synthetic.

## Start the application

If this workspace is already configured:

```sh
.venv/bin/uvicorn app.server:app --host 127.0.0.1 --port 8767
```

Open [the analyst workspace](http://127.0.0.1:8767/population.html). Use the FastAPI service above rather than a static file server. Alert intake persists jobs; four bounded workers process them without an analyst Investigate click. The initial pilot feed can be expanded with **Start full alert feed**. Once enabled, intake remains enabled across restarts.

## Fresh local setup

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
# Only create a new configuration if one does not already exist.
test -e .env || cp .env.example .env
.venv/bin/python -m scripts.build_population
```

Set `OPENAI_API_KEY` in the local `.env`, then initialize the retrieval indexes:

```sh
.venv/bin/python -m app.indexes
.venv/bin/uvicorn app.server:app --host 127.0.0.1 --port 8767
```

Indexing and live investigations use paid OpenAI calls. The selected model is `gpt-4.1`; communication retrieval uses `text-embedding-3-small`. Index setup reuses unchanged content. It uploads the eight policy PDFs from `output/pdf` when present, with the corresponding written Markdown policies as a fallback on a fresh checkout without rendered PDFs. Hosted File Search returns the exact consulted excerpts and file IDs. Communications are embedded separately, then filtered by authorized account scope and availability cutoff before semantic/hybrid search.

The reviewed PDF copies are also saved in `/Users/ydesai/Downloads/Trade_Surveillance_Policies`. Their editable sources are in `docs/surveillance_policies`.

## Investigation and review

The OpenAI Agents SDK executes the workflow using `Agent` and `Runner`. The Trade Surveillance Investigator selects and invokes state-gated SDK function tools; the Surveillance Report Writer produces a structured `Report`; the Evidence Support Reviewer independently checks its support using a structured `GroundingVerdict`. The application enforces mandatory checks, exact citations, depth, deadlines and tool budgets around these agents. The SDK agents have no analyst-decision or email-sending tools.

Set `OPENAI_TRACING_ENABLED=true` to export new investigations to OpenAI Platform. The current demo has this enabled. Each traced revision has an **Open in OpenAI Platform** link at the top of its **Investigation** tab. SDK model responses are stored for native trace inspection; the trace contains fictional case evidence, tool inputs/outputs and validation activity. Cached transcripts are labeled as reused, rather than presented as a new transcription call. Earlier custom-loop investigations remain preserved in History and are not relabeled as SDK runs. Unit tests disable live tracing and use an in-memory processor for tracing checks.

Every case must check trades, a historical baseline, order authority, public market context, live historical news search, and applicable policy. Initial assessments are preserved before additional leads are pursued. Relevant signal families add checks such as order-book activity, customer access, account ownership, communications, and restrictions. Pre-announcement cases must inspect access/relationship records. Mandatory rules enforce promotion to deep investigation for complex cases or material gaps.

The investigator requests one tool action per turn, so each next choice can use the prior result. Fixed source extracts are not re-fetched as if a differently worded query broadened their scope. Final reports use Structured Outputs, exact excerpt validation, calibrated assessment/recommendation checks, and a separate model support review. A failed check gets one repair attempt. Exhausted budgets, unavailable sources, and failed validation preserve evidence and route to human attention; no report or disposition is fabricated. Exact quotes and a model support check are not proof of factual correctness.

The case drawer includes Assessment, Investigation, Trading, Sources and History. Citation buttons open the actual retrieved source. Human review notes persist separately from model suggestions. Requesting more evidence creates a new revision atomically and keeps previous reports, audit events and evidence available. A case record can be downloaded as JSON.

## Email notifications

Use **Email setup** to enter the sender's Google app password locally. Do not put credentials in chat. SMTP settings are server-side only, persisted in the ignored `.env` with mode 0600. Gmail uses STARTTLS with certificate verification and a bundled CA trust store.

Validated drafts create a unique transactional outbox entry. Missing authentication blocks sending. Authentication errors wait for a configuration change; transient failures before submission have at most three attempts. An ambiguous submission is held as `delivery_unknown` to avoid blind duplicate sends. `sent` means SMTP accepted the message, not verified inbox delivery. Each notification identifies the synthetic draft case and links to the local workspace. Local review links work on the computer running the app.

## Show the agent working live

Open **Live agent activity** to see running cases, the current evidence check, concise tool purposes, retrieved-source counts, initial assessments, depth changes and report handoff. These values come from persisted events, not a staged progress animation.

For a repeatable demonstration, choose **Documented large order**, **Pre-announcement activity**, or **Missing evidence**, then click **Deliver demo alert**. This simulates an upstream delivery. The worker starts automatically using live OpenAI APIs, and **Open live investigation** follows its actual tool activity. A new delivery preserves previous case revisions; duplicate event IDs do not duplicate jobs. A delivery for an already queued/running case attaches to that active investigation. Demo deliveries are prioritized when a worker becomes free. Normal alert intake continues independently.

A completed draft still needs analyst review. Failed validation appears as human attention instead of a fabricated report. Demo deliveries can send real review notifications when email is configured.

## Five-minute walkthrough

1. Open the queue and inspect the eight alert families. Operational KPIs show workload and analyst decisions.
2. Open `CASE-52074E40` for a documented large-order case. Compare its lightweight initial assessment, mandate, and final cited draft.
3. Open `CASE-4A3C38E5` for deeper pre-announcement review. Inspect communications, access records, promotion, alternatives, and evidence gaps.
4. Open `CASE-51CDC1FB` to examine incomplete evidence and its preserved validation/review history. Live model outcomes may vary; the app displays the actual result.
5. Open **Policy library** to read the documents available to File Search. Open **Evaluation & audit** to inspect measured outcomes, denominators, held runs and limitations. Analyst decisions require a review note; they are never populated by the model.

## Tests and evaluation

```sh
.venv/bin/python -m pytest -q
.venv/bin/python -m scripts.evaluate_agent
```

Evaluation writes `evals/latest_results.json` and is also available in the app. It measures required checks, exact citation matching, independent support review, retrieval of authored key evidence, scenario-label agreement, latency and held runs. Grading keys in `evals/population_truth.json` are never available to agent tools or the static server. Scenario agreement is a synthetic benchmark, not production accuracy or a legal conclusion.

## Recorded backup

Archive completed real runs:

```sh
.venv/bin/python -m app.replay
```

Open **Recorded cases** for the labeled replay surface. Original evidence, timestamps, recommendations and audit activity are preserved. Replay performs no new OpenAI calls, creates no human decisions and sends no emails. SHA-256 checks detect accidental archive modifications. This local archive is not an immutable production records system.

## Persistence and reproducibility

- `data/population.sqlite3`: read-only source population used by investigation tools.
- `data/agent.sqlite3`: durable run queue, evidence snapshots, retrieval indexes, human decisions and email outbox.
- `data/replays`: recorded live-run backup.
- `docs/POPULATION.md` and `docs/DATA_MODEL.md`: source design, measured counts and limitations.
- `docs/AGENT_RUNTIME.md`: operational details.

`python -m scripts.render_workspace` regenerates the static source fallback without changing runtime reports. `python -m scripts.build_population --replace` regenerates the owned synthetic source using the cached market snapshot; back up your databases before intentionally starting a new scenario set. To start a separate runtime without deleting earlier work, set `RUNTIME_PATH` to a new SQLite path and initialize its indexes.

A generator correction aligns mandate-summary execution windows with the authoritative mandate table. `scripts/repair_mandate_windows.py` applies that correction idempotently and preserves original text/hashes in source repair records; earlier investigation snapshots remain unchanged.

This is a loopback-only single-user demonstration, without production identity, organization-level permissions, HA workers or regulatory record retention. Source availability controls and audit behavior are exercised locally. The older `app/store.py`, `app/fixtures.py` and small `sample/review.html` are inactive early scaffolding.

The real ChatGPT analyst experience now connects to the same workflow through a private MCP tunnel. It retrieves case assessments, trades, permitted evidence, communications/transcripts, policies, history and saved charts. Analyst decisions use an inline confirmation card and the same backend as the dashboard. See `docs/PHASE_2_CHATGPT_OPTIONS.md` for access limits, connection status and operation.

### Additional investigation tools and call evidence

New investigations reconstruct a chronological timeline and retrieve earlier case comparisons. The Trading tab shows the retrieved timeline. Sources includes shortcuts to timeline evidence, historical comparisons and recorded calls. Authored historical examples are clearly labeled fictional and kept separate from actual analyst decisions.

Six demonstration samples now have AI-generated audio re-enactments of existing synthetic evidence. When investigating these samples the agent calls the OpenAI Audio Transcriptions API (`whisper-1`) and retains playable audio, segment timestamps, content hashes and request provenance. Transcripts are embedded for semantic search alongside messages. Repeated investigations reuse a hash-checked transcript cache, with reuse explicitly recorded in the audit. Re-enactments are derived evidence, not independent corroboration. Existing reports are preserved; use a fresh incoming demo alert to exercise the new tools.

Asset preparation: `.venv/bin/python -m scripts.prepare_investigation_archive`. Configure `TRANSCRIPTION_MODEL=whisper-1` and `MAX_TOOL_CALLS=24` (defaults). OpenAI TTS generates the clearly labeled demo voice; transcription is performed by an actual API call during investigation, never copied from the authored script. No production audio ingestion integration is included.

The Apple screenshot now renders a separate fictional written exchange (`CHAT-DESK-CASE-0088C625`) about displayed buying interest and sell execution priorities. Its wording differs from the audio, which retains the original `CHAT-FLAG-CASE-0088C625` dialogue and provenance. Both are authored demo evidence, not independent real-world corroboration. Fresh source generation includes the new desk exchange; existing populations can add it with `python -m scripts.add_apple_desk_chat`, then render with `python -m scripts.build_image_evidence`. Earlier image artifacts remain available for historical citations while current previews use the new desk conversation.


To select an audio demo, open **Analyst review → All evidence → With recorded calls**. The filter lists only cases whose latest investigation actually retrieved a transcript. Case rows also carry a Recorded call label.

| Case | Demonstration |
|---|---|
| CASE-AF1D9C5F | Main demo: closing-price activity, valuation-related dialogue and late-day AMZN buying |
| CASE-4A3C38E5 | Ambiguous pre-announcement conversation; distinguish a lead from proof |
| CASE-52074E40 | Large NVDA order and a signed mandate |
| CASE-51CDC1FB | Innocuous office-seating explanation for ambiguous wording; other gaps remain |
| CASE-E6272323 | Recorded instruction mentioning a disclosed principal hedge and risk approval; verify the applicable exception |
| CASE-0088C625 | Quote withdrawal tied to inventory hedging; verify the full order sequence and authority |

Open a case, choose Sources, then Recorded call. All six use Marin. The new customer-hedge and quote-cancellation samples are also selectable in the incoming-alert controls. Their dialogue paraphrases the linked source records and must not be treated as independent corroboration.


**Additional main demo — End-of-day valuation (CASE-AF1D9C5F).** In Live agent activity, choose “End-of-day valuation · Main demo” to send a fresh event. The underlying case includes a 3:40 p.m. Eastern message about the valuation and concentrating buys near the close, followed by AMZN order activity starting at 3:55 p.m. The agent must examine the actual executions, earlier size baseline, mandate/benchmark rationale, strategy records and closing-price policy. It must not infer intent or causal price impact from timing alone. The Marin call re-enacts E-000085 and is not independent corroboration of that message. The case's final recommendation comes from the live investigation, not a hard-coded demo outcome.

Suggested walkthrough for CASE-AF1D9C5F: play the recorded call in Sources; open Trading to compare its 3:40 p.m. time with the 3:55–3:59 executions; open Investigation to show baseline, policy, authority and strategy checks; then read Assessment and its citations before recording an analyst decision. Describe price-influence intent as a hypothesis to investigate, rather than an established fact. The latest report and its recommendation are generated from the retrieved evidence.

### Hosted quantitative analysis

New closing-price, spoofing/layering and front-running investigations call **OpenAI Code Interpreter** to compute execution patterns and generate a chart. Other case families can use it when relevant. This is a real hosted Python execution through Responses, rather than a locally plotted stand-in.

Open **Trading** to see the execution chart, checked measurements and timeline together. **Sources → Execution chart** opens its evidence and offers the chart, calculations and scoped source extract. **Investigation** retains the actual hosted execution and validation trace. Numeric outputs are independently recomputed before entering a report; chart pixels still require analyst review. Percentages are explicitly scoped to case shares and supplied venue orders. The generated artifacts are saved locally with case/revision access checks and content hashes, so opening a saved report does not require an active OpenAI container.

The default investigation deadline is now 360 seconds. Hosted analysis adds token and container charges. Existing case revisions are preserved and do not acquire a chart retroactively.

### Demonstrate evidence changing an investigation

- Open CASE-8D933B57 → Assessment. Its preserved initial view is inconclusive; after cross-approval evidence is retrieved, its final draft is plausibly benign / standard review. Assessment journey displays both with citations.
- Open CASE-9732738F → Assessment. Revision 1 lacked authority evidence. Revision 2 receives a clearly fictional mandate extract and narrows the remaining gap to authentication; the agent correctly retains an inconclusive recommendation. History preserves the request as Demo workflow verification, not an actual analyst disposition.
- For a follow-up, expand Add supporting document for a new investigation under Your review. Enter a title, source reference and excerpt, add your question, then use Request more evidence. The agent checks the submitted source in the new revision. An excerpt is not independently authenticated.
- Evaluation & audit → Review original-label disagreements shows cases requiring inspection. The original baseline is preserved in evals/quality_baseline_v5.json; detailed review is in docs/QUALITY_REVIEW.md. Do not present scenario-label agreement as production accuracy.

The example follow-up payload is saved at output/demo/followup-evidence-example.json. Desk-owner evidence routing is not yet connected; manager escalation email is supported as described below.

### Escalate with a PDF summary

Enter your rationale under Your review, optionally inspect Preview escalation PDF, then choose Escalate. The app records your decision, generates the cited case summary and emails the PDF to `SURVEILLANCE_MANAGER_EMAIL`. Assessment shows the download and delivery status under Surveillance manager handoff; the case appears in Escalations. The current demo manager address is sheenadesai27@gmail.com, using the existing sender configuration. The agent recommendation remains separate from your decision.

A PDF or email failure does not discard the escalation. PDF generation can be retried without another analyst action. Uncertain email submissions pause for a Sent-folder check to prevent duplicate sends. The preview never records a decision or sends mail.

### Manager review

After Escalate, open Escalations → Open manager review, or use the Manager review tab on the case. The local demo manager can record an evidence request with a responsible owner, assign a deeper investigation, approve closure with a reason, or record a referral to Compliance investigations or Legal. Ownership, workflow status and immutable manager history remain visible.

Evidence requests waits for a submitted document; it does not keep rerunning. Add the requested source under Assessment → Your review to start one follow-up. Completed assigned investigations return to Analyst review; the analyst then chooses Return to manager. Supervisory closure appears under Completed cases. Referrals currently record a local handoff, without external dispatch.

### Before a demo

Run `.venv/bin/python scripts/demo_preflight.py` to check the running app, workers, policy index, database, analysis files and private ChatGPT connection. This does not trigger investigations, decisions or emails. Refresh the browser after updating the app; analyst submissions are bound to the case revision being reviewed.


### Staged interview demo

The rehearsal queue retains 98 assessed drafts and four manual holds. Three new revisions await investigation: AMZN `CASE-AF1D9C5F`, AAPL `CASE-0088C625`, and NVDA `CASE-52074E40`. Open **Live agent activity**, choose **End-of-day valuation · Main demo**, **Quote cancellation rationale**, or **Documented large order**, and select **Start investigation**. This releases the staged revision to the live agent; subsequent report-ready notifications use the configured real email delivery. No new investigation begins until an alert is released. Prior reports remain in case History.

Use the Alert queue's **Case status** filter for awaiting investigation, awaiting review, escalated, approved, awaiting evidence, or closed cases. Lists default to newest case activity first.

The pre-rehearsal runtime, including actual analyst actions and sent-email records, is archived at `data/demo_backups/20261021T003206127731Z/agent.sqlite3`. Restoring requires stopping the app and private MCP runtime before replacing the runtime from that SQLite backup; preserve the current runtime with SQLite backup first. Prepared PDF/audio/chart files remain in their original artifact directories. The reset does not recall previously sent messages.

To repeat preparation, first finish active runs and stop both services, then run `.venv/bin/python scripts/prepare_demo.py --services-stopped`. Each preparation creates a separate complete runtime backup before making a new rehearsal state.


### Order-linked written communications

Each of the 370 orders linked to the 105 surveillance cases has a fictional three-message desk conversation (1,110 messages). Fills share the parent order's thread. Open a case's **Chat** tab to see participants, timestamps and order references; additional account-context communications are collapsed separately. ChatGPT can retrieve the same records with `read_case_section(section="communications")`, and their content is embedded for future agent searches. Existing assessments are not rewritten when source conversations are added; records not retrieved in the saved assessment are labeled accordingly. Original sourced communications, recordings, transcripts, audits and decisions remain intact. Chats supplement the dataset and do not establish approval or intent. Recreate missing threads with `.venv/bin/python scripts/add_order_chats.py`, then refresh communication embeddings.

## Live historical news search

`search_market_news` calls OpenAI hosted Web Search through the Responses API for the case tickers and a publication window from seven days before the linked trading through the original cutoff. Public tickers and dates are sent to search; private case identifiers, accounts, communications and analyst notes are excluded. Daily market bars remain a separate tool. Stored scenario news summaries are no longer returned by `market_context` as external news.

Search runs afresh during each new investigation. A second structured extraction retains dated findings attributed to actual citation URLs; code rejects out-of-window dates, post-cutoff exact times, invalid dates and invented URLs. Dates remain source-reported rather than independently verified. Unknown same-day publication times cannot establish pre-trade availability, and empty results do not prove absence of news. Search summaries are labeled as model-generated, not verbatim articles. Sources are clickable in Evidence and accessible through ChatGPT’s existing sources tools; OpenAI Platform traces include an explicit OpenAI Web Search span. Saved assessments and human decisions are preserved and do not retroactively acquire new news findings.

### Image evidence demo

The Apple spoofing case (`CASE-0088C625`) and NVIDIA size-outlier case
(`CASE-52074E40`) include an **Image evidence** tab. These clearly labeled
synthetic images render existing fictional communications and instruction records;
they are derived views of the same evidence, not independent corroboration.

OpenAI Responses API vision reads the actual PNG pixels (`input_image`,
`store=False`). The app checks extracted quotes against the paired record and
caches verified readings locally. The viewer shows reading limits, source IDs and
whether an image reading was retrieved in the selected investigation. Existing
saved assessments are preserved. New investigations require the image review tool
when eligible images are attached. Image access reapplies case scope and source
availability and checks the file hash. Rebuild demo PNGs with
`.venv/bin/python -m scripts.build_image_evidence`.
