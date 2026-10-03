"""Validate contemporaneous price units against issuer holdings and restore hidden factors.
All factors repair vendor quote units; they never choose investments or returns.
"""
from pathlib import Path
import json
import pandas as pd
import numpy as np
import build_prices as b
P=b.P

def crosscheck(panel):
 a=pd.DataFrame(list(b.MAP.values()))[['symbol','id']].rename(columns={'id':'security_id'})
 x=pd.read_csv(P.parent.parent/'membership/cndx_monthly_holdings.csv');x=x[(x.marketCurrencyCode=='USD')&(x.unitPrice>0)].copy();x['date']=pd.to_datetime(x.date.astype(str),format='%Y%m%d');x['symbol']=x.ticker.str.rstrip('*');x=x[['date','symbol','unitPrice']].rename(columns={'unitPrice':'issuer_close'});x['source']='iShares_CNDX_monthly_holdings'
 z=pd.read_csv(P.parent.parent/'membership/qqq_2010_2013_annual_weights.csv',parse_dates=['date']);z['issuer_close']=z.value_usd/z.shares;z=z.rename(columns={'ticker':'symbol'});z['source']='Invesco_QQQ_annual_primary_holdings';z=z[['date','symbol','issuer_close','source']]
 # Old NWSA is pre-2013 original News Corp, not post-spin News Corp.
 z.loc[(z.symbol=='NWSA')&(z.date<'2013-07-01'),'symbol']='FOXA_OLD'
 a=pd.concat([a,pd.DataFrame([{'symbol':'FOXA_OLD','security_id':'tts-161284560'}])],ignore_index=True)
 anchors=pd.concat([x,z],ignore_index=True).merge(a,on='symbol')
 # Quotes may precede weekend reporting dates, with at most 5-calendar-day lag.
 combined=[]
 for sid,anchors_sid in anchors.groupby('security_id'):
  q=panel[panel.security_id==sid][['date','close_usd']].sort_values('date')
  if q.empty:continue
  matched=pd.merge_asof(anchors_sid.sort_values('date'),q,on='date',direction='backward',tolerance=pd.Timedelta(days=5));combined.append(matched)
 v=pd.concat(combined,ignore_index=True).dropna(subset=['close_usd']).rename(columns={'close_usd':'vendor_raw_close'});v['ratio']=v.issuer_close/v.vendor_raw_close
 return v

def main():
 panel=pd.read_csv(P/'prices_usd.csv.gz',parse_dates=['date'])
 # New retained children; HONA/SOLS already use stable native IDs.
 for symbol,asset in [('VSNT','yahoo:VSNT'),('HONA','tts-410496110')]:
  q=b.yf_frame(symbol)
  if q is None:continue
  q=q.copy();q['security_id']=asset;q['source']='yahoo_via_yfinance';q['quality']='raw_units_restored_from_yahoo_splits';panel=panel[panel.security_id!=asset];panel=pd.concat([panel,q[['security_id','close_usd','dividend_usd','source','quality']].reset_index()],ignore_index=True)
 v=crosscheck(panel);v.to_csv(P/'issuer_price_crosscheck_before_repairs.csv',index=False)
 repairs=[]
 for asset,cutoff,symbol in [('tts-828516','2017-02-01','CTXS'),('tts-3103596','2014-08-07','DISCA'),('tts-161284560','2013-07-01','FOXA_OLD')]:
  rows=v[(v.security_id==asset)&(v.date<cutoff)]
  factor=float(rows.ratio.median());disp=float((rows.ratio/factor-1).abs().max())
  if len(rows)<3 or disp>.003:raise ValueError(f'Primary price anchors do not establish a constant factor: {symbol}, {len(rows)}, {factor}, {disp}')
  # Idempotent: current data already at correct raw level needs no rescaling.
  mask=(panel.security_id==asset)&(panel.date<cutoff)
  panel.loc[mask,['close_usd','dividend_usd']]*=factor
  panel.loc[mask,'quality']='hidden_spin_factor_restored_from_multiple_primary_issuer_price_anchors'
  repairs.append({'security_id':asset,'symbol':symbol,'before':cutoff,'factor_applied_this_run':factor,'primary_anchors':len(rows),'max_relative_anchor_error':disp,'method':'constant vendor unit factor calibrated to actual contemporaneous issuer portfolio prices, no return-fitting'})
 # Discovery classC ordinary2-for-1 omitted fromsourcefactor. Primaryholderterms
 # and A-class raw price anchors independently identify the matching unit error.
 asset='tts-15427298';date=pd.Timestamp('2014-08-07');m=(panel.security_id==asset)&(panel.date<date)
 before=panel.loc[m].sort_values('date').iloc[-1].close_usd
 after=panel[(panel.security_id==asset)&(panel.date==date)].close_usd.iloc[0]
 factor=2.0 if before/after<1.4 else 1.0
 panel.loc[m,['close_usd','dividend_usd']]*=factor;panel.loc[m,'quality']='issuer_verified_classC_2_for_1_missing_from_vendor_split_factor'
 repairs.append({'security_id':asset,'symbol':'DISCK','before':'2014-08-07','factor_applied_this_run':factor,'primary_source':'https://ir.corporate.discovery.com/stock-information/cost-basis-and-debt-information/series-c-dividend/default.aspx'})
 # These source cash fields are stock entitlements, not dividends paid as cash.
 removed=[]
 for asset,date in [('tts-15427298','2014-08-07'),('tts-3103596','2014-08-07'),('tts-828516','2017-02-01')]:
  mask=(panel.security_id==asset)&(panel.date==date)
  removed.append({'security_id':asset,'date':date,'source_dividend_removed':float(panel.loc[mask,'dividend_usd'].sum())});panel.loc[mask,'dividend_usd']=0
 panel=panel.sort_values(['security_id','date']).drop_duplicates(['date','security_id']);panel.to_csv(P/'prices_usd.csv.gz',index=False)
 after=crosscheck(panel);after.to_csv(P/'issuer_monthly_price_crosscheck.csv',index=False)
 audit={'repairs':repairs,'noncash_dividends_removed':removed,'primary_price_observations':len(after),'relative_error_within_0_1pct':int(((after.ratio-1).abs()<=.001).sum()),'relative_error_within_1pct':int(((after.ratio-1).abs()<=.01).sum()),'remaining_over_3pct':int(((after.ratio-1).abs()>.03).sum())};(P/'primary_price_repair_summary.json').write_text(json.dumps(audit,indent=2));print(json.dumps(audit,indent=2))
 coverage=panel.groupby('security_id').agg(first=('date','min'),last=('date','max'),observations=('date','size'),dividend_days=('dividend_usd',lambda z:(z!=0).sum()),source=('source','last')).reset_index();coverage['symbol']=coverage.security_id.map(lambda z:b.MAP.get(z,{}).get('symbol',z.replace('yahoo:','')));coverage.to_csv(P/'price_coverage.csv',index=False)
if __name__=='__main__':main()
