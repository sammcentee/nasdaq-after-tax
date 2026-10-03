"""Economic continuity diagnostics; next quote is audit-only, never trading input."""
from pathlib import Path
import pandas as pd
import numpy as np
P=Path(__file__).parent
p=pd.read_csv(P/'prices_usd.csv.gz',parse_dates=['date']);a=pd.read_csv(P/'actions.csv',parse_dates=['date']);g={s:q.set_index('date').sort_index() for s,q in p.groupby('security_id')}

def quote(s,d,prior=False):
 q=g.get(s)
 if q is None:return float('nan'),''
 q=q[q.index<d] if prior else q[(q.index>=d)&(q.index<=d+pd.Timedelta(days=7))]
 if q.empty:return float('nan'),''
 row=q.iloc[-1] if prior else q.iloc[0]
 return float(row.close_usd),str(row.name.date())
rows=[]
for (d,s),ev in a.groupby(['date','security_id']):
 old,prev=quote(s,d,True);qty=1.;cash=0.;children=[];retain=True;notes=[]
 for r in ev.sort_values('priority').itertuples():
  if r.event_type=='split':qty*=r.ratio
  elif r.event_type=='spinoff':children.append((r.new_security_id,qty*r.ratio));notes.append('child:'+str(r.new_security_id))
  elif r.event_type in ['cash_dividend','contingent_cash']:cash+=qty*r.cash_usd_per_share
  elif r.event_type=='cash_merger':cash+=qty*r.cash_usd_per_share;retain=False
  elif r.event_type in ['stock_exchange','mixed_merger']:
   children.append((r.new_security_id,qty*r.ratio));cash+=qty*r.cash_usd_per_share;retain=False
  elif r.event_type=='worthless':retain=False
 new,nd=quote(s,d)
 total=cash+(qty*new if retain else 0);missing=[]
 for child,cqty in children:
  mark,cd=quote(child,d);total+=cqty*mark
  if not np.isfinite(mark):missing.append(child)
 jump=total/old-1 if old>0 else np.nan
 rows.append(dict(date=str(d.date()),security_id=s,symbol=ev.symbol.iloc[0],events=';'.join(ev.event_type),prior_close=old,prior_date=prev,parent_after_close=new,parent_after_date=nd,parent_after_quantity=qty if retain else 0,cash_usd=cash,total_entitlement_mark=total,economic_return=jump,missing_children=';'.join(missing),large_jump=bool(abs(jump)>.15) if np.isfinite(jump) else False,notes=';'.join(notes)))
out=pd.DataFrame(rows);out.to_csv(P/'action_boundary_audit.csv',index=False)
print(out[out.large_jump|out.missing_children.ne('')].to_string(index=False));print('rows',len(out),'large jumps',out.large_jump.sum(),'missing child marks',out.missing_children.ne('').sum())
