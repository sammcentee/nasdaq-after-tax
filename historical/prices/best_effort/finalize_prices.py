"""Add explicit further successors, remove reused ticker false matches, FX convert.
Run after build_prices.py and refine_prices.py. This file never fetches credentials.
"""
import json
import pandas as pd
import numpy as np
import build_prices as b
P=b.P

def main():
 panel=pd.read_csv(P/'prices_usd.csv.gz',parse_dates=['date']);spl=pd.read_csv(P/'split_events.csv')
 # These current tickers are unrelated to historical Nasdaq constituents.
 bad=['yahoo:GOLD','yahoo:MICC','yahoo:SHLD']
 panel=panel[~panel.security_id.isin(bad)];spl=spl[~spl.security_id.isin(bad)]
 successors={'VAC':'yahoo:VAC','ASIX':'yahoo:ASIX','GTX':'yahoo:GTX','REZI':'yahoo:REZI','SUNN.SW':'yahoo:SUNN.SW','GRAL':'tts-315092541','SOLS':'tts-375502573'}
 fxmanifest=[]
 for symbol,asset in successors.items():
  q=b.yf_frame(symbol)
  if q is None:continue
  q=q.copy();q['security_id']=asset;q['source']='yahoo_via_yfinance';q['quality']='raw_units_restored_from_yahoo_splits'
  if symbol=='SUNN.SW':
   fx=b.yf_frame('CHFUSD=X');rates=fx.close_usd.reindex(q.index,method='ffill')
   # CHF per-share quote/dividend converted to USD on each observation date.
   q['close_usd']*=rates;q['dividend_usd']*=rates;q['quality']='CHF_price_converted_to_USD_same_day_or_prior_Yahoo_FX'
   fxmanifest.append({'security_id':asset,'listing_currency':'CHF','FX_symbol':'CHFUSD=X','method':'latest observed on or before quote date; no future observation','first_date':str(q.index.min().date())})
  panel=panel[panel.security_id!=asset];panel=pd.concat([panel,q[['security_id','close_usd','dividend_usd','source','quality']].reset_index()],ignore_index=True)
  spl=spl[spl.security_id!=asset]
  for d,v in q.loc[q['Stock Splits']!=0,'Stock Splits'].items():spl=pd.concat([spl,pd.DataFrame([{'date':str(d.date()),'security_id':asset,'ratio':v,'source':'yahoo_split_field','symbol':symbol}])],ignore_index=True)
 # Named Yahoo spinoff ratios are used to restore quote units, not to award parent shares.
 NONCASH={('MAR','2011-11-22'),('VIAV','2015-08-04'),('HON','2016-10-03'),('HON','2018-10-01'),('HON','2018-10-29'),('HSIC','2019-02-08'),('DELL','2021-11-02'),('EXC','2022-02-02'),('FWONA','2023-07-20'),('FWONK','2023-07-20'),('ILMN','2024-06-25')}
 mask=spl.apply(lambda r:(r.symbol,r.date) in NONCASH,axis=1)
 noncash=spl[mask].copy();noncash['classification']='noncash_adjustment_replaced_by_explicit_entitlement';existing=pd.read_csv(P/'noncash_split_adjustment_candidates.csv');pd.concat([existing,noncash],ignore_index=True).drop_duplicates(['date','security_id']).to_csv(P/'noncash_split_adjustment_candidates.csv',index=False);spl=spl[~mask]
 panel=panel.sort_values(['security_id','date']).drop_duplicates(['date','security_id']);panel.to_csv(P/'prices_usd.csv.gz',index=False)
 spl=spl.sort_values(['date','security_id']).drop_duplicates(['date','security_id'],keep='last');spl.to_csv(P/'split_events.csv',index=False)
 (P/'foreign_currency_price_manifest.json').write_text(json.dumps(fxmanifest,indent=2))
 coverage=panel.groupby('security_id').agg(first=('date','min'),last=('date','max'),observations=('date','size'),dividend_days=('dividend_usd',lambda z:(z!=0).sum()),source=('source','last')).reset_index();coverage['symbol']=coverage.security_id.map(lambda z:b.MAP.get(z,{}).get('symbol',z.replace('yahoo:','')));coverage.to_csv(P/'price_coverage.csv',index=False)
 summary=json.loads((P/'price_build_summary.json').read_text());summary.update({'rows':len(panel),'securities':panel.security_id.nunique(),'ordinary_split_events':len(spl),'added_successors':successors,'quarantined_reused_tickers':bad,'fx_conversion':fxmanifest,'source_counts':panel.source.value_counts().to_dict()});(P/'price_build_summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
