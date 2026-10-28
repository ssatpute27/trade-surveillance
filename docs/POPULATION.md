# Full trading population

Generate with `.venv/bin/python -m scripts.build_population`. Rebuild the generator-owned outputs with `--replace`. No external API calls, model calls or credentials are used during population generation; the public daily history is read from the existing cache.

## Outputs

- `data/population.sqlite3`: local source database; excluded from Git. This is separate from the inactive agent scaffolding database.
- `sample/population.html`: analyst workspace, served at the existing local preview address with `/population.html`. This read-only stage shows open alerts, filters, rule observations, linked orders and preliminary source evidence. Data-generation counts and checks stay in the manifest, not product KPIs. The disconnected investigation service and empty report/disposition states are explicit.
- `sample/population/`: measured manifest and downloadable orders, executions, securities and alert CSVs.
- `evals/population_truth.json`: expected review routes for 96 authored episodes. This file is outside the web-served sample directory and must never be exposed through agent tools or retrieval indexes.

The manifest records observed counts and checks. The intended population is 40,000 parent orders, 150,000 fills, 24 fictional traders, 40 fictional accounts, 30 real equities and 60 sessions. Public history covers 6 March through 30 May 2025. Individual actors and private communications are invented; no misconduct by a real issuer or its employees is implied.

## Ordinary activity

The population includes buys and position-backed sells, market and limit orders, zero-fill cancellations, partial cancellations, amendments, customer instructions and dated portfolio mandates. Opening holdings are explicit. An internal protection collar on a market order is identified separately from an actual limit price via `price_limit_role`.

Schedules vary: TWAP uses equal spacing and intended equal slice sizes; VWAP weights planned slices by simulated minute volume; participation orders target a fixed fraction of simulated volume; manual orders use irregular timing and quantities. Available simulated volume and inventory can constrain a slice. These are illustrative schedules, not vendor algorithms or claims of best execution.

## Market simulation boundary

Real daily OHLC and volume provide the boundary. Synthetic minute paths include the daily open, high, low and close; minute volumes sum exactly to sourced daily volume and exhibit illustrative opening/closing concentration. This construction conditions on the complete daily bar and must not be used to claim forecasting skill. It does not reproduce observed intraday prices, market impact, queue priority or an exchange matching engine.

All simulated broker fills together consume at most 35% of any synthetic minute's volume. This is a construction guardrail, not an empirical market-share estimate. Matches represented on both sides are conservatively counted twice in this budget. Full venue order/depth detail is limited to the authored spoofing episodes; the broader population supplies parent-order lifecycle and fill history.

March daylight saving time is handled with `America/New_York`; the source session calendar excludes dates without historical bars. All dates in this selected window have full regular sessions. A new window requires checking for early closes rather than assuming every session lasts 390 minutes.

## Alert rules

Rules inspect source records; grading keys are associated only after detection. These thresholds are synthetic design choices, not regulatory safe harbors or validated production surveillance parameters:

| Family | Illustrative candidate rule |
| --- | --- |
| Spoofing/layering | At least six unexecuted displayed layers withdrawn in under two seconds, with opposite-side fills during their lifetimes, grouped by account/security/day |
| Pre-announcement | At least 5,000 shares executed within 24 hours before a recorded public event whose schedule was already known |
| Front-running | A principal execution in the same security and direction between receipt and execution of a customer order of at least 15,000 shares, with at least 500 principal shares and a principal first execution inside that interval |
| Wash/self-trade | At least three explicitly matched executions between accounts with the same recorded beneficial owner |
| Coordinated trading | At least three explicitly matched executions between accounts with different recorded beneficial owners |
| Marking the close | An order confined to the final five minutes participates in at least 10% of that window's synthetic market volume |
| Size outlier | At least 5,000 shares and six times the median shares and median daily-volume fraction of up to 80 earlier-session orders in the same desk/security/execution-strategy cohort, with at least 15 observations; daily-volume fraction must also exceed twice the cohort 95th percentile |
| Authorization/restriction | Execution precedes a signature or overlaps an effective account/security restriction; recorded verbal authority and exceptions remain matters for investigation |

An episode can produce more than one alert. These are candidate alert events, not completed investigations. Alerts sharing an underlying order are grouped into persisted investigation cases. A case can carry several signal types, while linked fills and notional are counted once. Independent orders are not merged simply because their account, stock or date matches. Intake deduplication, permissions, live retrieval, model evaluation and analyst disposition remain agent work.

## Validation

Run `.venv/bin/python -m pytest tests -q` after generation. The generator checks foreign keys, counts, timing, limits, market reconciliation, inventory, matched trade legs and coverage of all authored episodes. Mutation tests remove venue-order or public-event sources and rerun detection without grading keys to establish that the corresponding alerts depend on source data.

These checks establish internal consistency. They do not establish statistical representativeness, legal conclusions, intent, calibration of market behavior or agent quality. The private grading variants are concerning, plausibly explained and inconclusive; even the concerning variant is an escalation hypothesis requiring human review.

## Known next improvements

Before evaluating the agent, strengthen exact source citations and document provenance, add controlled prompt-injection and permission-denial records, and test retrieval against a separate held-out set. Restriction exceptions, account-control histories, access records and communication templates are intentionally simplified in this first population build.


Workspace priorities are deterministic display defaults: spoofing/layering, pre-announcement, front-running, self-trading, closing-price and authorization alerts are High; coordinated-trading and size alerts are Medium. These are triage defaults, not model judgments or calibrated risk scores. The static view includes only source metadata and no grading keys. It is a local demo; production authentication, per-user permissions, persisted review actions and live worker status remain backend work.


## Rebalanced scenario population and case queue

Each of the eight families now contains 12 authored episodes: four concerning, four plausibly explained and four inconclusive variants, distributed across dates, accounts and (where applicable) stocks. This is deliberate demo coverage, not an estimate of real-world incident prevalence. The pre-announcement examples share the sourced NVDA earnings event but use different accounts and trade windows.

Version 2 size comparisons separate execution strategies and desks, and adjust for the security's daily liquidity. Prior-day volume is available before the current trading day; finalized current-day volume is only used by this after-close rule. The threshold is not suitable for real-time use before session completion. These are documented synthetic thresholds, not empirically validated banking standards.

The observed v2 result is 141 raw alert events grouped into 105 investigation cases. Primary concerns: spoofing/layering 12, pre-announcement 15, front-running 13, self-trading 12, closing-price activity 12, coordinated trading 12, unusual size 16 and authorization/restriction 13. Raw size signals number 52, because 36 are secondary signals in other cases. No source alerts are deleted or hidden by grouping.

The analyst queue counts cases, displays primary-concern filters, and retains all underlying alert IDs and signal measurements in case details. The primary concern follows a fixed operational precedence, not an agent conclusion. Case identity is a deterministic hash of source event IDs. The stable IDs and immutable source links provide a foundation for subsequent investigation runs; this projection still has no completed agent reports or human dispositions.
