"""Extend same legal security through verified ticker changes, no taxable disposal."""
import hashlib,json
import pandas as pd
import numpy as np
import build_prices as b
P=b.P

def main():
 panel=pd.read_csv(P/'prices_usd.csv.gz',parse_dates=['date']);old=panel[panel.security_id=='tts-12361625'].set_index('date').sort_index();q=b.yf_frame('ECHO');assert q is not None
 overlap=old[['close_usd']].join(q[['close_usd']],how='inner',lsuffix='_sats',rsuffix='_echo');recent=overlap.loc['2026-01-01':'2026-06-22'];relative=(recent.close_usd_echo/recent.close_usd_sats-1).abs();assert len(recent)>50 and relative.quantile(.99)<.005
 q=q[q.index>='2026-06-23'].copy();q['security_id']='tts-12361625';q['source']='yahoo_ECHO_verified_SATS_ticker_continuation';q['quality']='same_CUSIP_verified_issuer; recent_overlap_matches; no_quantity_change'
 panel=panel[~((panel.security_id=='tts-12361625')&(panel.date>='2026-06-23'))];panel=panel[panel.security_id!='yahoo:ECHO'];panel=pd.concat([panel,q[['security_id','close_usd','dividend_usd','source','quality']].reset_index()],ignore_index=True);panel=panel.dropna(subset=['close_usd']).sort_values(['security_id','date']).drop_duplicates(['date','security_id'])
 for symbol in ['GLIBK','LILAP']:
  child=b.yf_frame(symbol)
  if child is None:continue
  child=child.copy();child['security_id']='yahoo:'+symbol;child['source']='yahoo_via_yfinance';child['quality']='new_successor_identity_from_listing_date; raw_share_units'
  panel=panel[panel.security_id!=child.security_id.iloc[0]];panel=pd.concat([panel,child[['security_id','close_usd','dividend_usd','source','quality']].reset_index()],ignore_index=True)
 panel=panel.dropna(subset=['close_usd']).sort_values(['security_id','date']).drop_duplicates(['date','security_id']);panel.to_csv(P/'prices_usd.csv.gz',index=False)
 manifest={'security_id':'tts-12361625','old_symbol':'SATS','new_symbol':'ECHO','legal_effective_date':'2026-06-24','first_extended_quote':'2026-06-23','source':'https://ir.echostar.com/news-releases/news-release-details/echostar-changing-stocker-ticker-sats-echo-marking-companys-next','price_source':'Yahoo via yfinance ECHO','quantity_ratio':1,'comparison_observations_2026':len(recent),'p99_relative_close_difference':float(relative.quantile(.99)),'new_observations':len(q),'first_extended_close_usd':float(q.close_usd.iloc[0]),'last_close_usd':float(q.close_usd.iloc[-1])};(P/'ticker_continuation_audit.json').write_text(json.dumps(manifest,indent=2))
 cov=panel.groupby('security_id').agg(first=('date','min'),last=('date','max'),observations=('date','size'),dividend_days=('dividend_usd',lambda z:(z!=0).sum()),source=('source','last')).reset_index();cov['symbol']=cov.security_id.map(lambda z:b.MAP.get(z,{}).get('symbol',z.replace('yahoo:','')));cov.to_csv(P/'price_coverage.csv',index=False)
 summary=json.loads((P/'price_build_summary.json').read_text());summary.update({'rows':len(panel),'securities':panel.security_id.nunique(),'yahoo_downloaded_symbols':len(list(P.glob('yf_*.csv'))),'source_counts':panel.source.value_counts().to_dict(),'verified_same_security_continuation':manifest});(P/'price_build_summary.json').write_text(json.dumps(summary,indent=2))
 assert not panel[['close_usd','dividend_usd']].isna().any().any();assert (panel.close_usd>0).all();assert not panel.duplicated(['date','security_id']).any()
 validation={'rows':len(panel),'securities':panel.security_id.nunique(),'null_prices_or_dividends':0,'nonpositive_prices':0,'duplicate_date_security_rows':0,'price_sha256':hashlib.sha256((P/'prices_usd.csv.gz').read_bytes()).hexdigest(),'status':'structural integrity checks passed; corporate action and source accuracy limitations remain'};(P/'price_validation.json').write_text(json.dumps(validation,indent=2));print(json.dumps(validation,indent=2))
if __name__=='__main__':main()
