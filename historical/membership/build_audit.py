import csv,hashlib,json,pathlib,subprocess,datetime
import pandas as pd
P=pathlib.Path(__file__).parent
s=pd.read_csv(P/'nasdaq100_membership_snapshots.csv');s.date=pd.to_datetime(s.date)
e=pd.read_csv(P/'nasdaq100_membership_events.csv').fillna('')
h=pd.read_csv(P/'cndx_monthly_holdings.csv');a=pd.read_csv(P/'cndx_archive_audit.csv')
q=pd.read_csv(P/'qqq_2010_2013_annual_weights.csv')
initial=set(s[s.date<='2010-10-01'].iloc[-1].tickers.split(','))
assert initial==set(q[q.date=='2010-09-30'].ticker)
assert len(initial)==100
assert len(q)==400
assert all(abs(g.equity_weight.sum()-1)<1e-9 for _,g in q.groupby('date'))
checks=[]
for date,add,remove,source in [
 ('2010-12-20','AKAM CTRP DLTR FFIV MU NFLX WFMI','CTAS DISH FWLT HOLX JBHT LOGI PDCO','https://ir.nasdaq.com/node/69796'),
 ('2011-12-19','AVGO FOSL GOLD HANS NUAN','FLIR ILMN NIHD QGEN URBN','https://ir.nasdaq.com/static-files/d92a5d2e-9eda-467e-831f-25db4e9ff1a6'),
 ('2013-12-23','DISH ILMN NXPI TRIP TSCO','FOSL MCHP NUAN SHLD XRAY','https://ir.nasdaq.com/static-files/07d71061-d890-419b-ba4e-3ed37b6b9495')]:
 row=e[e.date==date].iloc[0]
 ok=set(row.additions.split(','))==set(add.split()) and set(row.removals.split(','))==set(remove.split())
 assert ok
 checks.append(dict(date=date,source=source,status='all additions and removals match primary Nasdaq announcement'))
valid=a[a.status=='valid'];missing=a[a.status!='valid']
sources={
 'qqq_20100930':'https://www.sec.gov/Archives/edgar/data/1067839/000110465910064790/a10-18275_1n30b2.htm',
 'qqq_20110930':'https://www.sec.gov/Archives/edgar/data/1067839/000110465912003105/a11-28102_1n30b2.htm',
 'qqq_20120930':'https://www.sec.gov/Archives/edgar/data/1067839/000110465913005075/a12-24340_1n30b2.htm',
 'qqq_20130930':'https://www.sec.gov/Archives/edgar/data/1067839/000110465914003107/a13-21957_1n30b2.htm',
 '2011_special_rebalance':'https://ir.nasdaq.com/node/70891',
 'cndx_product':'https://www.ishares.com/uk/individual/en/products/253741/ishares-nasdaq-100-ucits-etf',
 'cndx_archive_example':'https://www.blackrock.com/varnish-api/uk-retail01-product-data/product-data/api/v2/get-product-data?appSubType=ISHARES&appType=PRODUCT_PAGE&component=holdings.all&locale=en_GB&portfolioId=253741&targetSite=ishares-uk&userType=individual&excludeContent=true&includeConfig=true&asOfDate=20150930'}
report={
 'status':'AUDIT CORPUS ONLY — not a complete executable historical direct-stock backtest',
 'retrieved_on':'2026-10-03',
 'membership':{
  'source':'https://github.com/jmccarrell/n100tickers','commit':'cf7c89419941316ff8523726ccba136125f2c11c','license':'MIT',
  'source_provenance':'Community reconstruction from Wikipedia historical component-change records, with manually patched historical tickers; not Nasdaq-certified.',
  'source_claimed_coverage':'2007-02-01 through at least 2026-09-26',
  'exported_coverage':'2010-01-01 through last change 2026-09-14; as-of lookup supports 2026-09-30',
  'snapshot_rows':len(s),'dated_event_rows':len(e),'unique_ticker_labels':len(set(t for row in s.tickers for t in row.split(','))),
  'initial_oct2010_count':100,'initial_membership_primary_validation':'All 100 names/tickers agree with QQQ September 30, 2010 audited holdings.',
  'cross_year_continuity':'No January 1 discontinuities after applying prior-year changes.',
  'primary_sample_checks':checks,
  'known_limitations':['CMCSK explicitly omitted in source despite being a genuine share class in the index in 2014–15.','LVNTA appears in primary CNDX holdings from October 2014 while the source list lacks it.','Index-addition and removal events do not supply merger, spinoff, cash-consideration or liquidation terms for retained holdings.','Tickers are labels, not stable security IDs. Old SNDK, DELL, ALTR and others must not automatically map to reused modern tickers.','Removal from index must stop future purchases, not automatically sell existing holdings, under the requested rule.']},
 'primary_monthly_weights':{
  'source':'BlackRock CNDX physical Nasdaq-100 ETF historical holdings JSON','source_url':sources['cndx_archive_example'],
  'earliest_valid':'2014-01-31','last_valid':'2026-09-30','valid_snapshots':len(valid),'total_requested_monthends':len(a),'missing_snapshots':len(missing),
  'missing_before_2014':len(missing[missing.requested<20140131]),'missing_within_supported_period':[str(x) for x in missing[missing.requested>=20140131].requested],
  'holding_rows':len(h),'equity_rows':int((h.assetClass=='Equity').sum()),
  'validation':'Accepted only if response asOfDate exactly equals request and ticker.value is a nonempty list. This rejects silent current-date fallback.',
  'known_limitations':['These are actual historical fund weights, not the official index weights; cash/derivatives and tracking differences exist.','Some early symbols are retrospectively relabeled or use non-US exchange symbols. Examples: GOOGL before April 2014, AABA for Yahoo in 2014, QRTEA for LINTA/QVCA, and INCO for Intel. Join by dated ISIN/security identity, not raw ticker.','Point-in-time publication timestamps are not included. Prior month-end weights are a reasonable stated lag assumption for next-month purchases but exact publication availability is not proven.','Jan–Jun 2017 monthly holdings are missing. Nearby-day requests also returned no holdings.','The generic fundDownloadV2 XLS accepts asOfDate but left its holdings on current date; do not use that endpoint to infer historical weights.','The old .ajax CSV endpoint returns HTML with status200; those responses are invalid.'],
  'github_vs_primary_raw_ticker_matches':100,'github_vs_primary_comparisons':147,
  'equity_weight_percent_min':float(h[h.assetClass=='Equity'].groupby('date').holdingPercent.sum().min()),'equity_weight_percent_max':float(h[h.assetClass=='Equity'].groupby('date').holdingPercent.sum().max())},
 'early_primary_weights':{
  'source':'QQQ annual reports filed with SEC','dates':['2010-09-30','2011-09-30','2012-09-30','2013-09-30'],'rows':400,
  'sum_of_holdings_matches_reported_total':True,
  'total_investment_usd':{'2010-09-30':21232784912,'2011-09-30':21485139915,'2012-09-30':34622078740,'2013-09-30':38231088980},
  'apple_20100930_equity_weight':float(q[(q.date=='2010-09-30')&(q.ticker=='AAPL')].equity_weight.iloc[0]),
  'known_limitations':['Annual weights are sparse. Interpolating future weights would introduce lookahead; simply drifting weights would miss intervening rebalances.','The 2011-05-02 Nasdaq special rebalance materially changed weights. Membership did not change; ignoring it makes the reconstructed allocation wrong.','The annual reports were published after period end (2010 report audited December23; 2011/12/13 reports published following January). They prove holdings at historical dates, but are not themselves publication-timely signals for purchases immediately after those dates.','No full monthly weight sequence for October2010–December2013 was recovered.']},
 'backtest_conclusion':'Full requested direct-stock return should not be reported as validated: historical monthly weights remain incomplete, early ticker identities need reconciliation, and retained departed stocks require separately vetted prices, distributions and corporate-action terms.',
 'sources':sources}
(P/'membership_coverage_audit.json').write_text(json.dumps(report,indent=2))
files=['nasdaq100_membership_snapshots.csv','nasdaq100_membership_events.csv','cndx_monthly_holdings.csv','cndx_archive_audit.csv','membership_vs_primary_holdings_audit.csv','qqq_20100930_weights.csv','qqq_2010_2013_annual_weights.csv']
(P/'artifact_sha256.json').write_text(json.dumps({n:hashlib.sha256((P/n).read_bytes()).hexdigest() for n in files},indent=2))
print(json.dumps({k:report[k] for k in ['status','early_primary_weights']},indent=2))
print('CNDX:',len(valid),'valid;',len(missing),'missing;',len(h),'rows')
