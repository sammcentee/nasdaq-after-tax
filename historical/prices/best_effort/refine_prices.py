"""Refine the baseline using independently downloaded Yahoo observations.
No gap is filled from a future quote. Primary-issuer repairs take precedence.
"""
from pathlib import Path
import json
import numpy as np
import pandas as pd
import build_prices as b
P=b.P
PRIORITY=['tts-832177','tts-71625495','tts-1947579','tts-831866','tts-832022','tts-203249662']
# Explicitly identified ordinary security continuations. The caller may unify
# duplicate vendor IDs; mapping does not infer that a reused ticker is sameissuer.
MULTI={'FISV':['tts-832260','tts-377137730'],'FOXA':['tts-61149824'],'FOX':['tts-61149825'],'SNDK':['tts-342851559'],'LIFE':['tts-387639951'],'BBBY':['tts-367344332'],'DELL':['tts-157040141'],'CEG':['tts-818716']}
# Not ordinary share splits: Yahoo uses adjustment ratios for spin distributions.
NONCASH={('GOOGL','2014-04-03'),('GOOG','2014-04-03'),('GOOG','2015-04-27'),('EBAY','2015-07-20'),('ADP','2014-10-01'),('CTXS','2017-02-01'),('LBTYA','2014-03-04'),('LBTYA','2015-07-02'),('LBTYA','2016-06-21'),('LBTYA','2024-11-13'),('LBTYK','2015-07-02'),('LBTYK','2016-06-21'),('LBTYK','2024-11-13'),('FLEX','2024-01-03'),('VOD','2014-02-24'),('WDC','2025-02-24'),('MDLZ','2012-10-01'),('CMCSA','2026-01-05'),('HON','2025-10-30'),('HON','2026-06-29'),('T','2022-04-11')}

def main():
 panel=pd.read_csv(P/'prices_usd.csv.gz',parse_dates=['date']);spl=pd.read_csv(P/'split_events.csv');checks=[];maps=[];noncash=[]
 for symbol in sorted(set(a['symbol'] for a in b.MAP.values())):
  q=b.yf_frame(symbol)
  if q is None:continue
  ids=[a['id'] for a in b.MAP.values() if a['symbol']==symbol]
  if len(ids)>1:
   ids=MULTI.get(symbol,[])
  for asset in ids:
   old=panel[panel.security_id==asset].set_index('date')
   if old.empty:continue
   overlap=old[['close_usd']].join(q[['close_usd']],lsuffix='_q',rsuffix='_y',how='inner').dropna()
   ratio=overlap.close_usd_y/overlap.close_usd_q
   if len(ratio)<10:continue
   # Current-price level anchors identity; past adjustments may differ materially.
   tail=ratio.tail(min(60,len(ratio)))
   latest_match=float(tail.median())
   accepted=abs(latest_match-1)<.015
   reason='recent_price_overlap_matches; historical_split_and_spin_factors_audited_separately' if accepted else 'recent_price_mismatch_quarantined'
   checks.append({'symbol':symbol,'security_id':asset,'overlap_days':len(ratio),'min_yahoo_quantiacs':float(ratio.min()),'median_ratio':float(ratio.median()),'last60_median_ratio':latest_match,'max_ratio':float(ratio.max()),'yahoo_dividend_days':int((q.dividend_usd!=0).sum()),'old_dividend_days':int((old.dividend_usd!=0).sum()),'accepted_yahoo':accepted,'reason':reason})
   if not accepted:continue
   y=q.copy();y['security_id']=asset;y['source']='yahoo_via_yfinance_crosschecked';y['quality']='raw_restored_from_yahoo_action_factors; action_and_irish_tax_assumptions_separate'
   # A newly listed same-ticker security may not inherit earlier observations.
   if symbol not in {'FISV','CEG'}:y=y[y.index>=old.index.min()]
   # Keep full Yahoo continuation for live identities even if old source stopped.
   panel=panel[panel.security_id!=asset]
   panel=pd.concat([panel,y[['security_id','close_usd','dividend_usd','source','quality']].reset_index()],ignore_index=True)
   maps.append({'symbol':symbol,'security_id':asset,'first':str(y.index.min().date()),'last':str(y.index.max().date())})
   spl=spl[spl.security_id!=asset]
   for d,v in y.loc[y['Stock Splits']!=0,'Stock Splits'].items():
    row={'date':str(d.date()),'security_id':asset,'ratio':v,'source':'yahoo_split_field','symbol':symbol}
    if (symbol,str(d.date())) in NONCASH:
     noncash.append({**row,'classification':'noncash_adjustment_replaced_by_explicit_entitlement'})
    else:
     spl=pd.concat([spl,pd.DataFrame([row])],ignore_index=True)
 # Re-apply independently calibrated primary repairs after Yahoo overlay.
 repair=pd.read_csv(b.BASE/'repairs/priority_daily_quotes.csv.gz',parse_dates=['date']).rename(columns={'source_asset_id':'security_id','raw_close_usd':'close_usd','cash_dividend_usd_per_share':'dividend_usd'})
 repair=repair[repair.security_id.isin(PRIORITY)];repair['source']='quantiacs_plus_primary_repair'
 for asset in repair.security_id.unique():
  r=repair[repair.security_id==asset];panel=panel[~((panel.security_id==asset)&panel.date.between(r.date.min(),r.date.max()))]
 panel=pd.concat([panel,repair[['date','security_id','close_usd','dividend_usd','source','quality']]],ignore_index=True)
 # Preserve verified missing ordinary splits, without repeating repaired spinoffs.
 ordinary=pd.read_csv(b.BASE/'repairs/priority_corporate_actions.csv')
 ordinary=ordinary[ordinary.action=='ordinary_split']
 for r in ordinary.itertuples():
  spl=spl[~((spl.security_id==r.old_asset_id)&(spl.date==r.economic_date))]
  spl=pd.concat([spl,pd.DataFrame([{'date':r.economic_date,'security_id':r.old_asset_id,'ratio':r.new_shares_per_old_share,'source':'primary_repair_or_source_verified_by_boundary','symbol':r.old_symbol}])],ignore_index=True)
 # Restore single-class quantity effect for Google's 2015 small distribution.
 spl=pd.concat([spl,pd.DataFrame([{'date':'2015-04-27','security_id':'tts-1947579','ratio':1.0027455,'source':'issuer_primary_repair','symbol':'GOOG'}])],ignore_index=True)
 panel=panel.sort_values(['security_id','date']).drop_duplicates(['date','security_id'],keep='last');panel.to_csv(P/'prices_usd.csv.gz',index=False)
 spl=spl.sort_values(['date','security_id']).drop_duplicates(['date','security_id'],keep='last');spl.to_csv(P/'split_events.csv',index=False)
 pd.DataFrame(checks).to_csv(P/'yahoo_quantiacs_crosscheck.csv',index=False)
 pd.DataFrame(maps).to_csv(P/'yahoo_accepted_identity_map.csv',index=False)
 pd.DataFrame(noncash).to_csv(P/'noncash_split_adjustment_candidates.csv',index=False)
 coverage=panel.groupby('security_id').agg(first=('date','min'),last=('date','max'),observations=('date','size'),dividend_days=('dividend_usd',lambda z:(z!=0).sum()),source=('source','last')).reset_index();coverage['symbol']=coverage.security_id.map(lambda z:b.MAP.get(z,{}).get('symbol',z.replace('yahoo:','')));coverage.to_csv(P/'price_coverage.csv',index=False)
 summary={'status':'best-effort raw price panel, not certified market or Irish corporate-action tax data','rows':len(panel),'securities':panel.security_id.nunique(),'yahoo_downloaded_symbols':len(list(P.glob('yf_*.csv'))),'accepted_yahoo_identities':len(maps),'ordinary_split_events':len(spl),'noncash_adjustment_events_removed_from_split_ledger':len(noncash),'source_counts':panel.source.value_counts().to_dict(),'priority_repairs_preserved':PRIORITY,'known_limitations':['Yahoo and Quantiacs can share upstream errors; agreement does not prove accuracy','Yahoo historical Close is split-adjusted and sometimes spin-adjusted; raw restoration uses explicit action factors','Retained successor and spin-off action ledger must be applied separately','Foreign currency listings must not be treated as USD without explicit FX conversion','Unavailable deleted securities remain excluded or separately approximated by the runner; not assigned fabricated prices']};(P/'price_build_summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
