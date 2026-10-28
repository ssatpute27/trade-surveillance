from app.demo_identities import display_identities,TRADER_NAMES,ACCOUNT_NAMES


def test_aliases_are_consistent_without_mutating_original_evidence():
    original={'text':'Alex Demo-01 traded for Simulated Internal Book 01.',
              'quote':{'text':'Alex Demo-01'},'quantity':1500,'evidence_id':'E-01'}
    displayed=display_identities(original)
    assert displayed['text']=='Alex Bennett traded for Event Opportunities Book.'
    assert displayed['quote']['text']=='Alex Bennett'
    assert displayed['quantity']==1500 and displayed['evidence_id']=='E-01'
    assert original['quote']['text']=='Alex Demo-01'
    assert display_identities(displayed)==displayed
    assert len(set(TRADER_NAMES))==24 and len(set(ACCOUNT_NAMES))==40
