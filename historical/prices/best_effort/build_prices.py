"""Public vendor price reconstruction without return-fitting.

Quantiacs endpoint close is empirically split-adjusted even for type=''.
Yahoo Close is also split-adjusted; explicit Yahoo splits are used to restore
contemporaneous share units. Non-ordinary Yahoo split factors may represent
spin-off adjustment factors: action ledger must replace them with entitlements.
This builder exposes both candidate panels and all action factors for audit.
"""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import json, time, hashlib, traceback
import numpy as np
import pandas as pd
import xarray as xr
import requests
import yfinance as yf
P=Path(__file__).resolve().parent; BASE=P.parent
START='2010-09-01';END='2026-10-01'
EXTRAS=['TAK','LBTYA','LBTYK','AMFW','WG.L','CDK','LOGM','LILA','LILAK','NXT','QRTEP','QVCGA','QVCGP','LGF.A','LGF.B','LGF-A','LGF-B','LION','STRZ','YHOO','AABA','WTW','KRFT','GOLD','MICC','NIHD','SHLD','SHLDQ','IACI','IAC','BATRR','SOLS','SATS','T','WBD','CI','AGN','ABBV','TDY','VTRS','PSKY','PARA','DIS','GEN','BMY','TKO','CHTR','LILAB','LILAV','FWONA','FWONK','LSXMA','LSXMK','GRPN','NWSA','NWS','ZIMV','GRAL','VSTS','GEHC','GEV','CEG','NFE','LBRDA','LBRDK','LMDIA','LVNTA','GLIBA','VAC','ASIX','GTX','REZI','CVET','VMW','CRNC','LLYVA','LLYVK','VSNT','VZ','SUNN.SW']
ASSETS=json.loads((BASE/'quantiacs_ndx_assets.json').read_text())
GENERAL=json.loads((BASE/'repairs/quantiacs_general_assets.json').read_text())
MAP={x['id']:x for x in GENERAL+ASSETS}
(P/'all_asset_metadata.json').write_text(json.dumps(list(MAP.values()),indent=2))

def yahoo_one(symbol):
    f=P/('yf_'+symbol.replace('/','_')+'.csv')
    if f.exists() and f.stat().st_size>500:return {'symbol':symbol,'status':'cached','path':f.name}
    try:
        q=yf.Ticker(symbol).history(start=START,end=END,auto_adjust=False,actions=True,raise_errors=True)
        if q.empty:return {'symbol':symbol,'status':'empty'}
        q.to_csv(f)
        return {'symbol':symbol,'status':'ok','rows':len(q),'first':str(q.index[0]),'last':str(q.index[-1]),'path':f.name}
    except Exception as e:return {'symbol':symbol,'status':'error','error':str(e)[:220]}

def download():
    symbols=sorted(set([a['symbol'] for a in ASSETS]+EXTRAS+['CHFUSD=X','GBPUSD=X','ECHO','GLIBK','LILAP']))
    out=[]
    with ThreadPoolExecutor(max_workers=6) as pool:
        jobs={pool.submit(yahoo_one,s):s for s in symbols}
        for n,job in enumerate(as_completed(jobs)):
            result=job.result();out.append(result)
            if n%25==0:print('Yahoo',n+1,'/',len(symbols),result['symbol'],result['status'],flush=True)
    (P/'yahoo_download_manifest.json').write_text(json.dumps(out,indent=2))
    # General endpoint extends the available universe, not its data conventions.
    wanted=sorted(set(x['id'] for x in GENERAL if x['symbol'] in EXTRAS))
    chunks=[wanted[i:i+50] for i in range(0,len(wanted),50)]
    for n,ids in enumerate(chunks):
        f=P/f'general_successors_{n:02d}.nc'
        if not f.exists() or not set(ids).issubset(set(map(str, xr.open_dataarray(f).asset.values))):
            r=requests.post('https://data-api.quantiacs.io/data',json={'assets':ids,'min_date':START,'max_date':'2026-09-30','type':''},timeout=120);r.raise_for_status();f.write_bytes(r.content)
        print('General',n,len(ids),flush=True)
    (P/'general_download_manifest.json').write_text(json.dumps({'chunks':chunks,'source':'https://data-api.quantiacs.io/data','unit_check':'general_unit_test.nc matches NDX adjusted data for AAPL EBAY GOOGL'},indent=2))

def yf_frame(symbol):
    f=P/('yf_'+symbol.replace('/','_')+'.csv')
    if not f.exists():return None
    x=pd.read_csv(f)
    x['date']=pd.to_datetime(x.Date.str[:10]);x=x.set_index('date').sort_index()
    sf=x['Stock Splits'].replace(0,1)
    # Reverse future adjustment only; ex-date quote uses new units.
    future=sf.iloc[::-1].cumprod().iloc[::-1]/sf
    x['close_usd']=x.Close*future
    x['dividend_usd']=x.Dividends*future
    x['unit_restoration_factor']=future
    return x

def build():
    frames=[];splits=[];quality=[];assets=[]
    datasets=[xr.open_dataarray(BASE/'quantiacs_ndx_all.nc')]+[xr.open_dataarray(f) for f in sorted(P.glob('general_successors_*.nc'))]
    seen=set()
    for data in datasets:
        for asset in data.asset.values:
            asset=str(asset)
            if asset in seen:continue
            seen.add(asset);q=data.sel(asset=asset,field=['close','divs','split_cumprod']).to_pandas().T.sort_index().dropna(subset=['close'])
            q['date']=pd.to_datetime(q.index);q=q.set_index('date')
            q['close_usd']=q.close/q.split_cumprod
            q['dividend_usd']=q.divs.fillna(0)/q.split_cumprod
            q['security_id']=asset;q['source']='quantiacs';q['quality']='split_factor_normalized_vendor_unverified'
            factors=(q.split_cumprod/q.split_cumprod.shift()).dropna()
            for d,v in factors.items():
                if abs(v-1)>1e-6:splits.append(dict(date=str(d.date()),security_id=asset,ratio=v,source='quantiacs_split_cumprod',symbol=MAP.get(asset,{}).get('symbol','')))
            frames.append(q[['security_id','close_usd','dividend_usd','source','quality']].reset_index())
    panel=pd.concat(frames,ignore_index=True)
    # Preserve issuer-supported repairs and remove contaminated post-redemption record.
    repair=pd.read_csv(BASE/'repairs/priority_daily_quotes.csv.gz');repair['date']=pd.to_datetime(repair.date)
    repair=repair.rename(columns={'source_asset_id':'security_id','raw_close_usd':'close_usd','cash_dividend_usd_per_share':'dividend_usd'})
    repair['source']='quantiacs_plus_primary_repair'
    for asset in repair.security_id.unique():panel=panel[~((panel.security_id==asset)&panel.date.between(repair[repair.security_id==asset].date.min(),repair[repair.security_id==asset].date.max()))]
    panel=pd.concat([panel,repair[['date','security_id','close_usd','dividend_usd','source','quality']]],ignore_index=True)
    panel=panel[~((panel.security_id=='tts-130097863')&(panel.date>'2015-12-28'))]
    # Raw Yahoo candidates separately: do not blindly map reused tickers.
    yr=[];ys=[]
    for f in sorted(P.glob('yf_*.csv')):
        symbol=f.stem[3:];q=yf_frame(symbol)
        if q is None:continue
        q['symbol']=symbol
        for d,v in q.loc[q['Stock Splits']!=0,'Stock Splits'].items():ys.append(dict(date=str(d.date()),symbol=symbol,ratio=v,source='yahoo_split_field'))
        yr.append(q[['symbol','close_usd','dividend_usd','unit_restoration_factor']].reset_index())
    if yr:pd.concat(yr,ignore_index=True).to_csv(P/'yahoo_raw_candidates.csv.gz',index=False)
    pd.DataFrame(ys).to_csv(P/'yahoo_split_candidates.csv',index=False)
    # Prefer Yahoo ordinary dividends/raw units only for stable, unique live identities
    # whose price series overlaps and agrees outside known corporate-event jumps.
    # Additional identities are explicit and retain a separate namespace.
    ymap={s:'yahoo:'+s for s in EXTRAS if s not in {a['symbol'] for a in MAP.values()}}
    ymap.update({x['symbol']:x['id'] for x in GENERAL if x['symbol'] in EXTRAS and sum(a['symbol']==x['symbol'] for a in MAP.values())==1})
    ymap.update({s:i for s,i in [('TAK','yahoo:TAK'),('LBTYA','tts-1784188'),('LBTYK','tts-3250167'),('WTW','tts-159320127')]})
    # Baseline includes only missing successor securities from Yahoo until crosschecks.
    for s,asset in ymap.items():
        if asset in set(panel.security_id):continue
        q=yf_frame(s)
        if q is None:continue
        q['security_id']=asset;q['source']='yahoo_via_yfinance';q['quality']='raw_restored_from_yahoo_split_fields; corporate_adjustments_need_review'
        panel=pd.concat([panel,q[['security_id','close_usd','dividend_usd','source','quality']].reset_index()],ignore_index=True)
        for d,v in q.loc[q['Stock Splits']!=0,'Stock Splits'].items():splits.append(dict(date=str(d.date()),security_id=asset,ratio=v,source='yahoo_split_field_unclassified',symbol=s))
    panel=panel[(panel.date>='2010-09-01')&(panel.date<='2026-09-30')].sort_values(['security_id','date']).drop_duplicates(['date','security_id'],keep='last')
    panel.to_csv(P/'prices_usd.csv.gz',index=False)
    pd.DataFrame(splits).to_csv(P/'split_events.csv',index=False)
    (P/'yahoo_security_map.json').write_text(json.dumps(ymap,indent=2))
    cov=panel.groupby('security_id').agg(first=('date','min'),last=('date','max'),observations=('date','size'),dividend_days=('dividend_usd',lambda z:(z!=0).sum()),source=('source','last')).reset_index();cov['symbol']=cov.security_id.map(lambda z:MAP.get(z,{}).get('symbol',z.replace('yahoo:','')));cov.to_csv(P/'price_coverage.csv',index=False)
    summary={'rows':len(panel),'securities':panel.security_id.nunique(),'status':'baseline executable panel; raw-unit and action reviews ongoing','yahoo_downloaded':len(list(P.glob('yf_*.csv'))),'baseline_sources':panel.source.value_counts().to_dict()};(P/'price_build_summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary),flush=True)
if __name__=='__main__':
    import sys
    if '--build-only' not in sys.argv:download()
    build()
