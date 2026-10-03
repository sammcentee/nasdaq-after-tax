"""Final primary-anchored delisted split repairs and additional successor histories."""
import json
import pandas as pd
import build_prices as b
from primary_price_repairs import crosscheck
P=b.P

def main():
 panel=pd.read_csv(P/'prices_usd.csv.gz',parse_dates=['date']);spl=pd.read_csv(P/'split_events.csv')
 for symbol, canonical_id in [('CRNC','yahoo:CRNC'),('LLYVA','yahoo:LLYVA'),('LLYVK','yahoo:LLYVK'),('VZ','tts-821874'),('MDLZ','tts-51210920'),('CEG','tts-239110702')]:
  q=b.yf_frame(symbol)
  if q is None:continue
  q=q.copy();q['security_id']=canonical_id;q['source']='yahoo_via_yfinance';q['quality']='raw_units_restored_from_yahoo_splits';panel=panel[panel.security_id!=q.security_id.iloc[0]];panel=pd.concat([panel,q[['security_id','close_usd','dividend_usd','source','quality']].reset_index()],ignore_index=True)
 v=crosscheck(panel);repairs=[]
 for asset,start,end in [('tts-29400599','2010-09-01','2013-05-30'),('tts-832025','2010-09-01','2011-06-27'),('tts-832025','2011-06-27','2013-07-01'),('tts-830036','2010-09-01','2019-10-02')]:
  a=v[(v.security_id==asset)&(v.date>=start)&(v.date<end)];factor=float(a.ratio.median());disp=float((a.ratio/factor-1).abs().max())
  if a.empty or disp>.003:raise ValueError((asset,len(a),factor,disp))
  m=(panel.security_id==asset)&(panel.date>=start)&(panel.date<end);panel.loc[m,['close_usd','dividend_usd']]*=factor;panel.loc[m,'quality']='missing_unit_adjustment_restored_from_primary_holdings_prices'
  repairs.append({'security_id':asset,'start':start,'end_exclusive':end,'factor_applied_this_run':factor,'primary_anchors':len(a),'max_relative_anchor_error':disp})
 for asset,symbol,date in [('tts-29400599','WFM','2013-05-30'),('tts-832025','CERN','2011-06-27'),('tts-832025','CERN','2013-07-01')]:
  spl=spl[~((spl.security_id==asset)&(spl.date==date))];spl=pd.concat([spl,pd.DataFrame([{'date':date,'security_id':asset,'ratio':2.,'source':'issuer_verified_split_missing_from_vendor','symbol':symbol}])],ignore_index=True)
 # Parent distributions are successor shares, not cash dividends.
 panel.loc[(panel.security_id=='tts-51210920')&(panel.date=='2012-10-02'),'dividend_usd']=0
 # NUAN distribution is successor shares, not a cash dividend.
 panel.loc[(panel.security_id=='tts-830036')&(panel.date=='2019-10-02'),'dividend_usd']=0
 panel=panel.dropna(subset=['close_usd']).sort_values(['security_id','date']).drop_duplicates(['date','security_id']);panel.to_csv(P/'prices_usd.csv.gz',index=False)
 spl.sort_values(['date','security_id']).to_csv(P/'split_events.csv',index=False)
 v=crosscheck(panel);v.to_csv(P/'issuer_monthly_price_crosscheck.csv',index=False)
 unresolved=v[(v.ratio-1).abs()>.03];unresolved.to_csv(P/'remaining_primary_price_discrepancies.csv',index=False)
 (P/'final_price_adjustments_summary.json').write_text(json.dumps({'repairs':repairs,'primary_crosscheck_observations':len(v),'within_0_1pct':int(((v.ratio-1).abs()<.001).sum()),'within_1pct':int(((v.ratio-1).abs()<.01).sum()),'remaining_over3pct_rows':len(unresolved),'remaining_flags':'QGEN old units; Braves2016 rights; unrelated reusedGENZ ticker (never mapped tooldholding)'},indent=2))
 cov=panel.groupby('security_id').agg(first=('date','min'),last=('date','max'),observations=('date','size'),dividend_days=('dividend_usd',lambda z:(z!=0).sum()),source=('source','last')).reset_index();cov['symbol']=cov.security_id.map(lambda z:b.MAP.get(z,{}).get('symbol',z.replace('yahoo:','')));cov.to_csv(P/'price_coverage.csv',index=False)
 summary=json.loads((P/'price_build_summary.json').read_text());summary.update({'rows':len(panel),'securities':panel.security_id.nunique(),'yahoo_downloaded_symbols':len(list(P.glob('yf_*.csv'))),'source_counts':panel.source.value_counts().to_dict(),'primary_price_observations':len(v),'primary_prices_within1pct':int(((v.ratio-1).abs()<.01).sum()),'remaining_primary_price_flags':len(unresolved),'executable_pipeline':['build_prices.py','refine_prices.py','finalize_prices.py','primary_price_repairs.py','final_price_adjustments.py','audit_action_boundaries.py']});(P/'price_build_summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
