"""Read-only structural checks of the existing historical-market-based dataset."""
import json
from pathlib import Path
import sqlite3
import sys
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from scripts.build_population import Population
from app.config import settings


def inspect():
    with sqlite3.connect('file:'+settings.source_path+'?mode=ro',uri=True) as c:
        c.row_factory=sqlite3.Row
        pop=Population.__new__(Population);pop.db=c
        pop.truth=json.loads((ROOT/'evals/population_truth.json').read_text())['episodes']
        checks=pop.validate(40000,150000)
        checks['no_placeholder_trader_names']=c.execute("SELECT count(*) FROM traders WHERE name LIKE '%Demo-%'").fetchone()[0]==0
        checks['no_placeholder_account_names']=c.execute("SELECT count(*) FROM accounts WHERE name LIKE 'Simulated %'").fetchone()[0]==0
        return {'basis':'Historical daily market context; fictional broker orders, fills, identities and private evidence.',
                'checks':checks,'all_passed':all(checks.values()),
                'orders':c.execute('SELECT count(*) FROM orders').fetchone()[0],
                'executions':c.execute('SELECT count(*) FROM fills').fetchone()[0],
                'securities':c.execute('SELECT count(*) FROM securities').fetchone()[0],
                'date_range':tuple(c.execute('SELECT min(session_date),max(session_date) FROM sessions').fetchone()),
                'order_sides':dict(c.execute('SELECT side,count(*) FROM orders GROUP BY side')),
                'order_types':dict(c.execute('SELECT order_type,count(*) FROM orders GROUP BY order_type')),
                'execution_strategies':dict(c.execute('SELECT execution_strategy,count(*) FROM orders GROUP BY execution_strategy')),
                'alert_families':dict(c.execute('SELECT rule,count(*) FROM alerts GROUP BY rule')),
                'limitations':['Individual orders and executions are not actual transactions.',
                               'Intraday prices and volume paths are generated to match historical daily bars.',
                               'Quotes and order-book detail are curated examples, not a complete market replay.',
                               'Alert thresholds and case mix are illustrative, not validated production surveillance.']}

if __name__=='__main__':
    result=inspect()
    path=ROOT/'output/data_realism_check.json';path.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
    sys.exit(0 if result['all_passed'] else 1)
