"""Download public Quantiacs data with source IDs retained to prevent ticker collisions."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import requests, json, time, hashlib
import xarray as xr
P=Path(__file__).parent
ASSET_URL='https://data-api.quantiacs.io/assets?min_date=2010-09-01&max_date=2026-10-02&type=NASDAQ100'
a=requests.get(ASSET_URL,timeout=60);a.raise_for_status();(P/'quantiacs_ndx_assets.json').write_text(a.text)
assets=a.json();ids=sorted(x['id'] for x in assets)
chunks=[ids[i:i+50] for i in range(0,len(ids),50)]

def fetch(arg):
 i,ids=arg;path=P/f'quantiacs_chunk_{i:02d}.nc'
 params={'assets':ids,'min_date':'2010-09-01','max_date':'2026-10-02','type':'NDX100'}
 for n in range(3):
  try:
   r=requests.post('https://data-api.quantiacs.io/data',json=params,timeout=120);r.raise_for_status();path.write_bytes(r.content)
   print(i,len(ids),len(r.content),flush=True);return {'file':path.name,'request':params,'sha256':hashlib.sha256(r.content).hexdigest()}
  except Exception as e:
   print(i,str(e),flush=True)
   if n==2:raise
   time.sleep(2)
with ThreadPoolExecutor(max_workers=3) as pool: downloads=list(pool.map(fetch,enumerate(chunks)))
arrays=[xr.open_dataarray(P/x['file']).load() for x in downloads]
all_data=xr.concat(arrays,dim='asset').sortby('time').sortby('asset');all_data.name='quantiacs_nasdaq100'
all_data.to_netcdf(P/'quantiacs_ndx_all.nc',engine='scipy')
meta={'retrieved_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'asset_url':ASSET_URL,'data_url':'https://data-api.quantiacs.io/data','documentation':'https://quantiacs.com/documentation/en/user_guide/data.html','toolbox_source':'https://github.com/quantiacs/toolbox/blob/master/qnt/data/stocks.py','asset_count':len(assets),'dimensions':dict(all_data.sizes),'fields':list(all_data.field.values),'first_date':str(all_data.time.min().values),'last_date':str(all_data.time.max().values),'downloads':downloads}
(P/'quantiacs_download_manifest.json').write_text(json.dumps(meta,indent=2))
print(json.dumps({k:v for k,v in meta.items() if k!='downloads'},indent=2),flush=True)
