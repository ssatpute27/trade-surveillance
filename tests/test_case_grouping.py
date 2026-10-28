import json
import sqlite3
from collections import Counter
from pathlib import Path
import pytest
from scripts.group_cases import grouped_alerts

ROOT=Path(__file__).resolve().parent.parent


@pytest.fixture
def db():
    path=ROOT/'data/population.sqlite3'
    if not path.exists():pytest.skip('Generate population first')
    c=sqlite3.connect(f'file:{path}?mode=ro',uri=True);c.row_factory=sqlite3.Row
    yield c
    c.close()


def test_each_source_alert_belongs_to_exactly_one_case(db):
    cases=grouped_alerts(db)
    linked=[a['alert_id'] for c in cases for a in c['alerts']]
    assert len(linked)==len(set(linked))==db.execute('SELECT count(*) FROM alerts').fetchone()[0]
    assert len(cases)<len(linked)
    assert db.execute('SELECT count(*) FROM case_alerts').fetchone()[0]==len(linked)


def test_shared_order_signals_stay_in_one_case(db):
    mapping={a['alert_id']:c['case_id'] for c in grouped_alerts(db) for a in c['alerts']}
    for row in db.execute('SELECT order_id,group_concat(alert_id) ids FROM alert_orders GROUP BY order_id HAVING count(*)>1'):
        assert len({mapping[aid] for aid in row['ids'].split(',')})==1


def test_authored_variants_have_expanded_without_exposing_keys(db):
    truth=json.loads((ROOT/'evals/population_truth.json').read_text())
    counts=Counter((e['family'],e['variant']) for e in truth['episodes'])
    assert len(counts)==24
    assert set(counts.values())=={4}
    assert all(e['detected_alert_ids'] for e in truth['episodes'])


def test_size_signals_use_strategy_and_liquidity_context(db):
    rows=db.execute("SELECT features_json FROM alert_features f JOIN alerts a USING(alert_id) WHERE a.rule='size_outlier'").fetchall()
    assert rows
    for row in rows:
        f=json.loads(row[0])
        assert f['prior_parent_orders']>=15
        assert f['cohort_desk']
        assert f['execution_strategy']
        assert f['baseline_cutoff']=='prior completed sessions'
        assert f['ratio']>=6
        assert f['historical_volume_fraction_ratio']>=6
