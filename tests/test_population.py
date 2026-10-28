"""Integration checks against the generated population; no API calls or model graders."""
import json
import shutil
import sqlite3
from pathlib import Path
import pytest
from scripts.build_population import Population

ROOT=Path(__file__).resolve().parent.parent
DATABASE=ROOT/'data/population.sqlite3'


@pytest.fixture
def source():
    if not DATABASE.exists():pytest.skip('Generate the population with python -m scripts.build_population first')
    db=sqlite3.connect(f'file:{DATABASE}?mode=ro',uri=True)
    db.row_factory=sqlite3.Row
    yield db
    db.close()


def test_full_population_and_source_window(source):
    assert source.execute('SELECT count(*) FROM fills').fetchone()[0]==150000
    assert source.execute('SELECT count(*) FROM orders').fetchone()[0]==40000
    assert source.execute('SELECT count(DISTINCT security_id) FROM market_daily').fetchone()[0]==30
    assert source.execute('SELECT count(*) FROM sessions').fetchone()[0]==60
    assert not source.execute("SELECT 1 FROM sessions WHERE session_date IN ('2025-04-18','2025-05-26')").fetchone()
    # DST is handled per session, rather than hard-coding every open to 13:30 UTC.
    assert '14:30' in source.execute("SELECT open_at FROM sessions WHERE session_date='2025-03-06'").fetchone()[0]
    assert '13:30' in source.execute("SELECT open_at FROM sessions WHERE session_date='2025-03-10'").fetchone()[0]


def test_real_buy_sell_and_execution_schedule_variety(source):
    assert {r[0] for r in source.execute('SELECT DISTINCT side FROM orders')}=={'buy','sell'}
    assert {r[0] for r in source.execute('SELECT DISTINCT order_type FROM orders')}=={'market','limit'}
    assert source.execute("SELECT count(*) FROM orders WHERE price_limit_role='internal_protection' AND order_type='market'").fetchone()[0]>1000
    twap=source.execute("SELECT order_id FROM orders WHERE execution_strategy='TWAP' AND order_id>'O-0000200' LIMIT 1").fetchone()[0]
    times=[r[0] for r in source.execute('SELECT executed_at FROM fills WHERE order_id=? ORDER BY executed_at',(twap,))]
    from datetime import datetime
    gaps=[(datetime.fromisoformat(b.replace('Z','+00:00'))-datetime.fromisoformat(a.replace('Z','+00:00'))).total_seconds() for a,b in zip(times,times[1:])]
    assert gaps and len(set(gaps))==1


def test_all_scenarios_detected_without_exposing_truth_in_sources(source):
    truth=json.loads((ROOT/'evals/population_truth.json').read_text())
    assert len(truth['episodes'])==96
    assert all(e['detected_alert_ids'] for e in truth['episodes'])
    tables={r[0] for r in source.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert not {'truth','expected_outcomes','scenario_keys'} & tables
    assert source.execute('SELECT count(DISTINCT rule) FROM alerts').fetchone()[0]==8


@pytest.mark.parametrize('remove_table,absent_family',[('venue_orders','spoofing_layering'),('public_events','pre_announcement')])
def test_detection_depends_on_source_records_not_scenario_keys(tmp_path,remove_table,absent_family):
    if not DATABASE.exists():pytest.skip('Generate population first')
    path=tmp_path/'mutation.sqlite3'
    shutil.copyfile(DATABASE,path)
    db=sqlite3.connect(path);db.row_factory=sqlite3.Row
    db.executescript('DELETE FROM case_alerts; DELETE FROM investigation_cases; DELETE FROM alert_features; DELETE FROM alert_orders; DELETE FROM alerts;')
    db.execute(f'DELETE FROM {remove_table}')
    pop=Population.__new__(Population)
    pop.db=db
    pop.truth=[]  # No grading keys available to this rerun.
    try:
        counts=pop.alerts()
        assert absent_family not in counts
        assert sum(counts.values())>0
    finally:db.close()


def test_runtime_data_scope_and_availability(source):
    assert source.execute("SELECT count(*) FROM evidence WHERE status='unavailable'").fetchone()[0]>=8
    assert source.execute('SELECT count(*) FROM execution_matches').fetchone()[0]==72
    # A private message cannot become public merely because its stock ticker is shared.
    message=source.execute("SELECT e.evidence_id,count(s.account_id) scopes FROM evidence e JOIN evidence_scope s USING(evidence_id) WHERE e.kind='communication' GROUP BY e.evidence_id LIMIT 1").fetchone()
    assert message['scopes']==1


def test_generated_mandate_summary_matches_its_execution_window(source):
    import re
    for evidence in source.execute("SELECT content FROM evidence WHERE kind='mandate'"):
        match=re.search(r'^Document (M-[0-9]+):.*execution window (\S+) to (\S+)\. Signed',evidence['content'])
        if match:
            row=source.execute('SELECT window_start,window_end FROM mandates WHERE mandate_id=?',(match[1],)).fetchone()
            assert row and tuple(row)==(match[2],match[3])
