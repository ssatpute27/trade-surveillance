"""Synthetic source records only. Grading keys live outside this module."""

ALERTS = [
    dict(id='TS-1042', subject='Alex Morgan', desk='Equities / Event Strategies', symbol='NOVA',
         title='Trading ahead of acquisition announcement', priority='High', rule='pre_announcement',
         event_time='2026-06-12T14:10:00Z', notional=4800000),
    dict(id='TS-1043', subject='Jordan Lee', desk='Institutional / Portfolio Execution', symbol='HBRX',
         title='Order size exceeds historical baseline', priority='Medium', rule='size_outlier',
         event_time='2026-06-12T15:00:00Z', notional=6200000),
    dict(id='TS-1044', subject='Sam Patel', desk='Equities / Client Execution', symbol='VELA',
         title='Conflicting order provenance', priority='High', rule='provenance_conflict',
         event_time='2026-06-12T14:45:00Z', notional=3100000),
]


def record(eid, case, kind, text, timestamp='2026-06-12T13:00:00Z', status='available', **meta):
    return dict(id=eid, case_id=case, kind=kind, text=text, timestamp=timestamp,
                status=status, permission='surveillance', metadata=meta)


POLICIES = [
    record('POL-1', '*', 'policy', 'POL-1 | Surveillance Standard v1.0 | Section 1: Every eligible alert requires trade verification, historical baseline, order/mandate provenance, public-context review, and consultation of this policy. The system drafts assessments; only a human reviewer records a disposition.', '2026-06-01T00:00:00Z'),
    record('POL-2', '*', 'policy', 'POL-2 | Surveillance Standard v1.0 | Section 2: Pre-announcement alerts require targeted communications review. A possible confidential-information lead requires deep investigation and relationship/access checks even when public research offers a plausible explanation. A relationship or entitlement alone does not establish receipt or use of confidential information.', '2026-06-01T00:00:00Z'),
    record('POL-3', '*', 'policy', 'POL-3 | Surveillance Standard v1.0 | Section 3: A dated mandate must precede execution and match security, direction, size, and execution window. Contradictory provenance or unavailable access records requires deep investigation and human attention. Missing data is not exculpatory evidence.', '2026-06-01T00:00:00Z'),
]

EVIDENCE = POLICIES + [
    record('TRD-42', 'TS-1042', 'trades', 'On 12 June 2026 at 14:10 UTC, Alex Morgan bought 120,000 NOVA shares at $40, notional $4,800,000. The fictional NOVA acquisition was announced on 15 June 2026 at 12:00 UTC.', quantity=120000, price=40, historical_notionals=[400000,600000,500000,450000,550000]),
    record('ORD-42', 'TS-1042', 'mandate', 'Order O-842 was entered by Alex Morgan on 12 June 2026 at 14:02 UTC for 120,000 NOVA shares. Rationale: public sector consolidation research. No client rebalance instruction is attached.'),
    record('NEWS-42', 'TS-1042', 'public', 'Public Northbridge Research note published 11 June 2026 at 09:00 UTC identified NOVA as one of six possible consolidation candidates. It named no buyer, transaction date, or agreed price.', '2026-06-11T09:00:00Z'),
    record('COM-42A', 'TS-1042', 'communications', 'Alex to Taylor, 12 June 2026 13:35 UTC: Is the blue folder finally getting a signature on Monday? Keep this away from the desk channel until the ink dries.', '2026-06-12T13:35:00Z'),
    record('COM-42B', 'TS-1042', 'communications', 'Alex to execution desk, 12 June 2026 13:45 UTC: The sector note makes a decent case for NOVA. Keep the limit at forty.', '2026-06-12T13:45:00Z'),
    record('COM-42C', 'TS-1042', 'communications', 'Operations channel, 10 June 2026: The blue folder for the office lease needs a signature. Facilities will collect it next week.', '2026-06-10T10:00:00Z'),
    record('REL-42', 'TS-1042', 'relationships', 'Approved employee directory records identify Taylor Reed as a corporate advisory associate assigned to Project Blue, concerning NOVA. Alex Morgan and Taylor Reed attended an internal training session on 9 June 2026. No recorded evidence establishes what they discussed.'),
    record('ACC-42', 'TS-1042', 'access', 'Taylor Reed accessed the Project Blue draft announcement on 12 June 2026 at 12:55 UTC. Alex Morgan had no direct entitlement and no successful access event in the available 10-12 June access extract. The extract cannot establish whether any off-system disclosure occurred.', '2026-06-12T12:55:00Z'),
    record('TRD-43', 'TS-1043', 'trades', 'On 12 June 2026 at 15:00 UTC, Jordan Lee bought 100,000 HBRX shares at $62, notional $6,200,000.', quantity=100000, price=62, historical_notionals=[1000000,1200000,900000,1100000,800000]),
    record('ORD-43', 'TS-1043', 'mandate', 'Client mandate M-731 signed 10 June 2026 at 16:00 UTC instructs purchase of 100,000 HBRX shares on 12 June between 14:30 and 15:30 UTC for the quarterly index rebalance. Order O-843 references M-731 and matches security, buy direction, quantity, and execution window.', '2026-06-10T16:00:00Z'),
    record('NEWS-43', 'TS-1043', 'public', 'Public index notice published 8 June 2026 states HBRX enters the fictional Broad Market 200 index at the close on 12 June. No acquisition announcement is present in the supplied public-news snapshot.', '2026-06-08T10:00:00Z'),
    record('COM-43', 'TS-1043', 'communications', 'Jordan to portfolio operations: Execute the signed quarterly index instruction M-731 within the approved window. Confirm allocation after the fill.'),
    record('TRD-44', 'TS-1044', 'trades', 'On 12 June 2026 at 14:45 UTC, Sam Patel bought 50,000 VELA shares at $62, notional $3,100,000.', quantity=50000, price=62, historical_notionals=[300000,350000,250000,400000,200000]),
    record('ORD-44', 'TS-1044', 'mandate', 'Order O-844 lists client instruction received at 14:20 UTC. The attached instruction was signed at 15:10 UTC, after the 14:45 execution. The metadata and attached document conflict; no earlier signed version is available.', '2026-06-12T15:10:00Z'),
    record('NEWS-44', 'TS-1044', 'public', 'Public VELA earnings call scheduled for 16 June 2026. The supplied news snapshot contains no event explaining the specific timing of this order.', '2026-06-11T09:00:00Z'),
    record('COM-44', 'TS-1044', 'communications', 'Sam to operations at 14:25 UTC: We have verbal approval; the signed copy should follow. Operations at 15:15 UTC: The attachment timestamp does not match the original order record.', '2026-06-12T15:15:00Z'),
    record('REL-44', 'TS-1044', 'relationships', 'Approved relationship records show Sam Patel serves the institutional client account listed on O-844. This establishes account coverage, not the timing of authorization.'),
    record('ACC-44', 'TS-1044', 'access', 'Access-log partition for VELA, 12 June 2026 12:00-16:00 UTC, is unavailable due to a synthetic archive failure. Request archive restoration from the records custodian.', status='unavailable'),
    record('DENIED-44', 'TS-1044', 'restricted', 'Restricted personnel record: never included in agent retrieval.', status='access_denied'),
]
