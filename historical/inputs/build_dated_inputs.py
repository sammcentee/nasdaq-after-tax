"""Build availability-aware source weights; unresolved prices remain explicit.

This does not certify an executable backtest. Run from any working directory.
"""
from pathlib import Path
from difflib import SequenceMatcher
from hashlib import sha256
import json
import re

import numpy as np
import pandas as pd
from bs4 import BeautifulSoup
from pypdf import PdfReader

P = Path(__file__).resolve().parent
H = P.parent
assets = pd.read_csv(H / 'prices/quantiacs_asset_coverage.csv').fillna('')
by_symbol = {s: g.to_dict('records') for s, g in assets.groupby('symbol')}
by_id = assets.set_index('id').to_dict('index')
monthly = pd.read_csv(H / 'membership/cndx_monthly_holdings.csv').fillna('')
monthly = monthly[monthly.assetClass == 'Equity'].copy()
monthly['date'] = pd.to_datetime(monthly.date.astype(str)).dt.strftime('%Y-%m-%d')
annual = pd.read_csv(H / 'membership/qqq_2010_2013_annual_weights.csv').fillna('')
sec = json.loads((P / 'qqq_sec_submissions.json').read_text())['filings']['recent']

def norm(x):
    return re.sub('[^a-z]', '', str(x).lower())

# Historical labels, not permission to replace a corporate-action ledger.
aliases = {'AAPL*':'AAPL','4XS':'ESRX','FB*':'META','FB':'META',
           'QCI':'QCOM','INCO':'INTC','ILU':'ILMN','VX1':'VRTX','KTF':'MDLZ',
           'GGQ7':'GOOG','ERTS':'EA','JOYG':'JOY','PCLN':'BKNG',
           'LINTA':'QRTEA','QVCA':'QRTEA','RIMM':'BB','WFMI':'WFM',
           'CTRP':'TCOM','SYMC':'NLOK','HANS':'MNST'}

def resolve(ticker, date, name='', isin=''):
    """Return a conservative vendor join or a stable unresolved source identity."""
    original = ticker
    symbol = aliases.get(ticker, ticker)
    if ticker == 'GOOG' and date < '2014-04-03':
        symbol = 'GOOGL'
    candidates = by_symbol.get(symbol, [])
    # Source identity overrides prevent security/ticker reuse collisions.
    selected = None
    method = 'name_symbol_date_consistent_candidate'
    notes = ''
    explicit = {'DTV':'tts-12035732', 'CA':'tts-14011355', 'SPLS':'tts-820309',
                'GENZ':'tts-829049','BBBY':'tts-827919','FISV':'tts-832260',
                'META':'tts-222568848','CEG':'tts-239110702'}
    if symbol == 'DELL':
        explicit[symbol] = 'tts-828600' if date < '2014-01-01' else 'tts-157040141'
    if symbol == 'SNDK':
        explicit[symbol] = 'tts-830518' if date < '2020-01-01' else 'tts-342851559'
    if symbol in explicit:
        selected = explicit[symbol]
        method = 'dated_reuse_or_duplicate_resolved_candidate'
    elif symbol in {'ALTR', 'LIFE'}:
        notes = 'Vendor name contradicts historical issuer; price history needs independent confirmation.'
    elif symbol in {'FOXA','FOX'} and date < '2019-03-19':
        # TFCFA is only a candidate for old class A; the old class B is absent.
        notes = 'Pre-2019 Twenty-First Century Fox is not post-2019 Fox Corporation.'
    elif len(candidates) == 1:
        selected = candidates[0]['id']
    elif len(candidates) > 1:
        overlapping = [a for a in candidates if a['first_price'] <= max(date,'2010-09-01') <= a['last_price']]
        if len(overlapping) == 1:
            selected = overlapping[0]['id']
            method = 'unique_dated_candidate'
    if selected:
        a = by_id[selected]
        # Absence of a 2009 history is a price issue, not an identity mismatch.
        comparison_date = max(date, '2010-09-01')
        if not (a['first_price'] <= comparison_date <= a['last_price']):
            notes = 'Selected historical issuer has no price on this source date.'
        if original != symbol:
            method = 'historical_alias_candidate'
        # The crosswalk is not independent proof of all corporate continuity.
        return selected, selected, method, notes, '|'.join(a['id'] for a in candidates)
    candidate_ids = '|'.join(a['id'] for a in candidates)
    if symbol == 'FOXA' and date < '2019-03-19':
        candidate_ids = 'tts-161284560'
    if not isin:
        # These are historical legal securities, not current reused symbols.
        # They connect annual and monthly source rows without pretending prices exist.
        historical_isins = {'ALTR':'US0214411003','KRFT':'US50076Q1067',
                            'YHOO':'US9843321061','AABA':'US9843321061',
                            'VIP':'US92719A1060','WLTW':'IE00BDB6Q211',
                            'LILA':'GB00BTC0M714','LILAK':'GB00BTC0MD78',
                            'SOLS':'US83443Q1031'}
        if original in {'FOXA','FOX'} and date < '2019-03-19':
            isin = 'US90130A1016' if original == 'FOXA' else 'US90130A2006'
        elif original in {'LMCA','LMCK'}:
            isin = ({'LMCA':'US5312291025','LMCK':'US5312293005'} if date < '2016-04-18'
                    else {'LMCA':'US5312298707','LMCK':'US5312298541'})[original]
        else:
            isin = historical_isins.get(original,'')
    identity = 'isin:' + isin if isin else 'unresolved:' + original
    return identity, '', 'unresolved_identity', notes or 'No unique defensible vendor identity in local corpus.', candidate_ids

# Recover the last SEC holdings report available before the requested start.
soup = BeautifulSoup((P / 'qqq_20090930_report.html').read_text(), 'html.parser')
initial = []
name_map = json.loads((H / 'membership/qqq_name_ticker_mapping_initial.json').read_text())
manual = {'DIRECTV Group, Inc./The':'DTV','Express Scripts, Inc.':'ESRX',
          'Baidu, Inc.':'BIDU','Juniper Networks, Inc.':'JNPR',
          'Steel Dynamics, Inc.':'STLD','Ryanair Holdings PLC':'RYAAY',
          'Hansen Natural Corp.':'HANS','Akamai Technologies, Inc.':'AKAM',
          'Liberty Global, Inc., Class A':'LBTYA','IAC/InterActiveCorp':'IACI',
          'Pharmaceutical Product Development, Inc.':'PPDI'}
for table in soup.find_all('table')[2:5]:
    for tr in table.find_all('tr')[1:]:
        v = [c.get_text(' ', strip=True) for c in tr.find_all('td', recursive=False)]
        v = [c for c in v if c and c != '$']
        if len(v) != 3 or not v[1].replace(',','').isdigit():
            continue
        name = v[0].rstrip('*')
        match = max(name_map, key=lambda k: SequenceMatcher(None,norm(name),norm(k)).ratio())
        score = SequenceMatcher(None,norm(name),norm(match)).ratio()
        assert name in manual or score >= .9, (name, match, score)
        initial.append(dict(date='2009-09-30', ticker=manual.get(name,name_map[match]),
                            name=name, shares=int(v[1].replace(',','')),
                            value_usd=int(v[2].replace(',',''))))
assert len(initial) == 100
assert len({r['ticker'] for r in initial}) == 100
assert sum(r['value_usd'] for r in initial) == 17093021127
initial = pd.DataFrame(initial)
initial['equity_weight'] = initial.value_usd / initial.value_usd.sum()
initial.to_csv(P / 'qqq_20090930_primary_weights.csv', index=False)
annual = pd.concat([initial, annual], ignore_index=True)

filings = {}
for i, form in enumerate(sec['form']):
    if form == 'N-30B-2' and sec['reportDate'][i] in set(annual.date):
        filings[sec['reportDate'][i]] = {k:sec[k][i] for k in ['filingDate','acceptanceDateTime','accessionNumber','primaryDocument']}
usable_dates = {'2009-09-30':'2010-01-19','2010-09-30':'2010-12-31',
                '2011-09-30':'2012-01-23','2012-09-30':'2013-01-29','2013-09-30':'2014-01-21'}
rows = []
def append_row(date, available, ticker, name, weight, source, isin='', **extra):
    sid,pid,quality,notes,candidates = resolve(ticker,date,name,isin)
    rows.append(dict(effective_date=date, available_date=available, security_id=sid,
                     weight=float(weight), ticker=ticker, name=name, isin=isin,
                     price_id=pid, identity_quality=quality, identity_notes=notes,
                     candidate_price_ids=candidates, source=source, **extra))

for date, g in annual.groupby('date'):
    filing = filings[date]
    url = 'https://www.sec.gov/Archives/edgar/data/1067839/' + filing['accessionNumber'].replace('-','') + '/' + filing['primaryDocument']
    for r in g.to_dict('records'):
        append_row(date,usable_dates[date],r['ticker'],r['name'],r['equity_weight'],'QQQ_SEC_annual',
                   source_url=url,weight_reference_date=date, source_weight=r['equity_weight'],
                   weight_quality='reported_fund_equity_normalized',
                   availability_quality='verified_SEC_filing_next_US_session',
                   published_date=filing['filingDate'],source_total_equity_weight=1.0)

for date, g in monthly.groupby('date'):
    total = g.holdingPercent.astype(float).sum()
    assert 98 < total < 102
    # Business days here mean Monday-Friday; holidays are not removed.
    available = (pd.Timestamp(date) + pd.offsets.BDay(5)).strftime('%Y-%m-%d')
    url = 'https://www.blackrock.com/varnish-api/uk-retail01-product-data/product-data/api/v2/get-product-data?appSubType=ISHARES&appType=PRODUCT_PAGE&component=holdings.all&locale=en_GB&portfolioId=253741&targetSite=ishares-uk&userType=individual&excludeContent=true&includeConfig=true&asOfDate=' + date.replace('-','')
    for r in g.to_dict('records'):
        append_row(date,available,r['ticker'],r['issueName'],float(r['holdingPercent'])/total,'CNDX_monthly',r['isin'],
                   source_url=url,weight_reference_date=date,source_weight=float(r['holdingPercent'])/100,
                   weight_quality='reported_fund_equity_normalized',
                   availability_quality='ASSUMED_5_MonFri_business_days_not_verified_publication',
                   published_date='',source_total_equity_weight=total/100)

# The Nasdaq-authored PDF is preserved by a newspaper, because Nasdaq's original
# presentation and shares CSV now return 404. Publication date is independently
# established by the Nasdaq trader announcement.
pdf = PdfReader(P / '2011_special_rebalance_nasdaq_mirrored.pdf')
weight_text = pdf.pages[21].extract_text()
share_text = pdf.pages[20].extract_text()
weights = {}
for ticker,current,projected,change in re.findall(r'\b([A-Z]{1,5})\s+([\d.]+)%\s+([\d.]+)%\s+(-?[\d.]+)%',weight_text):
    weights[ticker] = (float(current)/100,float(projected)/100)
shares = {}
for ticker,current,projected in re.findall(r'(?<![A-Z])([A-Z]{1,5})\*?\s+([\d,]+)\s+([\d,]+)',share_text):
    if ',' in current and ',' in projected:
        shares[ticker] = (int(current.replace(',','')),int(projected.replace(',','')))
assert len(weights) == 100, len(weights)
assert len(shares) == 100, len(shares)
special = pd.DataFrame([dict(ticker=t,current_weight=v[0],projected_weight=v[1],
                             current_index_shares=shares[t][0],projected_index_shares=shares[t][1])
                        for t,v in sorted(weights.items())])
special.to_csv(P / '2011_special_rebalance_primary_projection.csv',index=False)
mirror_url = 'https://st.ilsole24ore.com/pdf2010/SoleOnLine5/_Oggetti_Correlati/Documenti/Finanza%20e%20Mercati/2011/04/NDXSpecialRebalancePresentation%5B1%5D.pdf?uuid=d4dfeea2-5f69-11e0-b482-a582cb592628'
names = annual.set_index('ticker').name.to_dict()
for date, col, quality in [('2011-04-04','current_weight','Nasdaq_reported_rounded_start_of_day_weights'),
                          ('2011-05-02','projected_weight','Nasdaq_projected_rounded_weights_drift_from_Apr1_before_use')]:
    total = special[col].sum()
    for r in special.to_dict('records'):
        append_row(date,'2011-04-06',r['ticker'],names.get(r['ticker'],r['ticker']),r[col]/total,
                   'Nasdaq_2011_special_rebalance',source_url=mirror_url,
                   weight_reference_date='2011-04-01',source_weight=r[col],weight_quality=quality,
                   availability_quality='Nasdaq_Apr5_announcement_next_US_session',
                   published_date='2011-04-05',source_total_equity_weight=total)

out = pd.DataFrame(rows).sort_values(['effective_date','security_id'])
assert not out.duplicated(['effective_date','security_id']).any(), out[out.duplicated(['effective_date','security_id'],False)].to_dict('records')
assert np.allclose(out.groupby('effective_date').weight.sum(),1)
out.to_csv(P / 'target_weights.csv',index=False)

# Source dates and vendor IDs are retained even for unresolved records.
crosswalk = out.groupby(['ticker','isin','security_id','price_id','identity_quality','identity_notes','candidate_price_ids'],dropna=False).agg(
    first_source_date=('effective_date','min'),last_source_date=('effective_date','max'),
    observed_names=('name',lambda s:' | '.join(sorted(set(s))))).reset_index()
crosswalk.to_csv(P / 'dated_security_identity_map.csv',index=False)
out[out.price_id.eq('')].to_csv(P / 'unresolved_weight_identities.csv',index=False)

membership = pd.read_csv(H / 'membership/nasdaq100_membership_snapshots.csv')
members=[]
for date,tickers in membership[['date','tickers']].itertuples(index=False,name=None):
    for t in tickers.split(','):
        sid,pid,quality,notes,candidates=resolve(t,date)
        members.append(dict(effective_date=date,available_date=date,security_id=sid,ticker=t,
                            price_id=pid,identity_quality=quality,candidate_price_ids=candidates,
                            availability_quality='ASSUMED_known_on_effective_date_community_reconstruction'))
memberout=pd.DataFrame(members)
memberout.to_csv(P / 'membership_snapshots_dated.csv',index=False)
coverage=[]
for date,g in out.groupby('effective_date'):
    mapped=g.price_id.ne('')
    usable_price=[]
    for r in g.to_dict('records'):
        a=by_id.get(r['price_id'],{})
        usable_price.append(bool(a and a['first_price']<=r['weight_reference_date']<=a['last_price']))
    coverage.append(dict(effective_date=date,available_date=g.available_date.iloc[0],source=g.source.iloc[0],
                         rows=len(g),mapped_rows=int(mapped.sum()),unresolved_rows=int((~mapped).sum()),
                         mapped_weight=float(g.loc[mapped,'weight'].sum()),unresolved_weight=float(g.loc[~mapped,'weight'].sum()),
                         reference_price_date_range_covered_rows=sum(usable_price),
                         reference_price_date_range_covered_weight=float(g.loc[usable_price,'weight'].sum())))
coverage=pd.DataFrame(coverage)
coverage.to_csv(P / 'weight_join_coverage.csv',index=False)

# Audit every intended monthly purchase date without inventing an allocation for
# a new constituent absent from the latest published source.
calendar=pd.read_csv(H/'prices/quantiacs_daily_member_counts.csv').iloc[:,0]
calendar=pd.to_datetime(calendar)
calendar=calendar[(calendar>='2010-09-30')&(calendar<='2026-09-30')]
purchase_dates=calendar.groupby(calendar.dt.to_period('M')).max()
purchase_audit=[]
for stamp in purchase_dates:
    date=stamp.strftime('%Y-%m-%d')
    eligible=out[(out.effective_date<=date)&(out.available_date<=date)]
    if eligible.empty:
        purchase_audit.append(dict(purchase_date=date,status='no_available_weight_snapshot'))
        continue
    source_date=eligible.effective_date.max()
    basket=eligible[eligible.effective_date==source_date]
    member_date=memberout[memberout.effective_date<=date].effective_date.max()
    current=memberout[memberout.effective_date==member_date]
    missing=current[~current.security_id.isin(basket.security_id)]
    departed=basket[~basket.security_id.isin(current.security_id)]
    purchase_audit.append(dict(purchase_date=date,source_effective_date=source_date,
        source_available_date=basket.available_date.iloc[0],source=basket.source.iloc[0],
        snapshot_age_days=(stamp-pd.Timestamp(basket.weight_reference_date.iloc[0])).days,
        current_members=len(current),new_members_without_source_weight=len(missing),
        missing_member_tickers='|'.join(sorted(missing.ticker)),
        departed_source_names='|'.join(sorted(departed.ticker)),
        departed_source_weight=float(departed.weight.sum()),
        unresolved_positive_source_weight=float(basket.loc[basket.price_id.eq(''),'weight'].sum()),
        status='proxy_or_more_data_required' if len(missing) or basket.price_id.eq('').any() else 'source_weights_joined_price_and_actions_still_need_validation'))
purchase_audit=pd.DataFrame(purchase_audit)
purchase_audit.to_csv(P/'purchase_date_source_audit.csv',index=False)

initial_names=set(initial.ticker)
start_names=set(membership[membership.date<='2010-09-30'].iloc[-1].tickers.split(','))
summary={
 'status':'SOURCE INPUTS AND CANDIDATE IDENTITIES; FULL STRATEGY NOT VALIDATED',
 'snapshots':int(out.effective_date.nunique()),'rows':len(out),
 'snapshot_sources':out.groupby('source').effective_date.nunique().to_dict(),
 'mapped_rows':int(out.price_id.ne('').sum()),'unresolved_rows':int(out.price_id.eq('').sum()),
 'mapped_row_fraction':float(out.price_id.ne('').mean()),
 'monthly_purchase_dates':len(purchase_audit),
 'purchase_dates_with_new_members_missing_source_weights':int(purchase_audit.new_members_without_source_weight.gt(0).sum()),
 'unresolved_snapshot_weight_min':float(coverage.unresolved_weight.min()),
 'unresolved_snapshot_weight_max':float(coverage.unresolved_weight.max()),
 'source_equity_normalization':'Every source snapshot sums to one over ALL source equities. Unresolved weights are preserved; no renormalization over price survivors.',
 'early_initial':{'holdings_date':'2009-09-30','filed':'2010-01-15','usable_date':'2010-01-19',
                  'total_investments_usd':17093021127,
                  'new_2010_members_without_2009_weight':sorted(start_names-initial_names),
                  '2009_names_no_longer_members_at_start':sorted(initial_names-start_names),
                  'limitations':'2009 prices are absent from current vendor corpus. Initial stale weights are causal, but drifting the baseline to Sep2010 and assigning new-member weights requires more input or an explicit proxy.'},
 'filings':filings,
 'special_rebalance':{'announcement_url':'https://nasdaqtrader.com/TraderNews.aspx?id=fpnews2011-018',
                      'announced':'2011-04-05','effective':'2011-05-02','mirror_url':mirror_url,
                      'reference_close':'2011-04-01','current_weight_sum':float(special.current_weight.sum()),
                      'projected_weight_sum':float(special.projected_weight.sum()),
                      'limitations':'Rounded published projections, not actual May2 close weights. Exact index shares also preserved. Corporate changes and price drift between reference and rebalance still need handling.'},
 'causal_use_rules':[
  'Select latest effective snapshot whose available_date is no later than trade date AND effective_date is no later than trade date.',
  'To drift weights, use each snapshot weight_reference_date and prices available by the decision cutoff; never interpolate toward a future snapshot.',
  'CNDX availability uses five Monday-Friday business days as an explicit unverified publication assumption. Sep2026 source is not usable during Sep2026.',
  'Membership effective dates are community reconstructions; using them contemporaneously is an explicit availability assumption.',
  'An index removal stops new purchases only; it never justifies selling retained shares or extinguishing their value.',
  'New member missing from the selected source has no supplied weight: fail or use a separately labeled proxy. Do not backfill from a future source.',
  'Vendor joins are candidates. Crosswalk identity does not validate corporate actions, distributions, terminal proceeds, or retained-security price continuity.',
  'Do not execute the full backtest while unresolved positive weights or unvalidated corporate-action values remain.'
 ],
 'missing_monthly_snapshots_2014_on':['2017-01','2017-02','2017-03','2017-04','2017-05','2017-06'],
}
(P/'input_feasibility_audit.json').write_text(json.dumps(summary,indent=2))
files=['target_weights.csv','dated_security_identity_map.csv','membership_snapshots_dated.csv',
       'weight_join_coverage.csv','unresolved_weight_identities.csv','qqq_20090930_primary_weights.csv',
       'purchase_date_source_audit.csv',
       '2011_special_rebalance_primary_projection.csv','qqq_20090930_report.html',
       '2011_special_rebalance_nasdaq_mirrored.pdf']
(P/'input_artifact_sha256.json').write_text(json.dumps({n:sha256((P/n).read_bytes()).hexdigest() for n in files},indent=2))
print(json.dumps({k:summary[k] for k in ['status','snapshots','rows','mapped_rows','unresolved_rows','early_initial']},indent=2))
