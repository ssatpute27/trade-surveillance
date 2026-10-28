"""Cache public historical quotes; never falls back to invented market data.

Run explicitly to fetch. Sample regeneration reads this cache without network calls.
Yahoo Finance chart data is a convenience source for local demonstration, not an
exchange-certified feed or a grant of redistribution rights.
"""
import concurrent.futures
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parent.parent
SYMBOLS = ['AAPL','MSFT','NVDA','AMZN','GOOGL','META','TSLA','AMD','AVGO','ORCL',
           'JPM','BAC','GS','MS','V','MA','XOM','CVX','UNH','JNJ','PFE','LLY',
           'WMT','COST','HD','PG','KO','CAT','GE','DIS']
START='2025-03-03'
END='2025-05-31'  # Exclusive; May 30 is the last included session.


def fetch(symbol):
    start=int(datetime.fromisoformat(START).replace(tzinfo=timezone.utc).timestamp())
    end=int(datetime.fromisoformat(END).replace(tzinfo=timezone.utc).timestamp())
    url=f'https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?period1={start}&period2={end}&interval=1d'
    response=httpx.get(url,headers={'User-Agent':'TradeSurveillanceDemo/0.1'},timeout=30)
    response.raise_for_status()
    chart=response.json()['chart']
    if chart.get('error') or not chart.get('result'):
        raise ValueError(f'Provider returned no data for {symbol}')
    result=chart['result'][0]
    quotes=result['indicators']['quote'][0]
    bars=[]
    for i,timestamp in enumerate(result['timestamp']):
        fields={k:quotes[k][i] for k in ['open','high','low','close','volume']}
        if any(v is None for v in fields.values()):
            raise ValueError(f'Missing quote field for {symbol} at {timestamp}')
        bars.append({'date':datetime.fromtimestamp(timestamp,timezone.utc).date().isoformat(),**fields})
    if result['meta']['currency']!='USD' or result['meta']['symbol']!=symbol:
        raise ValueError('Unexpected provider identity or currency')
    return {'symbol':symbol,'name':result['meta'].get('longName',symbol),'currency':'USD',
            'provider':'Yahoo Finance chart','source_url':url,
            'fetched_at':datetime.now(timezone.utc).isoformat(),
            'response_sha256':hashlib.sha256(response.content).hexdigest(),
            'price_basis':'provider quote OHLC; adjusted-close field not used',
            'bars':bars}


def main():
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(fetch,SYMBOLS))
    common=set.intersection(*(set(b['date'] for b in r['bars']) for r in results))
    sessions=sorted(common)[-60:]
    if len(sessions)!=60:
        raise ValueError(f'Need 60 shared sessions, found {len(sessions)}')
    output={'scope':'Public historical daily market context; no private trading records',
            'sessions':sessions,'securities':results,
            'limitations':['Daily aggregates do not reveal historical order books, spreads or exact intraday execution prices.',
                           'Provider history may be revised. Cached snapshot and response hashes are retained.',
                           'No exchange-level completeness or redistribution entitlement is asserted.']}
    path=ROOT/'sample'/'market_history.json'
    temp=path.with_suffix('.tmp')
    temp.write_text(json.dumps(output,indent=2)+'\n')
    temp.replace(path)
    print(json.dumps({'securities':len(results),'shared_sessions':len(sessions),
                      'start':sessions[0],'end':sessions[-1],
                      'daily_bars':sum(len(r['bars']) for r in results),'cache':str(path)},indent=2))


if __name__=='__main__':
    main()
