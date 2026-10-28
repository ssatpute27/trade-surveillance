"""Versioned plotting recipe executed inside OpenAI Code Interpreter, never as an app fallback."""
import json
from collections import defaultdict
from datetime import datetime,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd
from matplotlib.ticker import FuncFormatter


def main():
    root=Path('/mnt/data')
    data=json.loads(next(root.glob('*case_activity.json')).read_text())
    # This pandas implementation is checked by the server's separate row-based implementation.
    frame=pd.DataFrame(data['fills'])
    frame['ts']=pd.to_datetime(frame['executed_at'],utc=True)
    frame['minute_et']=frame['ts'].dt.tz_convert('America/New_York').dt.strftime('%Y-%m-%d %H:%M')
    frame['session_day']=frame['ts'].dt.tz_convert('America/New_York').dt.strftime('%Y-%m-%d')
    close_map={row['session_date']:row['close_at'] for row in data['sessions']}
    closes=pd.to_datetime(frame['session_day'].map(close_map),utc=True)
    if closes.isna().any():raise ValueError('Execution date has no exchange session')
    in_last=(frame['ts']>=closes-pd.Timedelta(minutes=5))&(frame['ts']<=closes)
    frame['buy_shares']=frame['quantity'].where(frame['side']=='buy',0)
    frame['sell_shares']=frame['quantity'].where(frame['side']=='sell',0)
    buckets=frame.groupby('minute_et',sort=True).agg(buy_shares=('buy_shares','sum'),sell_shares=('sell_shares','sum'),fill_count=('fill_id','size')).reset_index()
    total=int(frame['quantity'].sum());late=int(frame.loc[in_last,'quantity'].sum())
    venue_count=len(data['venue_orders']);cancelled=sum(row['cancelled_at'] is not None for row in data['venue_orders'])
    metrics={'case_id':data['case_id'],'fill_count':len(frame),'total_shares':total,
             'buy_shares':int(frame['buy_shares'].sum()),'sell_shares':int(frame['sell_shares'].sum()),
             'notional_cents':int((frame['quantity']*frame['price_cents']).sum()),
             'last_five_minutes_shares':late,'last_five_minutes_pct':100*late/total,
             'venue_order_count':venue_count,'cancelled_venue_order_count':cancelled,
             'venue_cancellation_pct':100*cancelled/venue_count if venue_count else None,
             'minute_buckets':buckets.to_dict(orient='records')}
    (root/'analysis.json').write_text(json.dumps(metrics,indent=2))
    tz=ZoneInfo('America/New_York')
    parse=lambda s:datetime.fromisoformat(s.replace('Z','+00:00')).astimezone(tz)
    fills=sorted(data['fills'],key=lambda r:r['executed_at'])
    minutes=[datetime.strptime(r['minute_et'],'%Y-%m-%d %H:%M').replace(tzinfo=tz) for r in metrics['minute_buckets']]
    events=sorted(data['events'],key=lambda r:r['at'])[:3]
    times=minutes+[parse(r['executed_at']) for r in fills]+[parse(r['at']) for r in events]
    times += [parse(r['submitted_at']) for r in data['venue_orders']]
    times += [parse(r['cancelled_at']) for r in data['venue_orders'] if r['cancelled_at']]
    start=min(times)-timedelta(minutes=1);end=max(times)+timedelta(minutes=1)
    plt.rcParams.update({'font.size':11,'axes.titlesize':12,'axes.labelsize':11,'legend.fontsize':10})
    fig,(upper,lower)=plt.subplots(2,1,figsize=(11,7),sharex=True,gridspec_kw={'height_ratios':[1.2,1]})
    fig.subplots_adjust(left=.12,right=.97,top=.87,bottom=.17,hspace=.28)
    x=mdates.date2num(minutes)
    buy=[r['buy_shares'] for r in metrics['minute_buckets']]
    sell=[r['sell_shares'] for r in metrics['minute_buckets']]
    # Matplotlib datetime bar widths are DAYS, not minutes.
    minute_days=1/(24*60)
    upper.bar(x,buy,width=.72*minute_days,color='#16766e',label='Buy shares',zorder=3)
    upper.bar(x,sell,bottom=buy,width=.72*minute_days,color='#c99634',label='Sell shares',zorder=3)
    upper.set_title('Executed shares by minute',loc='left',pad=10)
    upper.set_ylabel('Executed shares');upper.set_ylim(bottom=0)
    upper.legend(loc='upper right',framealpha=.95)
    for i,event in enumerate(events):
        at=mdates.date2num(parse(event['at']))
        upper.axvline(at,color='#6a7f86',linestyle='--',linewidth=1.2,zorder=2)
        label=('Recorded call' if 'Recorded call' in event['label'] else event['label'])+' · '+parse(event['at']).strftime('%H:%M')
        near_right=at>mdates.date2num(start)+.65*(mdates.date2num(end)-mdates.date2num(start))
        upper.text(at+(-.15 if near_right else .15)*minute_days,(.78 if near_right else .94)-i*.12,label,transform=upper.get_xaxis_transform(),
                   fontsize=9,va='top',ha='right' if near_right else 'left',bbox={'facecolor':'white','edgecolor':'none','alpha':.9,'pad':2})
    if data['venue_orders']:
        submissions=defaultdict(int);cancels=defaultdict(int)
        for row in data['venue_orders']:
            submissions[parse(row['submitted_at']).replace(second=0,microsecond=0)]+=1
            if row['cancelled_at']:cancels[parse(row['cancelled_at']).replace(second=0,microsecond=0)]+=1
        keys=sorted(set(submissions)|set(cancels));xv=mdates.date2num(keys)
        lower.bar(xv-.18*minute_days,[submissions[k] for k in keys],width=.32*minute_days,color='#16766e',label='Submitted')
        lower.bar(xv+.18*minute_days,[cancels[k] for k in keys],width=.32*minute_days,color='#c99634',label='Cancelled')
        lower.set_title('Supplied venue orders by minute',loc='left',pad=10);lower.set_ylabel('Venue order count')
        lower.legend(loc='upper right');lower.set_ylim(bottom=0)
    else:
        cumulative=[0];points=[start]
        for row in fills:
            cumulative.append(cumulative[-1]+row['quantity']);points.append(parse(row['executed_at']))
        points.append(end);cumulative.append(cumulative[-1])
        lower.step(points,cumulative,where='post',color='#16766e',linewidth=2)
        lower.set_title('Cumulative executed shares',loc='left',pad=10)
        lower.set_ylabel('Executed shares');lower.set_ylim(bottom=0)
    for axis in (upper,lower):
        axis.set_xlim(start,end)
        axis.yaxis.set_major_formatter(FuncFormatter(lambda value,_:f'{value:,.0f}'))
        axis.grid(axis='y',color='#e2e8e8',linewidth=.7,zorder=0)
        axis.spines['top'].set_visible(False);axis.spines['right'].set_visible(False)
    lower.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=4,maxticks=8))
    lower.xaxis.set_major_formatter(mdates.DateFormatter('%b %d\n%H:%M',tz=tz))
    lower.set_xlabel('Eastern time',labelpad=8)
    symbols=', '.join(sorted({r['security_id'] for r in data['fills']}))
    fig.suptitle(f"{data['case_id']} · {symbols}\nCase execution pattern",fontsize=15,y=.97)
    fig.text(.5,.035,'Linked case activity; timing does not establish intent',ha='center',fontsize=9,color='#64787d')
    fig.savefig(root/'execution_pattern.png',dpi=140,facecolor='white')
    plt.close(fig)


if __name__=='__main__':main()
