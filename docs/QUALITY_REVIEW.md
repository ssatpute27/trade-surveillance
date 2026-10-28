# Investigation quality review

Baseline captured before v6 live reruns. Original scenario labels and reports are preserved. Diagnostic flags identify review areas, not proven causes.

Original-label disagreements: 42.

## Findings

- Four unavailable communication notices were omitted by embedding-only ranking. v6 surfaces them without requiring vectors. Three other missing keys are office-move distractor messages; not ranking in the top five does not alone establish a retrieval failure.
- Explained scenarios often have supporting narrative records but missing primary order authority. An authored label cannot resolve this gap.
- Some concerning labels imply more certainty than size, timing, missing approval, ownership or a bank research draft establish.
- Some older drafts over-escalate ambiguous cancellation or self-match patterns despite alternative explanations. New runs must assess the explanation rather than copying a label.
- Communication search is now required for coordinated-trading cases. Older runs remain evaluated against their recorded control requirements.
- No benchmark labels have been changed and no assessment has been forced.

## Case-by-case review

### CASE-0088C625 · spoofing_layering

Original label: plausibly_benign; draft: concerning / escalate; controls: 2026-10-agent-v5.2.

Review areas: potential_over_escalation.

Nine large AAPL buy orders—entered shortly after smaller sell orders and cancelled rapidly without execution—were observed with overlap to sell order fills from the same account. This pattern triggered a spoofing/layering signal. Evidence notes risk-linked bid withdrawal, but specific intent for these episodes is not documented; escalation is needed.

Evidence gaps: Order authority and intent are not documented in the linked extract; specific instructions or rationale for layering and rapid cancellation are not recorded. No explicit agent communication or documentation describes whether the layered buy orders in these episodes were bona fide or non-bona-fide, and explicit guidance on cancellation intent is missing from the available record.

Missing keyed sources: none

### CASE-02E115C8 · coordinated_trading

Original label: concerning; draft: inconclusive / request_more_evidence; controls: 2026-10-agent-v3.

Review areas: uncertainty_vs_scenario_label.

Three pairs of closely matched MSFT buy and sell orders were executed between A-04 and A-12 by different traders, without the same beneficial owner or supplied authority documentation. Policy states matched size and timing alone do not prove improper coordination. No approved crossing instruction is present.

Evidence gaps: No documentation of trader authority, instructions, or explicit client approval has been supplied for these orders. No operator instruction or approved crossing instruction is archived for these matched trades.

Missing keyed sources: none

### CASE-08293D4D · spoofing_layering

Original label: inconclusive; draft: concerning / escalate; controls: 2026-10-agent-v3.

Review areas: potential_over_escalation.

T-03 repeatedly placed large (15,000 share) NVDA buy orders that were rapidly cancelled, while smaller sell orders were filled on the opposite side. These large buy orders were well above normal historical size for the desk and each was live for only about one second per cycle. No mandate or signed authority was documented, and strategy logs justifying the pattern are unavailable. The pattern aligns with layering/spoofing risk, and authority/documentation failures warrant escalation as per policy.

Evidence gaps: Original mandate documentation is missing and two mandate versions reportedly disagree on quantity. No relevant communication was recovered to explain the rationale or instruction for these NVDA trades.

Missing keyed sources: none

### CASE-0A99773E · marking_close, size_outlier

Original label: concerning; draft: inconclusive / request_more_evidence; controls: 2026-10-agent-v3.

Review areas: uncertainty_vs_scenario_label.

A buy order for 1,936,162 NVDA shares was manually executed near the close, vastly exceeding the desk’s historical baseline (median 405 shares). No signed mandate or specific order authority is recorded for the transaction. Communications show intent to concentrate purchases near the close due to valuation benchmarks, but do not confirm proper authorization. Documentation from the desk regarding approval and mandate is required to resolve the authority gap.

Evidence gaps: Missing evidence of authorization: No signed mandate or strategy instruction covering this trade is documented.

Missing keyed sources: none

### CASE-0E682694 · pre_announcement, size_outlier

Original label: plausibly_benign; draft: inconclusive / request_more_evidence; controls: 2026-10-agent-v3.

Review areas: uncertainty_vs_scenario_label.

Order O-0000146 was a significant outlier in size compared to historical NVDA orders and was executed before a scheduled public results release. It was supported by prior mandate and strategy authorization referencing only public event timing. The available evidence does not establish whether confidential information was accessed or used.

Evidence gaps: There is no specific retrieved communication record referencing NVDA results, guidance, or confidential information relating to this order.

Missing keyed sources: none

### CASE-0F89D3C6 · pre_announcement, size_outlier

Original label: concerning; draft: inconclusive / request_more_evidence; controls: 2026-10-agent-v3.

Review areas: retrieval_gap, uncertainty_vs_scenario_label.

T-04 placed a highly anomalous buy order for 18,000 NVDA shares (O-0000148) just before NVIDIA’s publicly scheduled earnings on 2025-05-28, which is 45x the desk’s typical size baseline. No mandate or instruction receipt confirming trade authority was on record, and communications suggest awareness of internal research but do not establish possession of confidential results. Absence of authority documentation leaves the legitimacy of the order unresolved.

Evidence gaps: No signed mandate, explicit client instruction, or approval is available for O-0000148, so the basis for trade authority is unverified.

Missing keyed sources: E-000029

### CASE-26DDEED7 · spoofing_layering

Original label: inconclusive; draft: concerning / escalate; controls: 2026-10-agent-v3.

Review areas: potential_over_escalation.

On 2025-05-15, T-06 entered repeated large, short-lived buy orders for AAPL alongside smaller sell orders, canceling each buy layer prior to execution and resulting in sell fills. These layered/canceled buy orders significantly exceeded the desk baseline in size and frequency, and no supporting mandate, instruction, or strategy documentation is available. Communications do not evidence any alternative rationale or approval. Synthetic bank policy requires escalation when authority or strategy gaps co-occur with potential layering.

Evidence gaps: No mandate, claimed instruction, or signed document is available for the entered AAPL orders, leaving authority unresolved. Desk rationale or risk/strategy log supporting any alternative explanation for the large layered buy orders is missing.

Missing keyed sources: none

### CASE-2F9C358A · authorization_restriction

Original label: concerning; draft: inconclusive / request_more_evidence; controls: 2026-10-agent-v3.

Review areas: uncertainty_vs_scenario_label.

Order O-0000358 for JPM was executed before the related mandate was formally signed, and current records provide no documentation or recording of a valid verbal authorization per policy. No supervisor acknowledgment or restriction exception was found. Further evidence of timely approval, such as client verbal authorization and supervisor acknowledgment, is required.

Evidence gaps: No evidence of timely client verbal or written authorization for the O-0000358 trade has been provided. No evidence of supervisor acknowledgment for a verbal trade instruction has been supplied.

Missing keyed sources: none

### CASE-322898AC · front_running, size_outlier

Original label: concerning; draft: inconclusive / request_more_evidence; controls: 2026-10-agent-v3.

Review areas: uncertainty_vs_scenario_label.

Flagged orders in AMZN include a significant size outlier (20,000 shares vs prior median 1,265.5) with instruction receipt documented for O-0000170. However, for both O-0000169 and O-0000170, no supporting portfolio mandate or hedging consent is documented. Access records show T-01 viewed the pending customer instruction prior to placing a principal order. With key authorization and consent evidence missing, a substantive violation is not established but the case warrants further review.

Evidence gaps: No portfolio mandate, dated trading authorization, or hedging consent was provided for the size outlier order(s).

Missing keyed sources: none

### CASE-3B7F48EA · spoofing_layering

Original label: plausibly_benign; draft: concerning / escalate; controls: 2026-10-agent-v3.

Review areas: potential_over_escalation.

A concerning pattern was observed in MSFT: large, rapid, unfilled buy orders placed and cancelled within seconds, shortly before filled smaller sell orders, diverging markedly from historical desk size norms. However, there is no available mandate or authority directly linked to these specific orders in the extracted records.

Evidence gaps: No evidence was found of a signed mandate, instruction, or authority authorizing these flagged orders. The extracted authority records explicitly record mandates as none and instructions as not recorded. The actual intent behind these rapid, large buy orders and their cancellations cannot be verified without further supporting communications or documented order-level strategy linkage.

Missing keyed sources: none

### CASE-4934E3A6 · spoofing_layering

Original label: plausibly_benign; draft: inconclusive / request_more_evidence; controls: 2026-10-agent-v3.

Review areas: uncertainty_vs_scenario_label.

A series of rapid, large buy orders in NVDA were placed and cancelled without execution during three cycles in the alert window. While a client allocation document exists, the specific orders flagged have no recorded mandate linkage or signature in the order authority extract. The desk’s risk ticket describes a general cancellation strategy, but evidence does not connect it to these specific orders. Further evidence on direct order authority or strategy linkage is required.

Evidence gaps: No evidence confirms mandate linkage, instruction receipt, or approval signatures for the flagged orders—these fields are explicitly missing per the authority extract. No retrieved instruction, communication, or system log directly ties the general strategy log’s risk-based cancellation to these nine flagged NVDA buy orders.

Missing keyed sources: none

### CASE-4A3C38E5 · pre_announcement, size_outlier

Original label: concerning; draft: inconclusive / request_more_evidence; controls: 2026-10-agent-v4.

Review areas: uncertainty_vs_scenario_label.

A large NVDA order (45x historical median for A-01) was placed manually just before NVIDIA’s public results, without a recorded mandate or instruction. Communications around the time reference keeping 'figures out of the Desk Channel,' but no access to issuer confidential results is established. Further evidence (instruction, approval, or direct result access) is required for disposition.

Evidence gaps: No signed instruction or documented mandate for the order is provided in the available authority records. There is insufficient evidence to confirm or rule out possession of nonpublic results or a direct trading instruction by the trader.

Missing keyed sources: none

### CASE-542714B9 · wash_self_trade

Original label: plausibly_benign; draft: concerning / escalate; controls: 2026-10-agent-v3.

Review areas: potential_over_escalation.

Three sets of paired, same-size buy and sell limit orders for AAPL were executed almost simultaneously between accounts A-01 and A-09, controlled by the same beneficial owner. While accidental self-match was documented, there was no attached proof of independent decision making or an approved crossing instruction, triggering synthetic policy escalation for potential wash/self-trading.

Evidence gaps: There is no recovery of independent strategy records or explicit demonstration that T-04 and T-19 acted separately for these orders. No signed, approved crossing instruction or operator attestation is present in available material.

Missing keyed sources: none

### CASE-579289A4 · size_outlier

Original label: concerning; draft: inconclusive / request_more_evidence; controls: 2026-10-agent-v3.

Review areas: uncertainty_vs_scenario_label.

A manual MSFT buy order of 30,000 shares was flagged as an extreme size outlier versus a historical median of 387 shares. No linked mandate, portfolio instruction, or explicit authorization was found for order O-0000343. Restrictions were not active, but the trade's basis remains unresolved; further evidence of documented approval is needed.

Evidence gaps: No signed instruction, explicit order ticket approval, or dated mandate supporting the large MSFT trade was found in current records. The 'approved order quantity' referenced in the communication is unspecified and not linked to the MSFT order’s size.

Missing keyed sources: none

### CASE-5AD25B43 · wash_self_trade

Original label: concerning; draft: inconclusive / request_more_evidence; controls: 2026-10-agent-v3.

Review areas: uncertainty_vs_scenario_label.

Three pairs of matched buy/sell MSFT executions occurred between two accounts with identical beneficial owner, in sizes below desk historical median, flagged as wash/self trades. There is no documented instruction, mandate, or crossing approval provided for these trades. Further evidence of decision-making, authority, or exception is required to establish intent or policy breach.

Evidence gaps: No documentary evidence of trade mandate, client instruction, or internal exception was provided for these transactions.

Missing keyed sources: none

### CASE-5CBC73BD · authorization_restriction

Original label: concerning; draft: inconclusive / request_more_evidence; controls: 2026-10-agent-v3.

Review areas: uncertainty_vs_scenario_label.

Order O-0000352 in AAPL began execution before the supporting mandate was signed, with no record of verbal or pre-signing authority in the available evidence. This leaves a gap regarding valid authorization at the time of order execution.

Evidence gaps: No client authorization, supervisor acknowledgment, or pre-execution verbal recording is present to explain early order execution.

Missing keyed sources: none

### CASE-5E82D8BD · front_running, size_outlier

Original label: plausibly_benign; draft: inconclusive / request_more_evidence; controls: 2026-10-agent-v3.

Review areas: uncertainty_vs_scenario_label.

The large NVDA order in A-27 (O-0000178) was backed by a client allocation and a recorded customer instruction. A-11's NVDA buy (O-0000177) occurred before the client's execution but lacks a recorded mandate or instruction. However, the customer instruction for A-27 authorized a principal hedge before the block execution. The case cannot be resolved without review of the specific risk approval and compliance exception attached to the hedge.

Evidence gaps: No mandate, claimed instruction, or signed documentation was located for A-11’s NVDA order; the compliance exception for the principal hedge remains unverified in the current record.

Missing keyed sources: none

### CASE-6887E1E0 · coordinated_trading

Original label: plausibly_benign; draft: inconclusive / request_more_evidence; controls: 2026-10-agent-v3.

Review areas: uncertainty_vs_scenario_label.

Multiple cross-account AAPL trades matched in size and timing between unrelated beneficial owners, with crossing records stating that both clients signed negotiated-cross instructions and all three trades received matching engine 'CROSS-APPROVED' tags. However, direct order authority documentation in the order records is not available.

Evidence gaps: There is no direct documentation of mandate, signed instructions, or receipt in the extracted order authority for orders O-0000271 through O-0000276.

Missing keyed sources: none

### CASE-731FF2C6 · wash_self_trade

Original label: concerning; draft: inconclusive / request_more_evidence; controls: 2026-10-agent-v3.

Review areas: uncertainty_vs_scenario_label.

Three paired buy/sell trades in AAPL executed between accounts with identical beneficial ownership, at the same time and size, triggered a wash/self-trading alert. No authority or crossing instruction is available for these matched trades. Policy requires assessment of independent decision-making and alternative explanations; intent and authorization remain unresolved due to missing records.

Evidence gaps: No extracted record of the authority, trading rationale, or independent control for the matched orders. Communications or records of strategy for the involved trades and account-control certification are unavailable.

Missing keyed sources: none

### CASE-760328B8 · authorization_restriction

Original label: concerning; draft: inconclusive / request_more_evidence; controls: 2026-10-agent-v3.

Review areas: uncertainty_vs_scenario_label.

Order O-0000355 (900 AMZN shares) was executed before the client mandate was signed. Policy allows for verbal instructions if a pre-execution recording and supervisor approval exist, but these supporting records are absent. No effective trading restriction or abnormal size was found. The original client authorization or qualifying verbal instruction evidence is required for final assessment.

Evidence gaps: The original client authorization or pre-trade verbal approval record is missing from supplied evidence.

Missing keyed sources: none

### CASE-782ED0A4 · marking_close, size_outlier

Original label: concerning; draft: inconclusive / request_more_evidence; controls: 2026-10-agent-v3.

Review areas: uncertainty_vs_scenario_label.

Order O-0000256, a manual buy of 371,431 AAPL shares near the close, is a pronounced outlier versus historical desk activity and triggered marking-close surveillance. No mandate or explicit instruction authorizes this trade on record. Communications suggest intent to influence the closing price for valuation, but a valid exception or authority remains undocumented. Further evidence of account authorization or a legitimate benchmark/mandate is needed.

Evidence gaps: No signed instruction, mandate amendment, or explicit documented exception for this account's large AAPL purchase near close is on file; desk authorization is unresolved. No evidence was retrieved indicating a contemporaneous benchmark, rebalancing program, or regulatory deadline requiring such trading in AAPL for this account.

Missing keyed sources: none

### CASE-7902E466 · front_running, size_outlier

Original label: plausibly_benign; draft: inconclusive / request_more_evidence; controls: 2026-10-agent-v3.

Review areas: uncertainty_vs_scenario_label.

Order O-0000166 is a significant outlier in MSFT size, but has a recorded customer instruction and explicit authorization for the principal hedge ahead of the block. Mandate and instruction documentation for O-0000165 remain absent, creating an unresolved authority gap. There is no evidence of front-running based on timing alone.

Evidence gaps: There is no mandate, client instruction record, or documented authority for O-0000165 in the available extracts; required for conclusive review.

Missing keyed sources: none

### CASE-79A93EFB · coordinated_trading

Original label: concerning; draft: inconclusive / request_more_evidence; controls: 2026-10-agent-v3.

Review areas: uncertainty_vs_scenario_label.

Three pairs of buy and sell NVDA orders were entered manually at identical sizes and times by different traders in unrelated accounts, lacking explicit mandate or approved crossing documentation. While the trading matches in time and size, current policy states this pattern alone does not confirm improper coordination, especially without communications or authority records.

Evidence gaps: No communication or instruction records were reviewed; without such evidence, intent or improper coordination cannot be determined. No approved crossing instruction or related operational approval is present for the matched trades.

Missing keyed sources: none

### CASE-7DC7B9DB · pre_announcement, size_outlier

Original label: plausibly_benign; draft: inconclusive / escalate; controls: 2026-10-agent-v3.

Review areas: uncertainty_vs_scenario_label.

The 18,000-share NVDA order entered by T-23 for A-11 was an extreme outlier compared to prior manual trades (historical median: 309 shares). This activity was authorized by a documented mandate and referenced public event timing; strategy approval made no reference to confidential results. No direct evidence of confidential information or intent appears in reviewed records. Due to the significant size and event timing, further review is recommended.

Evidence gaps: No direct evidence was recovered to confirm or refute receipt or use of confidential NVDA earnings results.

Missing keyed sources: none

### CASE-9732738F · size_outlier

Original label: concerning; draft: inconclusive / request_more_evidence; controls: 2026-10-agent-v3.

Review areas: uncertainty_vs_scenario_label.

A 30,000-share manual AMZN buy was entered by T-22 and flagged as a size outlier compared to historical activity. No mandate or portfolio instruction is documented for this order. The bank policy requires verification of mandate and authority for such outliers. Additional desk-supplied records or explicit authorization are required to resolve the unexplained authority gap.

Evidence gaps: No desk-supplied mandate, explicit order instruction, or approval is provided for the size outlier. Absence of these documents in the extract means authority cannot be verified.

Missing keyed sources: none

### CASE-B50F9F5E · coordinated_trading

Original label: concerning; draft: inconclusive / request_more_evidence; controls: 2026-10-agent-v3.

Review areas: uncertainty_vs_scenario_label.

Three pairs of matched AMZN buy/sell trades were executed between accounts A-04 and A-12 at identical times and prices, each involving different beneficial owners and no mandate or crossing authority on record. Policy clarifies that matched trade patterns alone do not establish misconduct. No controlling relationship or approved instructions explain the activity, but the absence of authority records leaves the explanation unresolved.

Evidence gaps: No evidence of account relationships or crossing approvals was located, but the absence of instruction or mandate documentation leaves the permissible purpose unresolved.

Missing keyed sources: none

### CASE-B6EBE1D3 · pre_announcement, size_outlier

Original label: concerning; draft: inconclusive / request_more_evidence; controls: 2026-10-agent-v3.

Review areas: retrieval_gap, uncertainty_vs_scenario_label.

A highly unusual manual NVDA buy order (18,000 shares) executed hours before a scheduled public earnings release flagged both as a size outlier and a pre-announcement event. No trade mandate or instruction is recorded for this activity. Communications indicate heightened sensitivity regarding information flow, but do not confirm possession or misuse of confidential results. Further evidence of trade authority or intent is required.

Evidence gaps: There is no available record of the authorization, mandate, or instruction associated with the order. No direct evidence confirms the trader received or acted on any nonpublic earnings results.

Missing keyed sources: E-000041

### CASE-BAAC2C60 · wash_self_trade

Original label: plausibly_benign; draft: inconclusive / request_more_evidence; controls: 2026-10-agent-v3.

Review areas: uncertainty_vs_scenario_label.

Three pairs of AMZN trades were matched between accounts A-01 and A-09, both under identical beneficial ownership, at the same size, price, and near-simultaneous timing. No record of trade authority or mandate is available. Exception logs indicate these self-matches were accidental and subject to cross-approved control overrides and remediation, but missing instructions or explicit approvals remain a compliance gap.

Evidence gaps: No formal order mandate, instruction record, or approval is available to conclusively determine trading intent or compliance with cross-account policy.

Missing keyed sources: none

### CASE-C3D70FD4 · marking_close, size_outlier

Original label: concerning; draft: inconclusive / request_more_evidence; controls: 2026-10-agent-v3.

Review areas: uncertainty_vs_scenario_label.

A buy order for 170,677 MSFT shares, far larger than this desk's historical median, was entered manually just before the close. No mandate or instruction is recorded, and communications indicate an intent to concentrate buying in the final minutes. Authority for the trade is unresolved due to unavailable mandate and instruction evidence.

Evidence gaps: Mandate, portfolio instruction, or other explicit authorization for this order is unavailable and could not be verified.

Missing keyed sources: none

### CASE-CEC7322D · authorization_restriction

Original label: concerning; draft: inconclusive / request_more_evidence; controls: 2026-10-agent-v3.

Review areas: uncertainty_vs_scenario_label.

Order O-0000349 (buy 900 MSFT shares) was executed prior to formal signature of the supporting instruction (M-0000349). There is no record of verbal pre-execution approval or supervisor acknowledgment; the later signature alone does not suffice according to policy. The only gap is the absence of evidence for valid pre-execution authority.

Evidence gaps: There is no record of a verbal client instruction, pre-execution recording, or supervisor approval for this trade. The original client authorization (if any) is missing from supplied records.

Missing keyed sources: none

### CASE-D45DD0A9 · wash_self_trade

Original label: plausibly_benign; draft: inconclusive / request_more_evidence; controls: 2026-10-agent-v3.

Review areas: uncertainty_vs_scenario_label.

Three same-quantity matched MSFT buy/sell trades between accounts A-01 and A-09 (sharing the same beneficial owner) triggered a wash/self trade alert. The trades are all under typical desk medians and occurred at nearly identical times. No documented order authority or crossing instruction is available, while independent logs report the matches as accidental and remediation controls were triggered. Additional evidence (signed instruction or authorized crossing approval) is needed.

Evidence gaps: No signed trading instruction or explicit cross-trade approval is present for the matched executions. Operator instruction and account-control records are referenced but not attached; it is unclear whether an approved crossing instruction exists.

Missing keyed sources: none

### CASE-D7D41857 · coordinated_trading

Original label: plausibly_benign; draft: inconclusive / request_more_evidence; controls: 2026-10-agent-v3.

Review areas: uncertainty_vs_scenario_label.

Matched MSFT trades between A-05 and A-13 occurred at identical sizes and near-simultaneous times, flagged as coordinated trading. Both clients reportedly signed a negotiated-cross instruction per a secondary record, but primary order extracts show missing authority documentation. No evidence of shared beneficial ownership or explicit policy breach was found. The absence of direct signatures or mandates precludes confirming proper authorization.

Evidence gaps: All primary order extracts lack direct authority documentation, with no instruction receipts or signatures recorded.

Missing keyed sources: none

### CASE-DEAA57C7 · wash_self_trade

Original label: concerning; draft: inconclusive / request_more_evidence; controls: 2026-10-agent-v3.

Review areas: uncertainty_vs_scenario_label.

Three pairs of AMZN buy and sell orders between accounts under identical beneficial ownership were executed in matched sizes and timing, without any documented mandate, instruction, or crossing exception. Although this pattern matches a wash/self-trade surveillance signal and lacks necessary approvals, intent and violation are not established from current records alone. Additional evidence on trading authority and instruction is required.

Evidence gaps: No signed mandate, client instruction, or compliance exception approval is available to clarify the authorization or rationale for these trades. Account-control and strategy communication records, which could reveal if the crossings were independently decided or coordinated, are missing.

Missing keyed sources: none

### CASE-E34A33C6 · wash_self_trade

Original label: concerning; draft: inconclusive / request_more_evidence; controls: 2026-10-agent-v3.

Review areas: uncertainty_vs_scenario_label.

Three pairs of identical NVDA buy and sell orders executed instantaneously and in full between accounts with the same beneficial owner, but no mandate or crossing approval is recorded. The trade sizes match historical medians. Absence of authority records and approved crossing instruction is a material gap; policy requires escalation and alternative explanations to be considered.

Evidence gaps: Missing mandate, explicit instruction, and approval documentation for all matched trades. Unavailable strategy communications and independent account-control certification prevent definitive assessment of oversight and intent. Two mandate versions disagree on quantity; the original signed attachment is unavailable and approval cannot be inferred from the metadata.

Missing keyed sources: none

### CASE-E35A57F6 · wash_self_trade

Original label: plausibly_benign; draft: inconclusive / request_more_evidence; controls: 2026-10-agent-v3.

Review areas: uncertainty_vs_scenario_label.

Three pairs of highly matched NVDA buy/sell trades occurred between accounts with the same beneficial owner. The alert and records confirm repeated same-owner crosses with no available mandate, approvals, or signed instructions. Logs suggest an accidental self-match and a control exception, but explicit operator intent is not established due to missing documentation. Policy requires further review when material evidence is unavailable.

Evidence gaps: Account mandate records, signed instructions, and operator approval documentation for these specific trades remain unavailable. The full content of relevant strategy communications and account-control certifications for these cross trades is unavailable.

Missing keyed sources: none

### CASE-E3C68AD0 · size_outlier

Original label: concerning; draft: inconclusive / request_more_evidence; controls: 2026-10-agent-v3.

Review areas: uncertainty_vs_scenario_label.

A large manual NVDA buy order in account A-01 (30,000 shares) is a significant size outlier versus the historical median (433 shares). No mandate, instruction, or documented authority was found for this trade, and the rationale remains unclear. There are no restriction records prohibiting the trade. Further evidence from the desk is required to clarify authority and intent.

Evidence gaps: No signed mandate, instruction, or explicit approval supporting the large NVDA trade was found; desk documentation is missing.

Missing keyed sources: none

### CASE-E55A06FF · pre_announcement, size_outlier

Original label: concerning; draft: inconclusive / request_more_evidence; controls: 2026-10-agent-v3.

Review areas: retrieval_gap, uncertainty_vs_scenario_label.

A large (18,000 share) NVDA order, significantly exceeding historical size norms, was placed by T-22 before a scheduled public earnings announcement. Mandate and instruction evidence is missing. Communications reference a research draft and information timing but do not confirm access to confidential results. No direct evidence establishes improper authority, intent, or use of restricted data. Further mandate and instruction records are needed.

Evidence gaps: There is no documented mandate, explicit instruction, or signed approval for the order, leaving the authority for the trade unresolved. No direct evidence establishes T-22’s access to confidential NVDA results prior to public release.

Missing keyed sources: E-000053

### CASE-E6272323 · front_running, size_outlier

Original label: plausibly_benign; draft: inconclusive / request_more_evidence; controls: 2026-10-agent-v4.

Review areas: uncertainty_vs_scenario_label.

Order O-0000172 is a large buy for AMZN, confirmed as a size outlier but supported by a documented client mandate and a recorded instruction authorizing a disclosed principal hedge ahead of the block. Order O-0000171, a smaller AMZN buy, lacks clear evidence of mandate or instruction. Principal hedge authority exists for O-0000172, but the compliance exception is unresolved. No direct evidence of intent, misuse of information, or undisclosed trading is found, but authority for O-0000171 remains uncertain.

Evidence gaps: No documented mandate, instruction receipt, or authorization is found for Order O-0000171; authority or rationale for this trade is unclear. Compliance review and confirmation of the principal hedge exception for the pre-block activity remains incomplete.

Missing keyed sources: none

### CASE-E6C951C4 · spoofing_layering

Original label: plausibly_benign; draft: inconclusive / request_more_evidence; controls: 2026-10-agent-v3.

Review areas: uncertainty_vs_scenario_label.

Large, rapidly canceled buy orders for AMZN coincided with smaller, filled sell orders, consistent with a layering/spoofing pattern. The buy order sizes were highly anomalous versus the historical baseline. Mandate and risk-ticket records reference expected participation and cancellation tactics, but do not directly evidence authorized use of this specific rapid submission/cancel pattern for these orders. No direct instruction or confirmation links these orders to their purported purpose.

Evidence gaps: No direct authority documentation, order-level signatures, or specific instruction confirmations exist for the individual large buy orders; authority is not evidenced in the approval system.

Missing keyed sources: none

### CASE-EE20C218 · authorization_restriction

Original label: plausibly_benign; draft: inconclusive / request_more_evidence; controls: 2026-10-agent-v3.

Review areas: uncertainty_vs_scenario_label.

Order O-0000353 was executed after receipt of a claimed client instruction and before a written signature, with evidence that a recorded call provided explicit verbal client authorization and supervisor acknowledgment as per demo policy. However, the actual recording content and completeness of restrictions coverage are not directly verified from the available evidence, creating residual uncertainty.

Evidence gaps: The actual content of the recorded call and details of the supervisor acknowledgment were not available for verification in the evidence provided. No restriction was found, but the result does not rule out missing, confidential, or temporary internal restrictions.

Missing keyed sources: none

### CASE-F6774EFE · front_running, size_outlier

Original label: plausibly_benign; draft: inconclusive / request_more_evidence; controls: 2026-10-agent-v3.

Review areas: uncertainty_vs_scenario_label.

A significant size outlier AAPL order (20,000 shares) was executed for account A-18, and a smaller order for A-02, both via manual strategy. Historical median size for this desk and strategy is much lower. There is explicit, time-stamped customer instruction and principal hedge authorization documented for the large order and block. However, mandate and authority documentation for A-02’s order (O-0000159) remain missing, leaving its authorization unresolved. No evidence supports established advance knowledge or customer information misuse by trading staff in available records.

Evidence gaps: Order authority documentation for AAPL O-0000159 is absent; cannot resolve whether A-02’s order was properly authorized.

Missing keyed sources: none

### CASE-FF5E602E · spoofing_layering

Original label: inconclusive; draft: concerning / escalate; controls: 2026-10-agent-v3.

Review areas: potential_over_escalation.

The flagged AMZN trades in account A-12 show a repeated pattern of large, short-lived layered buy orders that are cancelled without execution, while smaller sell limit orders are filled in overlapping timeframes. There is no documented authority or strategic rationale, and no communications explain or justify the trading pattern. Required policy and market context checks were performed. These factors support deep review for potential spoofing or layering.

Evidence gaps: Mandate, signed instructions, and supporting rationale documentation for T-24’s AMZN trading in A-12 on 2025-05-23 are missing or unavailable. Strategy-support log covering the three AMZN order cycles is unavailable, leaving trading intent and explanation for the observed order pattern unresolved.

Missing keyed sources: none
