# ChatGPT analyst integration

The implementation connects the real ChatGPT product to the existing local surveillance workflow using a private MCP server. Browser extension connectivity lets Codex assist with setup; it does not itself connect ChatGPT to the case database.

## Implemented locally

- `app/chatgpt_mcp.py`: MCP tools to find cases by stock/order/account/trader, read current or historical assessments, paginate full orders/fills, retrieve permitted evidence and exact cited sources, read communications/transcripts, policies, revision/review/manager history, saved measurements, and verified Code Interpreter charts.
- Read tools reuse case/account/cutoff controls. They do not start agent investigations, transcriptions, embedding requests, or email delivery. Denied source text and metadata are redacted; evaluation keys and credentials are not tools.
- `prepare_analyst_decision` displays an MCP Apps confirmation card containing the exact case, revision, disposition, rationale, supplied document, and escalation recipient/consequence. The case is unchanged until the analyst clicks.
- The confirmation token is returned only in UI metadata. The commit tool is app-only. Tokens expire after 15 minutes; server guards prevent stale revisions and duplicate submissions. This is a controlled local interview demo, without production multi-user identity or role authentication.
- `app/reviews.py` is the shared dashboard/ChatGPT review service. Escalation creates the existing manager case, PDF and email outbox. Evidence requests queue one child revision. Mark reviewed cannot bypass manager closure. The audit labels confirmed ChatGPT actions separately.
- Local media links still require the app on this computer. Charts can be returned inline through MCP. Recording transcripts and provenance are available as text; audio playback is available in the app. A saved chart is absent where no analysis was performed.

## Start and connect

Build the card with `npm ci --prefix chatgpt-ui` and `chatgpt-ui/node_modules/.bin/esbuild chatgpt-ui/decision.js --bundle --format=esm --minify --outfile=chatgpt-ui/dist/decision.js`.

Private stdio command: `/Users/ydesai/code/trade-surveillance/.venv/bin/python -m app.chatgpt_mcp`, working directory `/Users/ydesai/code/trade-surveillance`.

Use the official OpenAI Secure MCP Tunnel client. Associate the intended Personal Platform organization and ChatGPT workspace; runtime credentials need Tunnels Read + Use. Keep keys out of arguments, logs, source files and browser screenshots. The tunnel must remain healthy and polling for discovery and every call. Do not expose the existing dashboard publicly.

In ChatGPT Plugins, add a custom MCP server using Connection: Tunnel. Only after the local server and private tunnel are ready, create/install the plugin and verify a safe read call. Preserve per-action confirmations for writes. Connection is complete only when ChatGPT successfully retrieves a real case through the plugin; local tests alone do not establish a ChatGPT connection.

## Demo prompts

- Find the AMZN case for order O-0000253 and explain the concern, competing explanations and missing evidence. Cite the original sources.
- Show its communications, recording transcript and Code Interpreter chart. Explain what each supports and what it cannot establish.
- Compare the first and latest assessment for CASE-8D933B57. What evidence changed the conclusion?
- Prepare an escalation for this case with the rationale I provide, then let me confirm the decision.

Manager approvals, legal referrals and closure use the existing manager workflow. ChatGPT analyst tools cannot impersonate the manager or file external regulatory reports.

## Connection status

Connected and verified in the user's Personal ChatGPT workspace on October 19, 2026. ChatGPT retrieved CASE-AF1D9C5F revision 5, the linked O-0000253 AMZN order, and original supporting source records through the installed Trade Surveillance plugin. No analyst disposition or escalation was submitted during connection verification.

- Plugin: `plugin_asdk_app_6ad6e2c1bd708191865bf87facfa667a`
- Tunnel: `tunnel_6ad6e29487308191a3414d9d4ae5c3d8`
- Managed runtime alias: `trade-surveillance`; healthy/ready verified with the official client.
- Verification conversation: https://chatgpt.com/c/6ad6e2f1-3738-83e9-8344-d96d38d6b90f

Use `.venv/bin/python scripts/chatgpt_connection.py status`, `start`, or `doctor` from this project. `start` loads the existing local API key into the child environment, while the runtime config stores an environment reference. It does not print or store a literal key. The computer, local dashboard workers and private tunnel must be running for the complete workflow. After stopping or rebooting, use `start` to restore the private connection.

Official setup: https://developers.openai.com/api/docs/guides/secure-mcp-tunnels
