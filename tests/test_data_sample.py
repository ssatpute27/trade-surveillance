import sqlite3
import pytest
from scripts.build_data_sample import build, validate, visible_evidence


@pytest.fixture
def db(tmp_path):
    connection=build(tmp_path/'review.sqlite3')
    yield connection
    connection.close()


def test_curated_sample_reconciles(db):
    checks,errors=validate(db)
    assert all(checks.values()),errors
    assert db.execute('SELECT count(*) FROM orders').fetchone()[0]==20


def test_rejects_orphan_execution(db):
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("UPDATE fills SET order_id='does-not-exist' WHERE fill_id='O-842-F01'")


@pytest.mark.parametrize('assignment',["quantity=999999", "price_cents=99999", "executed_at='2025-05-28T21:30:00Z'"])
def test_validation_catches_bad_fill(db,assignment):
    db.execute(f"UPDATE fills SET {assignment},ingested_at='2025-05-28T22:00:00Z' WHERE fill_id='O-842-F01'")
    checks,errors=validate(db)
    assert not checks['lifecycle_quantity_limits_sessions_market_price']
    assert errors


def test_scope_cutoff_and_denial_apply_before_retrieval(db):
    rows=visible_evidence(db,'A-03','2025-05-29T12:10:00Z')
    ids={r['evidence_id'] for r in rows}
    assert 'E-014' in ids  # Coverage failure is visible, not treated as zero events.
    assert 'E-017' not in ids  # Future source.
    assert 'E-018' not in ids  # Restricted source.
    assert 'E-004' not in ids  # Another account's private communication.
    assert 'E-002' in ids  # Announcement is available during investigation.


def test_announcement_and_access_extract_not_known_before_trade(db):
    ids={r['evidence_id'] for r in visible_evidence(db,'A-01','2025-05-28T14:09:00Z')}
    assert 'E-001' in ids
    assert 'E-002' not in ids
    assert 'E-008' not in ids  # Extract not yet available, even though an event occurred.


def test_ingestion_delay_is_not_ignored(db):
    ids={r['evidence_id'] for r in visible_evidence(db,'A-01','2025-05-28T13:35:02Z')}
    assert 'E-004' not in ids


def test_large_control_and_multiple_rebalance_lines_exist(db):
    amount=db.execute("SELECT sum(quantity*price_cents) FROM fills WHERE order_id='O-1014'").fetchone()[0]
    assert amount>db.execute("SELECT sum(quantity*price_cents) FROM fills WHERE order_id='O-843'").fetchone()[0]
    assert db.execute("SELECT count(DISTINCT security_id) FROM mandates WHERE source_record_id='DOC-731'").fetchone()[0]==2


def test_partial_cancel_has_unexecuted_remainder(db):
    executed=db.execute("SELECT sum(quantity) FROM fills WHERE order_id='O-1015'").fetchone()[0]
    assert executed==5000
    assert db.execute("SELECT event_type FROM order_events WHERE order_id='O-1015' ORDER BY event_at DESC LIMIT 1").fetchone()[0]=='cancelled'


def test_real_security_and_historical_anchor(db):
    row=db.execute("SELECT * FROM securities WHERE security_id='S-01'").fetchone()
    assert row['symbol']=='NVDA'
    assert 'NVIDIA' in row['issuer'].upper()
    bar=db.execute("SELECT * FROM market_daily WHERE security_id='S-01' AND session_date='2025-05-28'").fetchone()
    assert bar['open_cents']==13603
    assert len(bar['response_sha256'])==64
    assert bar['source_url'].startswith('https://query1.finance.yahoo.com/')
    assert db.execute("SELECT price_cents FROM fills WHERE fill_id='O-842-F01'").fetchone()[0]==13603


def test_market_range_validation_detects_corruption(db):
    db.execute("UPDATE market_daily SET high_cents=1 WHERE security_id='S-01' AND session_date='2025-05-28'")
    checks,_=validate(db)
    assert not checks['fills_within_sourced_daily_range']


def test_public_fact_and_synthetic_evidence_have_different_origins(db):
    import json
    public=db.execute("SELECT metadata_json FROM evidence WHERE evidence_id='E-002'").fetchone()[0]
    private=db.execute("SELECT metadata_json FROM evidence WHERE evidence_id='E-004'").fetchone()[0]
    assert json.loads(public)['origin']=='historical_public_summary'
    assert json.loads(private)['origin']=='synthetic'
    assert 'investor.nvidia.com' in json.loads(public)['source_url']
