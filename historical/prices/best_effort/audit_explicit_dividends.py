"""Read-only audit: identify explicit action dividends also present in vendor panel."""
from pathlib import Path
import pandas as pd
P=Path(__file__).parent
p=pd.read_csv(P/'prices_usd.csv.gz',parse_dates=['date']);a=pd.read_csv(P/'actions.csv',parse_dates=['date'])
rows=[]
for r in a[a.event_type.isin(['cash_dividend','contingent_cash'])].itertuples():
 q=p[(p.security_id==r.security_id)&(p.dividend_usd!=0)&(p.date.between(r.date-pd.Timedelta(days=40),r.date+pd.Timedelta(days=40)))]
 if q.empty:rows.append({'action_date':r.date,'security_id':r.security_id,'symbol':r.symbol,'action_amount':r.cash_usd_per_share,'provider_date':'','provider_dividend_usd':0.,'day_offset':'','comparison':'no provider dividend within +/-40 calendar days'})
 else:
  for v in q.itertuples():rows.append({'action_date':r.date,'security_id':r.security_id,'symbol':r.symbol,'action_amount':r.cash_usd_per_share,'provider_date':v.date,'provider_dividend_usd':v.dividend_usd,'day_offset':(v.date-r.date).days,'comparison':'same-day duplicate' if v.date==r.date else 'nearby date: investigate event identity'})
out=pd.DataFrame(rows);out.to_csv(P/'explicit_dividend_duplicate_audit.csv',index=False);print(out[out.provider_dividend_usd!=0].to_string(index=False));print('explicitactions',len(a[a.event_type.isin(['cash_dividend','contingent_cash'])]))
